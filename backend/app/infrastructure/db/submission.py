from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class SubmissionVersion(Base):
    __tablename__ = "submission_versions"

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "version_number",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_submission_versions_organization_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "submission_id"],
            ["submissions.organization_id", "submissions.id"],
            name="fk_submission_versions_org_submission_submissions",
        ),
        CheckConstraint(
            "version_number > 0",
            name="positive_version_number",
        ),
        CheckConstraint(
            "source_type IN ('text', 'file')",
            name="valid_source_type",
        ),
        CheckConstraint(
            "("
            "source_type = 'text' AND original_text IS NOT NULL"
            ") OR ("
            "source_type = 'file' AND storage_key IS NOT NULL"
            ")",
            name="source_content_consistent",
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

    submission_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    original_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    storage_key: Mapped[str | None] = mapped_column(
        String(),
        nullable=True,
    )

    original_filename: Mapped[str | None] = mapped_column(
        String(),
        nullable=True,
    )

    media_type: Mapped[str | None] = mapped_column(
        String(),
        nullable=True,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )