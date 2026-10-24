import { apiRequest } from "@/lib/api-client";

import type {
  RegisterRequest,
  UUID,
} from "@/types/api-contracts";

export interface UserResponse {
  id: UUID;
  full_name: string;
  email: string;
}

export interface OrganizationResponse {
  id: UUID;
  name: string;
}

export type UserRole = "admin" | "creator" | "reviewer";

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserResponse;
  organization: OrganizationResponse;
  role: UserRole;
}

export interface MeResponse {
  user: UserResponse;
  organization: OrganizationResponse;
  role: UserRole;
}

// Register a user and create their initial organisation.
export async function registerUser(
  data: RegisterRequest
): Promise<AuthResponse> {
  return apiRequest<AuthResponse>(
    "/api/v1/auth/register",
    {
      method: "POST",
      body: JSON.stringify(data),
    }
  );
}

// Retrieve the authenticated user's active organisation.
export async function getCurrentUser(): Promise<MeResponse> {
  return apiRequest<MeResponse>("/api/v1/me", {
    method: "GET",
  });
}