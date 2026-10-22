from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_analysis_jobs_organization_id_id",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            "submission_version_id",
            name="uq_analysis_jobs_org_id_submission_version",
        ),
        ForeignKeyConstraint(
            ["organization_id", "submission_version_id"],
            [
                "submission_versions.organization_id",
                "submission_versions.id",
            ],
            name="fk_analysis_jobs_org_submission_version",
        ),
        CheckConstraint(
            "status IN "
            "('queued', 'processing', 'completed', 'partial', 'failed')",
            name="valid_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="non_negative_attempts",
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

    submission_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    requested_checks: Mapped[
        dict[str, Any] | list[Any] | None
    ] = mapped_column(
        JSONB,
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )