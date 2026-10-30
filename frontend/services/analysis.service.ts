import { apiRequest } from "@/lib/api-client";
import type {
  AnalysisJobResponse as ApiAnalysisJobResponse,
  UUID,
} from "@/types/api-contracts";

export type AnalysisJobResponse = ApiAnalysisJobResponse;

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