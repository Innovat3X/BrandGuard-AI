from enum import Enum
from typing import Annotated, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# Finding categories allowed by the shared contract.
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


class DetectionMethod(str, Enum):
    DETERMINISTIC = "deterministic"
    AI_ASSISTED = "ai_assisted"
    OCR = "ocr"
    VISUAL_CHECK = "visual_check"


# Job lifecycle status and analysis-result status are different.
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


# The kind field determines which location structure is used.
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

    # A result is completed or partial.
    # The worker separately tracks queued, processing and failed.
    status: Literal["completed", "partial"]

    findings: list[Finding]
    summary: AnalysisSummary


def build_summary(findings: list[Finding]) -> AnalysisSummary:
    """Count findings by severity for the response summary."""

    counts = {
        severity: 0
        for severity in Severity
    }

    for finding in findings:
        counts[finding.severity] += 1

    return AnalysisSummary(
        info=counts[Severity.INFO],
        low=counts[Severity.LOW],
        medium=counts[Severity.MEDIUM],
        high=counts[Severity.HIGH],
        total=len(findings),
    )