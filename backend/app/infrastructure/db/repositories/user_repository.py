
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.user import User


class UserRepository:
    """Database operations for user identity records.

    The application service owns authentication, authorization,
    transaction boundaries, and commits.

    Callers must provide a securely generated password hash,
    never a plaintext password.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_user(
        self,
        full_name: str,
        email: str,
        password_hash: str,
        is_active: bool = True,
    ) -> User:
        """Create a user with a normalized email address."""
        normalized_name = full_name.strip()
        normalized_email = email.strip().lower()

        if not normalized_name:
            raise ValueError("Full name must not be empty.")

        if not normalized_email:
            raise ValueError("Email must not be empty.")

        if not password_hash.strip():
            raise ValueError("Password hash must not be empty.")

        if not isinstance(is_active, bool):
            raise ValueError("is_active must be a boolean.")

        user = User(
            full_name=normalized_name,
            email=normalized_email,
            password_hash=password_hash,
            is_active=is_active,
        )

        self._session.add(user)
        self._session.flush()

        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        """Retrieve a user by primary key."""
        return self._session.scalar(
            select(User).where(User.id == user_id)
        )

    def get_by_email(self, email: str) -> User | None:
        """Retrieve a user using a normalized email address."""
        normalized_email = email.strip().lower()

        if not normalized_email:
            return None

        return self._session.scalar(
            select(User).where(User.email == normalized_email)
        )

    def set_active(
        self,
        user_id: UUID,
        is_active: bool,
    ) -> User | None:
        """Update account-active status.

        Returns None when the user does not exist.
        The caller remains responsible for authorization.
        """
        if not isinstance(is_active, bool):
            raise ValueError("is_active must be a boolean.")

        user = self._session.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
        )

        if user is None:
            return None

        user.is_active = is_active
        self._session.flush()

        return user
