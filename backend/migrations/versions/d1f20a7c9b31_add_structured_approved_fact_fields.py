"""Add structured fields to approved fact versions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d1f20a7c9b31"
down_revision: Union[str, Sequence[str], None] = "4b71e8d29c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "brand_fact_versions",
        sa.Column(
            "fact_key",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "brand_fact_versions",
        sa.Column(
            "structured_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_brand_fact_versions_fact_key",
        "brand_fact_versions",
        ["fact_key"],
        unique=False,
    )

    op.create_check_constraint(
        "ck_brand_fact_versions_structured_fields_pair",
        "brand_fact_versions",
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
    )

    op.create_check_constraint(
        "ck_brand_fact_versions_supported_fact_key",
        "brand_fact_versions",
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
    )

    op.create_check_constraint(
        "ck_brand_fact_versions_structured_value_shape",
        "brand_fact_versions",
        """
        structured_value IS NULL OR (
            jsonb_typeof(structured_value) = 'object'
            AND structured_value ? 'kind'
            AND structured_value ? 'value'
            AND structured_value ? 'unit'
        )
        """,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_brand_fact_versions_structured_value_shape",
        "brand_fact_versions",
        type_="check",
    )

    op.drop_constraint(
        "ck_brand_fact_versions_supported_fact_key",
        "brand_fact_versions",
        type_="check",
    )

    op.drop_constraint(
        "ck_brand_fact_versions_structured_fields_pair",
        "brand_fact_versions",
        type_="check",
    )

    op.drop_index(
        "ix_brand_fact_versions_fact_key",
        table_name="brand_fact_versions",
    )

    op.drop_column(
        "brand_fact_versions",
        "structured_value",
    )

    op.drop_column(
        "brand_fact_versions",
        "fact_key",
    )