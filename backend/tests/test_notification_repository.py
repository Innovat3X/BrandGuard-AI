from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.infrastructure.db import Notification, Organization, User
from app.infrastructure.db.repositories.notification_repository import (
    NotificationRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex

    organization = Organization(name=f"Test Organization {suffix}")
    user = User(
        full_name="Notification Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    return organization, user


def test_create_notification(db_session):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    notification = repository.create_notification(
        organization_id=organization.id,
        user_id=user.id,
        notification_type="analysis.completed",
        payload={"job_id": str(uuid4()), "status": "completed"},
    )

    assert notification.id is not None
    assert notification.organization_id == organization.id
    assert notification.user_id == user.id
    assert notification.type == "analysis.completed"
    assert notification.payload["status"] == "completed"
    assert notification.read_at is None


def test_get_notification_is_scoped_to_organization_and_recipient(
    db_session,
):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    notification = repository.create_notification(
        organization_id=organization.id,
        user_id=user.id,
        notification_type="submission.updated",
        payload={"message": "Submission updated"},
    )

    other_organization, other_user = create_org_user(db_session)

    assert repository.get_notification(
        organization_id=other_organization.id,
        user_id=other_user.id,
        notification_id=notification.id,
    ) is None

    assert repository.get_notification(
        organization_id=organization.id,
        user_id=other_user.id,
        notification_id=notification.id,
    ) is None

    assert repository.get_notification(
        organization_id=organization.id,
        user_id=user.id,
        notification_id=notification.id,
    ) is not None


def test_list_for_user_returns_only_recipient_notifications(db_session):
    organization, user = create_org_user(db_session)
    other_organization, other_user = create_org_user(db_session)

    now = datetime.now(timezone.utc)

    older = Notification(
        organization_id=organization.id,
        user_id=user.id,
        type="submission.created",
        payload={"label": "older"},
        created_at=now - timedelta(minutes=2),
    )
    newer = Notification(
        organization_id=organization.id,
        user_id=user.id,
        type="analysis.completed",
        payload={"label": "newer"},
        created_at=now,
    )
    unrelated = Notification(
        organization_id=other_organization.id,
        user_id=other_user.id,
        type="other",
        payload={"label": "unrelated"},
        created_at=now + timedelta(minutes=1),
    )

    db_session.add_all([older, newer, unrelated])
    db_session.flush()

    repository = NotificationRepository(db_session)
    result = repository.list_for_user(
        organization_id=organization.id,
        user_id=user.id,
    )

    assert [item.id for item in result] == [newer.id, older.id]


def test_unread_filter_excludes_read_notifications(db_session):
    organization, user = create_org_user(db_session)
    now = datetime.now(timezone.utc)

    unread = Notification(
        organization_id=organization.id,
        user_id=user.id,
        type="analysis.completed",
        payload={"label": "unread"},
        created_at=now,
    )
    read = Notification(
        organization_id=organization.id,
        user_id=user.id,
        type="submission.updated",
        payload={"label": "read"},
        read_at=now - timedelta(minutes=1),
        created_at=now - timedelta(minutes=2),
    )

    db_session.add_all([unread, read])
    db_session.flush()

    repository = NotificationRepository(db_session)
    result = repository.list_for_user(
        organization_id=organization.id,
        user_id=user.id,
        unread_only=True,
    )

    assert [item.id for item in result] == [unread.id]


def test_mark_as_read_sets_timestamp(db_session):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    notification = repository.create_notification(
        organization_id=organization.id,
        user_id=user.id,
        notification_type="analysis.completed",
        payload={"status": "completed"},
    )

    result = repository.mark_as_read(
        organization_id=organization.id,
        user_id=user.id,
        notification_id=notification.id,
    )

    assert result is not None
    assert result.read_at is not None
    assert result.read_at.tzinfo is not None


def test_mark_as_read_is_idempotent(db_session):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    notification = repository.create_notification(
        organization_id=organization.id,
        user_id=user.id,
        notification_type="submission.updated",
        payload={"status": "updated"},
    )

    first = repository.mark_as_read(
        organization_id=organization.id,
        user_id=user.id,
        notification_id=notification.id,
    )
    assert first is not None
    first_read_at = first.read_at

    second = repository.mark_as_read(
        organization_id=organization.id,
        user_id=user.id,
        notification_id=notification.id,
    )

    assert second is not None
    assert second.read_at == first_read_at


def test_mark_as_read_cannot_access_another_recipient_notification(
    db_session,
):
    organization, user = create_org_user(db_session)
    _, other_user = create_org_user(db_session)

    repository = NotificationRepository(db_session)
    notification = repository.create_notification(
        organization_id=organization.id,
        user_id=user.id,
        notification_type="analysis.completed",
        payload={"status": "completed"},
    )

    result = repository.mark_as_read(
        organization_id=organization.id,
        user_id=other_user.id,
        notification_id=notification.id,
    )

    assert result is None

    db_session.refresh(notification)
    assert notification.read_at is None


@pytest.mark.parametrize("limit", [0, -1])
def test_list_for_user_rejects_invalid_limit(db_session, limit):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    with pytest.raises(ValueError, match="at least 1"):
        repository.list_for_user(
            organization_id=organization.id,
            user_id=user.id,
            limit=limit,
        )


def test_create_notification_rejects_empty_type(db_session):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    with pytest.raises(ValueError, match="must not be empty"):
        repository.create_notification(
            organization_id=organization.id,
            user_id=user.id,
            notification_type=" ",
            payload={},
        )


def test_create_notification_rejects_non_dictionary_payload(db_session):
    organization, user = create_org_user(db_session)
    repository = NotificationRepository(db_session)

    with pytest.raises(ValueError, match="must be a dictionary"):
        repository.create_notification(
            organization_id=organization.id,
            user_id=user.id,
            notification_type="analysis.completed",
            payload=[],  # type: ignore[arg-type]
        )