"""Add persisted check outcomes to analysis jobs."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e2c6b1478a90"
down_revision: Union[str, Sequence[str], None] = "d1f20a7c9b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "check_outcomes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "analysis_jobs",
        "check_outcomes",
    )