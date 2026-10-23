from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.notification import Notification


class NotificationRepository:
    """Persistence operations for in-app notifications.

    The application service owns transaction boundaries and commits.
    Every read or update is scoped to the organization and recipient.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_notification(
        self,
        organization_id: UUID,
        user_id: UUID,
        notification_type: str,
        payload: dict[str, Any],
    ) -> Notification:
        """Create an in-app notification for a specified recipient.

        The application service must verify that the recipient belongs
        to the organization and is eligible to receive the notification.
        """
        if not notification_type.strip():
            raise ValueError("Notification type must not be empty.")

        if not isinstance(payload, dict):
            raise ValueError("Notification payload must be a dictionary.")

        notification = Notification(
            organization_id=organization_id,
            user_id=user_id,
            type=notification_type,
            payload=payload,
        )

        self._session.add(notification)
        self._session.flush()

        return notification

    def get_notification(
        self,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        """Retrieve a notification belonging to this recipient."""
        statement = select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
            Notification.id == notification_id,
        )

        return self._session.scalar(statement)

    def list_for_user(
        self,
        organization_id: UUID,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """List a recipient's notifications, newest first."""
        if limit < 1:
            raise ValueError("Limit must be at least 1.")

        statement = select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.user_id == user_id,
        )

        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))

        statement = (
            statement
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def mark_as_read(
        self,
        organization_id: UUID,
        user_id: UUID,
        notification_id: UUID,
    ) -> Notification | None:
        """Mark a recipient's notification as read.

        Repeated calls are idempotent: an already-read notification
        retains its original read timestamp.

        Returns None if the notification does not belong to the
        specified organization and recipient.
        """
        statement = (
            select(Notification)
            .where(
                Notification.organization_id == organization_id,
                Notification.user_id == user_id,
                Notification.id == notification_id,
            )
            .with_for_update()
        )

        notification = self._session.scalar(statement)

        if notification is None:
            return None

        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            self._session.flush()

        return notification