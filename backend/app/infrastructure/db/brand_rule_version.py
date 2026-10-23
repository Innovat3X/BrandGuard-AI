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


class BrandRuleVersion(Base):
    __tablename__ = "brand_rule_versions"

    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "version_number",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_brand_rule_versions_organization_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_id"],
            ["brand_rules.organization_id", "brand_rules.id"],
            name="fk_brand_rule_versions_org_rule_brand_rules",
        ),
        CheckConstraint(
            "version_number > 0",
            name="positive_version_number",
        ),
        CheckConstraint(
            "category IN ('tone', 'terminology', 'messaging', 'other')",
            name="valid_category",
        ),
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high')",
            name="valid_severity",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'archived')",
            name="valid_status",
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

    rule_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    rule_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
    )

    created_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    approved_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )