
from enum import Enum
from typing import Annotated, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FindingCategory(str, Enum):
    TONE = "tone"
    TERMINOLOGY = "terminology"
    MESSAGING = "messaging"
    FACTUAL_CLAIM = "factual_claim"
    VISUAL = "visual"
    ACCESSIBILITY = "accessibility"
    OTHER = "other"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingResult(str, Enum):
    CONFLICT = "conflict"
    UNSUPPORTED = "unsupported"
    INCONCLUSIVE = "inconclusive"
    CHECK_UNAVAILABLE = "check_unavailable"


class CheckOutcomeStatus(str, Enum):
    """Status of a check, separate from issue findings."""

    SUPPORTED = "supported"
    ISSUES_FOUND = "issues_found"
    INCONCLUSIVE = "inconclusive"
    CHECK_UNAVAILABLE = "check_unavailable"
    DISABLED = "disabled"
    NOT_ASSESSED = "not_assessed"
    COVERAGE_LIMITED = "coverage_limited"


class DetectionMethod(str, Enum):
    DETERMINISTIC = "deterministic"
    AI_ASSISTED = "ai_assisted"
    OCR = "ocr"
    VISUAL_CHECK = "visual_check"


class AnalysisJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class Evidence(BaseModel):
    submitted_text: str | None = None
    approved_reference: str | None = None
    source_name: str | None = None
    source_url: str | None = None


class TextRangeLocation(BaseModel):
    kind: Literal["text_range"]
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    matched_text: str


class ImageBoundingBoxLocation(BaseModel):
    kind: Literal["image_bbox"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


Location = Annotated[
    Union[TextRangeLocation, ImageBoundingBoxLocation],
    Field(discriminator="kind"),
]


class Finding(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    category: FindingCategory
    severity: Severity
    result: FindingResult
    explanation: str

    evidence: Evidence = Field(default_factory=Evidence)

    source_rule_version_id: UUID | None = None
    source_fact_version_id: UUID | None = None
    location: Location | None = None
    suggested_correction: str | None = None

    detection_method: DetectionMethod
    requires_human_review: bool = True


class CheckOutcome(BaseModel):
    """Describes what a check assessed without inventing an issue."""

    category: FindingCategory
    status: CheckOutcomeStatus
    message: str = Field(min_length=1)
    detection_method: DetectionMethod | None = None
    assessed_count: int = Field(default=0, ge=0)
    scope: str | None = None


class AnalysisSummary(BaseModel):
    info: int = Field(default=0, ge=0)
    low: int = Field(default=0, ge=0)
    medium: int = Field(default=0, ge=0)
    high: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class AnalysisResponse(BaseModel):
    job_id: UUID
    submission_id: UUID
    submission_version_id: UUID

    # Job result; lifecycle states are tracked separately by the worker.
    status: Literal["completed", "partial"]

    # Findings represent issues or checks needing attention.
    findings: list[Finding]

    # Outcomes make check coverage and unavailable checks explicit.
    check_outcomes: list[CheckOutcome] = Field(default_factory=list)

    summary: AnalysisSummary


def build_summary(findings: list[Finding]) -> AnalysisSummary:
    """Count issue findings by severity."""

    counts = {severity: 0 for severity in Severity}

    for finding in findings:
        counts[finding.severity] += 1

    return AnalysisSummary(
        info=counts[Severity.INFO],
        low=counts[Severity.LOW],
        medium=counts[Severity.MEDIUM],
        high=counts[Severity.HIGH],
        total=len(findings),
    )
