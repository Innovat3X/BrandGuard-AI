from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.analysis.contracts import Finding


class SubmissionCreatedResponse(BaseModel):
    submission_id: UUID
    version_number: int
    status: str
    created_at: datetime


class QueueAnalysisRequest(BaseModel):
    version_number: int | None = Field(default=None, ge=1)


class AnalysisAcceptedResponse(BaseModel):
    job_id: UUID
    submission_id: UUID
    version_number: int
    status: Literal[
        "queued",
        "processing",
        "completed",
        "partial",
        "failed",
    ]


class AnalysisJobStatusResponse(BaseModel):
    job_id: UUID
    submission_id: UUID
    version_number: int
    status: Literal[
        "queued",
        "processing",
        "completed",
        "partial",
        "failed",
    ]
    attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


class FindingsListResponse(BaseModel):
    submission_id: UUID
    version_number: int
    findings: list[Finding]