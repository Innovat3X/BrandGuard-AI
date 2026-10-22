from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class BrandAsset(Base):
    __tablename__ = "brand_assets"

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "created_by"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_brand_assets_org_creator_membership",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            [
                "organization_memberships.organization_id",
                "organization_memberships.user_id",
            ],
            name="fk_brand_assets_org_approver_membership",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="non_negative_size_bytes",
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

    name: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    asset_type: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    storage_key: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    media_type: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        nullable=False,
    )

    checksum_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(),
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
    )

    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    approved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )