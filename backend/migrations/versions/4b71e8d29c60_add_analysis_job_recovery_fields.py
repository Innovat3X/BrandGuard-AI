"""add analysis job recovery fields

Revision ID: 4b71e8d29c60
Revises: faf4dacc2b9e
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# Revision identifiers, used by Alembic.
revision: str = "4b71e8d29c60"
down_revision: Union[str, Sequence[str], None] = "faf4dacc2b9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_jobs",
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "dispatch_lease_token",
            sa.String(),
            nullable=True,
        ),
    )

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "dispatch_lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Existing processing jobs have no heartbeat yet. Use their last
    # recorded update as an initial baseline for stale-job recovery.
    op.execute(
        sa.text(
            """
            UPDATE analysis_jobs
            SET heartbeat_at = updated_at
            WHERE status = 'processing'
              AND heartbeat_at IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column(
        "analysis_jobs",
        "dispatch_lease_expires_at",
    )
    op.drop_column(
        "analysis_jobs",
        "dispatch_lease_token",
    )
    op.drop_column(
        "analysis_jobs",
        "heartbeat_at",
    )