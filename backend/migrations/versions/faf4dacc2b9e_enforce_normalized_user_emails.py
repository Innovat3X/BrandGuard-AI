"""enforce normalized user emails

Revision ID: faf4dacc2b9e
Revises: acc679f20edb
Create Date: 2026-10-23 00:30:13.238541
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# Revision identifiers, used by Alembic.
revision: str = "faf4dacc2b9e"
down_revision: Union[str, Sequence[str], None] = "acc679f20edb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Normalize existing addresses before enforcing the constraint.
    # If normalization creates duplicate emails, the unique
    # constraint will reject the update and the migration will fail.
    op.execute(
        sa.text(
            "UPDATE users SET email = lower(trim(email))"
        )
    )

    op.create_check_constraint(
        op.f("ck_users_normalized_email"),
        "users",
        "email = lower(trim(email))",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_users_normalized_email"),
        "users",
        type_="check",
    )