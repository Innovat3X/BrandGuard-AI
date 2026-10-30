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
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class BrandFactVersion(Base):
    __tablename__ = "brand_fact_versions"

    __table_args__ = (
        UniqueConstraint("fact_id", "version_number"),
        UniqueConstraint(
            "organization_id",
            "id",
            name="uq_brand_fact_versions_organization_id_id",
        ),
        ForeignKeyConstraint(
            ["organization_id", "fact_id"],
            ["brand_facts.organization_id", "brand_facts.id"],
            name="fk_brand_fact_versions_org_fact_brand_facts",
        ),
        CheckConstraint(
            "version_number > 0",
            name="positive_version_number",
        ),
        CheckConstraint(
            "status IN ('draft', 'approved', 'archived')",
            name="valid_status",
        ),
        CheckConstraint(
            """
            (
                fact_key IS NULL
                AND structured_value IS NULL
            )
            OR
            (
                fact_key IS NOT NULL
                AND structured_value IS NOT NULL
            )
            """,
            name="structured_fields_pair",
        ),
        CheckConstraint(
            """
            fact_key IS NULL OR fact_key IN (
                'product_price',
                'discount_percentage',
                'warranty_duration',
                'battery_life_duration',
                'product_weight',
                'product_capacity'
            )
            """,
            name="supported_fact_key",
        ),
        CheckConstraint(
            """
            structured_value IS NULL OR (
                jsonb_typeof(structured_value) = 'object'
                AND structured_value ? 'kind'
                AND structured_value ? 'value'
                AND structured_value ? 'unit'
            )
            """,
            name="structured_value_shape",
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

    fact_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    fact_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_url: Mapped[str | None] = mapped_column(
        String(),
        nullable=True,
    )

    fact_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    # Important: Python None must become SQL NULL, not JSON null.
    structured_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
        index=True,
    )

    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )