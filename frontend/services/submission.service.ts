import { apiRequest } from "@/lib/api-client";

import type {
  AnalysisAcceptedResponse,
  SubmissionContent,
  SubmissionStatus,
  UUID,
} from "@/types/api-contracts";

// The exact response field names must be confirmed
// against the implemented FastAPI response schema.
export interface SubmissionCreatedResponse {
  submission_id: UUID;
  version_number: number;
  status: SubmissionStatus;
  created_at: string;
}

// Create a submission using multipart/form-data.
// Exactly one content source is required: text OR file.
export async function createSubmission(
  input: SubmissionContent
): Promise<SubmissionCreatedResponse> {
  if (!input.title.trim()) {
    throw new Error("Submission title is required.");
  }

  const hasText = typeof input.text === "string";
  const hasFile = input.file !== undefined;

  if (hasText === hasFile) {
    throw new Error(
      "Provide exactly one content source: text or file."
    );
  }

  const formData = new FormData();

  formData.append("title", input.title.trim());

  if (hasText && input.text.trim()) {
    formData.append("text", input.text);
  } else if (hasFile && input.file instanceof File) {
    formData.append("file", input.file);
  } else {
    throw new Error("The supplied content is empty or invalid.");
  }

  return apiRequest<SubmissionCreatedResponse>(
    "/api/v1/submissions",
    {
      method: "POST",
      body: formData,
    }
  );
}

// Queue asynchronous analysis for a submission.
export async function queueSubmissionAnalysis(
  submissionId: UUID,
  versionNumber?: number
): Promise<AnalysisAcceptedResponse> {
  const options: RequestInit = {
    method: "POST",
  };

  if (versionNumber !== undefined) {
    options.body = JSON.stringify({
      version_number: versionNumber,
    });
  }

  return apiRequest<AnalysisAcceptedResponse>(
    `/api/v1/submissions/${encodeURIComponent(submissionId)}/analysis`,
    options
  );
}