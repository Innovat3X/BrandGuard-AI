from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.analysis.contracts import CheckOutcome, Finding


AnalysisCheck = Literal[
    "tone",
    "messaging",
    "terminology",
    "factual_claim",
]


class SubmissionCreatedResponse(BaseModel):
    submission_id: UUID
    version_number: int
    status: str
    created_at: datetime


class QueueAnalysisRequest(BaseModel):
    version_number: int | None = Field(default=None, ge=1)

    requested_checks: dict[AnalysisCheck, bool] | None = None

    @model_validator(mode="after")
    def require_at_least_one_check(self) -> "QueueAnalysisRequest":
        if (
            self.requested_checks is not None
            and not any(self.requested_checks.values())
        ):
            raise ValueError(
                "At least one analysis check must be selected."
            )
        return self


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
    check_outcomes: list[CheckOutcome] = Field(default_factory=list)


class FindingsListResponse(BaseModel):
    submission_id: UUID
    version_number: int
    findings: list[Finding]