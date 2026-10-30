// frontend/types/api-contracts.ts

// Common types
export type UUID = string;
export type ISODateTime = string;

// Standard API error response
export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details: unknown[];
    request_id: string;
  };
}

// Authentication requests
export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  full_name: string;
  email: string;
  password: string;
  organization_name: string;
}

// Authentication responses
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

// Submission statuses
export type SubmissionStatus =
  | "draft"
  | "submitted"
  | "processing"
  | "under_review"
  | "changes_requested"
  | "approved"
  | "rejected"
  | "failed_needs_attention";

// Analysis job statuses
export type AnalysisJobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "partial"
  | "failed";

// Analysis finding categories
export type FindingCategory =
  | "tone"
  | "terminology"
  | "messaging"
  | "factual_claim"
  | "visual"
  | "accessibility"
  | "other";

// Finding severity
export type FindingSeverity =
  | "info"
  | "low"
  | "medium"
  | "high";

// Finding result classification
export type FindingResult =
  | "conflict"
  | "unsupported"
  | "inconclusive"
  | "check_unavailable";

// Finding detection method
export type DetectionMethod =
  | "deterministic"
  | "ai_assisted"
  | "ocr"
  | "visual_check";

// Status of an individual analysis check.
export type CheckOutcomeStatus =
  | "supported"
  | "issues_found"
  | "inconclusive"
  | "check_unavailable"
  | "disabled"
  | "not_assessed"
  | "coverage_limited";

// Result describing what a check assessed.
export interface CheckOutcome {
  category: FindingCategory;
  status: CheckOutcomeStatus;
  message: string;
  detection_method: DetectionMethod | null;
  assessed_count: number;
  scope: string | null;
}

// Evidence returned with a finding
export interface FindingEvidence {
  submitted_text?: string | null;
  approved_reference?: string | null;
  source_name?: string | null;
  source_url?: string | null;
}

// Text finding location
export interface TextRangeLocation {
  kind: "text_range";
  start_offset: number;
  end_offset: number;
  matched_text: string;
}

// Image finding location
export interface ImageBoundingBoxLocation {
  kind: "image_bbox";
  x: number;
  y: number;
  width: number;
  height: number;
}

export type FindingLocation =
  | TextRangeLocation
  | ImageBoundingBoxLocation
  | null;

// Individual analysis finding
export interface Finding {
  id: UUID;
  category: FindingCategory;
  severity: FindingSeverity;
  result: FindingResult;
  explanation: string;
  evidence: FindingEvidence;
  source_rule_version_id: UUID | null;
  source_fact_version_id: UUID | null;
  location: FindingLocation;
  suggested_correction: string | null;
  detection_method: DetectionMethod;
  requires_human_review: boolean;
}

// Analysis summary
export interface AnalysisSummary {
  info: number;
  low: number;
  medium: number;
  high: number;
  total: number;
}

// Completed or partial analysis result
export interface AnalysisResultResponse {
  job_id: UUID;
  submission_id: UUID;
  submission_version_id: UUID;
  status: "completed" | "partial";
  findings: Finding[];
  check_outcomes: CheckOutcome[];
  summary: AnalysisSummary;
}

// Response when analysis is queued or an existing job is reused.
// Existing idempotent requests may return a status other than "queued".
export interface AnalysisAcceptedResponse {
  job_id: UUID;
  submission_id: UUID;
  version_number: number;
  status: AnalysisJobStatus;
}

// Analysis job status response
export interface AnalysisJobResponse {
  job_id?: UUID;
  submission_id?: UUID;
  version_number?: number;
  status: AnalysisJobStatus;
  attempts?: number;
  created_at?: ISODateTime;
  updated_at?: ISODateTime;
  started_at?: ISODateTime | null;
  completed_at?: ISODateTime | null;
  error_code?: string | null;
  error_message?: string | null;
  check_outcomes: CheckOutcome[];
}

// Submission creation response
export interface SubmissionCreatedResponse {
  submission_id: UUID;
  version_number: number;
  status: SubmissionStatus;
  created_at: ISODateTime;
}

// Submission content
// Exactly one content source must be supplied.
export type SubmissionContent =
  | {
    title: string;
    text: string;
    file?: never;
  }
  | {
    title: string;
    file: File;
    text?: never;
  };

// Brand rule creation
export interface CreateBrandRuleRequest {
  title: string;
  category: string;
  description: string;
  rule_text: string;
  severity: FindingSeverity;
}

// Approved fact creation
export interface CreateBrandFactRequest {
  label: string;
  fact_text: string;
  source_url: string;
}

// Human review actions
export type ReviewActionRequest =
  | {
    action: "approve";
    comment?: string;
  }
  | {
    action: "request_changes";
    comment: string;
  }
  | {
    action: "reject";
    comment: string;
  };