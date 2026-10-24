import { apiRequest } from "@/lib/api-client";

import type {
  Finding,
  UUID,
} from "@/types/api-contracts";

// The API permits a findings response to be wrapped
// with pagination metadata. Exact metadata is pending
// confirmation from the backend response schema.
export type FindingsResponse =
  | Finding[]
  | {
      findings: Finding[];
      [metadata: string]: unknown;
    };

// Retrieve findings for a specific immutable version.
export async function getSubmissionFindings(
  submissionId: UUID,
  version: number
): Promise<FindingsResponse> {
  if (!submissionId.trim()) {
    throw new Error("Submission ID is required.");
  }

  if (!Number.isInteger(version) || version < 1) {
    throw new Error("Version must be a positive integer.");
  }

  const query = new URLSearchParams({
    version: String(version),
  });

  return apiRequest<FindingsResponse>(
    `/api/v1/submissions/${encodeURIComponent(
      submissionId
    )}/findings?${query.toString()}`,
    {
      method: "GET",
    }
  );
}

// Extract findings regardless of whether the response
// is a direct array or a paginated object.
export function extractFindings(
  response: FindingsResponse
): Finding[] {
  return Array.isArray(response)
    ? response
    : response.findings;
}
