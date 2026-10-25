import { apiRequest } from "@/lib/api-client";
import type { AnalysisJobStatus, UUID } from "@/types/api-contracts";

export interface AnalysisJobResponse {
  status: AnalysisJobStatus;
  error_code?: string | null;
  error_message?: string | null;
}

export async function getAnalysisJob(
  jobId: UUID
): Promise<AnalysisJobResponse> {
  if (!jobId.trim()) {
    throw new Error("Analysis job ID is required.");
  }

  return apiRequest<AnalysisJobResponse>(
    `/api/v1/analysis-jobs/${encodeURIComponent(jobId)}`,
    { method: "GET" }
  );
}