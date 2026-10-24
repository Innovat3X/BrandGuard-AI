import { apiRequest } from "@/lib/api-client";

import type {
  AnalysisJobStatus,
  UUID,
} from "@/types/api-contracts";

// Minimal response type based on the confirmed API contract.
// Additional fields will be added after Bhumika confirms
// the implemented response schema.
export interface AnalysisJobResponse {
  status: AnalysisJobStatus;
}

// Retrieve the current status of an analysis job.
export async function getAnalysisJob(
  jobId: UUID
): Promise<AnalysisJobResponse> {
  if (!jobId.trim()) {
    throw new Error("Analysis job ID is required.");
  }

  return apiRequest<AnalysisJobResponse>(
    `/api/v1/analysis-jobs/${encodeURIComponent(jobId)}`,
    {
      method: "GET",
    }
  );
}