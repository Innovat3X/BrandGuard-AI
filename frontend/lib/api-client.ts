// frontend/lib/api-client.ts

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

const ACCESS_TOKEN_KEY = "brandguard_access_token";

export type AccessTokenProvider = () =>
  | string
  | null
  | Promise<string | null>;

let accessTokenProvider: AccessTokenProvider | undefined;

// Optional integration point for an app-level authentication store.
export function configureAccessTokenProvider(
  provider?: AccessTokenProvider
): void {
  accessTokenProvider = provider;
}

// Store the token for this browser session.
export function saveAccessToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
  } catch {
    return null;
  }
}

interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: unknown[];
    request_id?: string;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown[];
  readonly requestId: string | null;

  constructor(
    status: number,
    message: string,
    code = "API_ERROR",
    details: unknown[] = [],
    requestId: string | null = null
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown;

  try {
    body = await response.json();
  } catch {
    body = null;
  }

  const errorBody = isObject(body)
    ? (body as ApiErrorBody).error
    : undefined;

  return new ApiError(
    response.status,
    errorBody?.message ??
      `The request failed with status ${response.status}.`,
    errorBody?.code ?? "API_ERROR",
    errorBody?.details ?? [],
    errorBody?.request_id ?? null
  );
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  if (!path.startsWith("/")) {
    throw new Error("API paths must start with /.");
  }

  const headers = new Headers(options.headers);

  headers.set("Accept", "application/json");

  const token = accessTokenProvider
    ? await accessTokenProvider()
    : getStoredAccessToken();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // FormData must set its own Content-Type boundary.
  // JSON bodies use application/json.
  if (
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      cache: options.cache ?? "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "Unable to connect to BrandGuard AI server. Check your connection and API server.",
      "NETWORK_ERROR"
    );
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(
      response.status,
      "The server returned an invalid response.",
      "INVALID_RESPONSE"
    );
  }
}