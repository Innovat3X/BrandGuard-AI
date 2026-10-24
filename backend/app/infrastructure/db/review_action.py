from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ReviewAction(Base):
    __tablename__ = "review_actions"

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "submission_id"],
            ["submissions.organization_id", "submissions.id"],
            name="fk_review_actions_org_submission",
        ),
        ForeignKeyConstraint(
            ["organization_id", "submission_version_id"],
            [
                "submission_versions.organization_id",
                "submission_versions.id",
            ],
            name="fk_review_actions_org_submission_version",
        ),
        ForeignKeyConstraint(
            ["submission_id", "submission_version_id"],
            [
                "submission_versions.submission_id",
                "submission_versions.id",
            ],
            name="fk_review_actions_submission_version_pair",
        ),
        CheckConstraint(
            "action IN ('approve', 'request_changes', 'reject')",
            name="valid_action",
        ),
        CheckConstraint(
            "action NOT IN ('request_changes', 'reject') "
            "OR (comment IS NOT NULL AND length(trim(comment)) > 0)",
            name="comment_required_for_changes_or_rejection",
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

    submission_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    reviewer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )