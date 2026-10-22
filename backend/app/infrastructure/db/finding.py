from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class Finding(Base):
    __tablename__ = "findings"

    __table_args__ = (
        UniqueConstraint(
            "analysis_job_id",
            "finding_fingerprint",
        ),
        ForeignKeyConstraint(
            [
                "organization_id",
                "analysis_job_id",
                "submission_version_id",
            ],
            [
                "analysis_jobs.organization_id",
                "analysis_jobs.id",
                "analysis_jobs.submission_version_id",
            ],
            name="fk_findings_org_job_submission_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_rule_version_id"],
            [
                "brand_rule_versions.organization_id",
                "brand_rule_versions.id",
            ],
            name="fk_findings_org_source_rule_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_fact_version_id"],
            [
                "brand_fact_versions.organization_id",
                "brand_fact_versions.id",
            ],
            name="fk_findings_org_source_fact_version",
        ),
        CheckConstraint(
            "category IN ("
            "'tone', 'terminology', 'messaging', "
            "'factual_claim', 'visual', 'accessibility', 'other'"
            ")",
            name="valid_category",
        ),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high')",
            name="valid_severity",
        ),
        CheckConstraint(
            "result IN ("
            "'conflict', 'unsupported', "
            "'inconclusive', 'check_unavailable'"
            ")",
            name="valid_result",
        ),
        CheckConstraint(
            "detection_method IN ("
            "'deterministic', 'ai_assisted', 'ocr', 'visual_check'"
            ")",
            name="valid_detection_method",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )

    analysis_job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    submission_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    result: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    source_rule_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    source_fact_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        index=True,
    )

    location: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    suggested_correction: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    detection_method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    requires_human_review: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    finding_fingerprint: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )