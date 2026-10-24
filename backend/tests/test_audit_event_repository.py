from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.infrastructure.db import AuditEvent, Organization, User
from app.infrastructure.db.repositories.audit_event_repository import (
    AuditEventRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex

    organization = Organization(name=f"Test Organization {suffix}")
    user = User(
        full_name="Audit Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    return organization, user


def test_create_audit_event(db_session):
    organization, user = create_org_user(db_session)
    repository = AuditEventRepository(db_session)

    event = repository.create_event(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="submission.created",
        entity_type="submission",
        entity_id=uuid4(),
        details={"source": "test"},
    )

    assert event.id is not None
    assert event.organization_id == organization.id
    assert event.actor_user_id == user.id
    assert event.action == "submission.created"
    assert event.entity_type == "submission"
    assert event.details == {"source": "test"}


def test_audit_event_can_have_no_actor_or_entity_id(db_session):
    organization, _ = create_org_user(db_session)
    repository = AuditEventRepository(db_session)

    event = repository.create_event(
        organization_id=organization.id,
        action="system.operation",
        entity_type="system",
    )

    assert event.actor_user_id is None
    assert event.entity_id is None
    assert event.details is None


def test_get_event_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    repository = AuditEventRepository(db_session)

    event = repository.create_event(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="submission.created",
        entity_type="submission",
        entity_id=uuid4(),
    )

    other_organization = Organization(name="Other Organization")
    db_session.add(other_organization)
    db_session.flush()

    assert repository.get_event(
        organization_id=other_organization.id,
        event_id=event.id,
    ) is None

    found = repository.get_event(
        organization_id=organization.id,
        event_id=event.id,
    )
    assert found is not None
    assert found.id == event.id


def test_list_for_entity_filters_and_orders_events(db_session):
    organization, user = create_org_user(db_session)
    repository = AuditEventRepository(db_session)
    entity_id = uuid4()
    now = datetime.now(timezone.utc)

    older = AuditEvent(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="submission.created",
        entity_type="submission",
        entity_id=entity_id,
        created_at=now - timedelta(minutes=2),
    )
    newer = AuditEvent(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="submission.reviewed",
        entity_type="submission",
        entity_id=entity_id,
        created_at=now,
    )
    unrelated = AuditEvent(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="asset.created",
        entity_type="asset",
        entity_id=uuid4(),
        created_at=now - timedelta(minutes=1),
    )

    db_session.add_all([older, newer, unrelated])
    db_session.flush()

    events = repository.list_for_entity(
        organization_id=organization.id,
        entity_type="submission",
        entity_id=entity_id,
    )

    assert [event.id for event in events] == [older.id, newer.id]


def test_list_recent_is_organization_scoped_and_limited(db_session):
    organization, user = create_org_user(db_session)
    repository = AuditEventRepository(db_session)
    now = datetime.now(timezone.utc)

    older = AuditEvent(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="older",
        entity_type="test",
        created_at=now - timedelta(minutes=2),
    )
    newer = AuditEvent(
        organization_id=organization.id,
        actor_user_id=user.id,
        action="newer",
        entity_type="test",
        created_at=now,
    )

    other_organization = Organization(name="Unrelated Organization")
    db_session.add(other_organization)
    db_session.flush()

    unrelated = AuditEvent(
        organization_id=other_organization.id,
        action="other.organization",
        entity_type="test",
        created_at=now + timedelta(minutes=1),
    )

    db_session.add_all([older, newer, unrelated])
    db_session.flush()

    events = repository.list_recent(
        organization_id=organization.id,
        limit=1,
    )

    assert len(events) == 1
    assert events[0].id == newer.id


def test_list_methods_reject_invalid_limit(db_session):
    organization, _ = create_org_user(db_session)
    repository = AuditEventRepository(db_session)

    with pytest.raises(ValueError, match="at least 1"):
        repository.list_recent(organization.id, limit=0)

    with pytest.raises(ValueError, match="at least 1"):
        repository.list_for_entity(
            organization_id=organization.id,
            entity_type="submission",
            entity_id=uuid4(),
            limit=0,
        )


@pytest.mark.parametrize(
    ("action", "entity_type"),
    [
        ("", "submission"),
        ("submission.created", ""),
    ],
)
def test_create_event_rejects_empty_action_or_entity_type(
    db_session, action, entity_type
):
    organization, _ = create_org_user(db_session)
    repository = AuditEventRepository(db_session)

    with pytest.raises(ValueError):
        repository.create_event(
            organization_id=organization.id,
            action=action,
            entity_type=entity_type,
        )