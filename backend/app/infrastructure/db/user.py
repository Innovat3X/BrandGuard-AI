from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.infrastructure.db.base import Base


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "email = lower(trim(email))",
            name="normalized_email",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    full_name: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(),
        nullable=False,
        unique=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
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

    @validates("email")
    def normalize_email(
        self,
        key: str,
        value: str,
    ) -> str:
        """Normalize email addresses before ORM persistence."""
        return value.strip().lower()