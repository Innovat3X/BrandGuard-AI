
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.infrastructure.db import Organization, User
from app.infrastructure.db.repositories.brand_fact_repository import (
    BrandFactRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex
    organization = Organization(name=f"Fact Test Organization {suffix}")
    user = User(
        full_name="Brand Fact Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )
    db_session.add_all([organization, user])
    db_session.flush()
    return organization, user


def create_fact(db_session, organization, user):
    repository = BrandFactRepository(db_session)
    return repository.create_fact(
        organization_id=organization.id,
        label="Official product name",
        fact_text="The approved product name is FreshTag.",
        created_by=user.id,
        source_url="https://example.com/product",
    )


def approve_version(db_session, organization, fact, version, user):
    repository = BrandFactRepository(db_session)
    return repository.approve_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=version.version_number,
        approved_by=user.id,
    )


def create_version(
    db_session,
    organization,
    fact,
    user,
    fact_text,
    effective_from=None,
    expires_at=None,
):
    repository = BrandFactRepository(db_session)
    return repository.create_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        fact_text=fact_text,
        created_by=user.id,
        effective_from=effective_from,
        expires_at=expires_at,
    )


def test_create_fact_creates_first_draft_version(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    assert fact.id is not None
    assert fact.organization_id == organization.id
    assert fact.label == "Official product name"
    assert version.fact_id == fact.id
    assert version.organization_id == organization.id
    assert version.version_number == 1
    assert version.status == "draft"
    assert version.fact_text == "The approved product name is FreshTag."
    assert version.source_url == "https://example.com/product"
    assert version.created_by == user.id
    assert version.approved_by is None
    assert version.approved_at is None


def test_fact_reads_are_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)
    other_organization, _ = create_org_user(db_session)

    repository = BrandFactRepository(db_session)

    assert repository.get_fact(organization.id, fact.id) is not None
    assert repository.get_fact(other_organization.id, fact.id) is None

    assert (
        repository.get_fact_version(
            organization.id, fact.id, version.version_number
        )
        is not None
    )
    assert (
        repository.get_fact_version(
            other_organization.id, fact.id, version.version_number
        )
        is None
    )


def test_list_facts_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    fact, _ = create_fact(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    other_fact, _ = create_fact(
        db_session, other_organization, other_user
    )

    repository = BrandFactRepository(db_session)

    own_facts = repository.list_facts(organization.id)
    other_facts = repository.list_facts(other_organization.id)

    assert [item.id for item in own_facts] == [fact.id]
    assert [item.id for item in other_facts] == [other_fact.id]


def test_new_version_preserves_existing_version(db_session):
    organization, user = create_org_user(db_session)
    fact, version1 = create_fact(db_session, organization, user)

    version2 = create_version(
        db_session,
        organization,
        fact,
        user,
        "The approved product name is FreshTag Tracker.",
    )

    assert version2.id != version1.id
    assert version2.version_number == 2
    assert version2.status == "draft"

    db_session.refresh(version1)
    assert version1.version_number == 1
    assert version1.fact_text == "The approved product name is FreshTag."
    assert version1.status == "draft"

    repository = BrandFactRepository(db_session)
    versions = repository.list_fact_versions(organization.id, fact.id)

    assert versions is not None
    assert [item.version_number for item in versions] == [1, 2]


def test_create_version_rejects_fact_from_another_organization(db_session):
    organization, user = create_org_user(db_session)
    fact, _ = create_fact(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(LookupError, match="not found"):
        repository.create_fact_version(
            organization_id=other_organization.id,
            fact_id=fact.id,
            fact_text="A fact from another organization.",
            created_by=other_user.id,
        )


def test_list_fact_versions_returns_none_for_wrong_organization(db_session):
    organization, user = create_org_user(db_session)
    fact, _ = create_fact(db_session, organization, user)
    other_organization, _ = create_org_user(db_session)

    repository = BrandFactRepository(db_session)

    assert (
        repository.list_fact_versions(other_organization.id, fact.id)
        is None
    )


def test_approve_draft_version_records_approval_metadata(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    approved = approve_version(
        db_session, organization, fact, version, user
    )

    assert approved.status == "approved"
    assert approved.approved_by == user.id
    assert approved.approved_at is not None
    assert approved.approved_at.tzinfo is not None
    assert approved.fact_text == version.fact_text


def test_reapproving_version_preserves_original_approval(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    first = approve_version(
        db_session, organization, fact, version, user
    )
    original_approved_at = first.approved_at

    second = approve_version(
        db_session, organization, fact, version, user
    )

    assert second.status == "approved"
    assert second.approved_at == original_approved_at
    assert second.approved_by == user.id


def test_archived_version_cannot_be_approved(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    version.status = "archived"
    db_session.flush()

    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="Only a draft"):
        repository.approve_fact_version(
            organization_id=organization.id,
            fact_id=fact.id,
            version_number=version.version_number,
            approved_by=user.id,
        )


def test_create_fact_rejects_empty_label(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="label"):
        repository.create_fact(
            organization_id=organization.id,
            label=" ",
            fact_text="A valid fact.",
            created_by=user.id,
        )


def test_create_fact_rejects_empty_fact_text(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="Fact text"):
        repository.create_fact(
            organization_id=organization.id,
            label="Product name",
            fact_text=" ",
            created_by=user.id,
        )


def test_create_version_rejects_empty_fact_text(db_session):
    organization, user = create_org_user(db_session)
    fact, _ = create_fact(db_session, organization, user)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="Fact text"):
        repository.create_fact_version(
            organization_id=organization.id,
            fact_id=fact.id,
            fact_text=" ",
            created_by=user.id,
        )


def test_create_fact_rejects_naive_effective_date(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.create_fact(
            organization_id=organization.id,
            label="Product name",
            fact_text="A valid fact.",
            created_by=user.id,
            effective_from=datetime(2026, 4, 1),
        )


def test_create_fact_rejects_expiry_before_effective_date(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="later than effective_from"):
        repository.create_fact(
            organization_id=organization.id,
            label="Product name",
            fact_text="A valid fact.",
            created_by=user.id,
            effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
            expires_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )


def test_active_facts_exclude_drafts(db_session):
    organization, user = create_org_user(db_session)
    create_fact(db_session, organization, user)

    repository = BrandFactRepository(db_session)

    assert (
        repository.list_active_fact_versions(
            organization_id=organization.id
        )
        == []
    )


def test_active_facts_return_approved_versions(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)
    approve_version(db_session, organization, fact, version, user)

    repository = BrandFactRepository(db_session)
    active = repository.list_active_fact_versions(
        organization_id=organization.id
    )

    assert len(active) == 1
    assert active[0].fact_id == fact.id
    assert active[0].version_number == 1
    assert active[0].status == "approved"


def test_active_facts_return_latest_approved_version(db_session):
    organization, user = create_org_user(db_session)
    fact, version1 = create_fact(db_session, organization, user)
    approve_version(db_session, organization, fact, version1, user)

    version2 = create_version(
        db_session,
        organization,
        fact,
        user,
        "The approved product name is FreshTag Tracker.",
    )
    approve_version(db_session, organization, fact, version2, user)

    repository = BrandFactRepository(db_session)
    active = repository.list_active_fact_versions(
        organization_id=organization.id
    )

    assert len(active) == 1
    assert active[0].fact_id == fact.id
    assert active[0].version_number == 2
    assert active[0].fact_text == (
        "The approved product name is FreshTag Tracker."
    )

    db_session.refresh(version1)
    assert version1.status == "approved"
    assert version1.fact_text == "The approved product name is FreshTag."


def test_active_facts_exclude_future_effective_version(db_session):
    organization, user = create_org_user(db_session)
    fact, version1 = create_fact(db_session, organization, user)
    approve_version(db_session, organization, fact, version1, user)

    version2 = create_version(
        db_session,
        organization,
        fact,
        user,
        "The future approved product name is FreshTag Next.",
        effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    approve_version(db_session, organization, fact, version2, user)

    repository = BrandFactRepository(db_session)
    active = repository.list_active_fact_versions(
        organization_id=organization.id,
        as_of=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )

    assert len(active) == 1
    assert active[0].version_number == 1
    assert active[0].fact_text == "The approved product name is FreshTag."


def test_active_facts_include_version_at_effective_time(db_session):
    organization, user = create_org_user(db_session)
    fact, version1 = create_fact(db_session, organization, user)
    approve_version(db_session, organization, fact, version1, user)

    effective_from = datetime(2026, 5, 1, tzinfo=timezone.utc)
    version2 = create_version(
        db_session,
        organization,
        fact,
        user,
        "The new approved product name is FreshTag Next.",
        effective_from=effective_from,
    )
    approve_version(db_session, organization, fact, version2, user)

    repository = BrandFactRepository(db_session)
    active = repository.list_active_fact_versions(
        organization_id=organization.id,
        as_of=effective_from,
    )

    assert len(active) == 1
    assert active[0].version_number == 2


def test_active_facts_exclude_expired_version(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    version.effective_from = datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )
    version.expires_at = datetime(
        2026, 3, 1, tzinfo=timezone.utc
    )
    db_session.flush()

    approve_version(db_session, organization, fact, version, user)

    repository = BrandFactRepository(db_session)
    active = repository.list_active_fact_versions(
        organization_id=organization.id,
        as_of=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )

    assert active == []


def test_active_facts_exclude_archived_versions(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    version.status = "archived"
    db_session.flush()

    repository = BrandFactRepository(db_session)
    active = repository.list_active_fact_versions(
        organization_id=organization.id,
        as_of=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )

    assert active == []


def test_active_facts_are_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)
    approve_version(db_session, organization, fact, version, user)

    other_organization, other_user = create_org_user(db_session)
    other_fact, other_version = create_fact(
        db_session, other_organization, other_user
    )
    approve_version(
        db_session,
        other_organization,
        other_fact,
        other_version,
        other_user,
    )

    repository = BrandFactRepository(db_session)

    own_active = repository.list_active_fact_versions(
        organization_id=organization.id
    )
    other_active = repository.list_active_fact_versions(
        organization_id=other_organization.id
    )

    assert len(own_active) == 1
    assert own_active[0].fact_id == fact.id

    assert len(other_active) == 1
    assert other_active[0].fact_id == other_fact.id


def test_active_facts_reject_naive_as_of_datetime(db_session):
    organization, _ = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.list_active_fact_versions(
            organization_id=organization.id,
            as_of=datetime(2026, 4, 1),
        )


def test_active_facts_reject_invalid_limit(db_session):
    organization, _ = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="at least 1"):
        repository.list_active_fact_versions(
            organization_id=organization.id,
            limit=0,
        )


def test_approved_fact_listing_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)
    approve_version(db_session, organization, fact, version, user)

    other_organization, _ = create_org_user(db_session)

    repository = BrandFactRepository(db_session)

    own_approved = repository.list_approved_fact_versions(
        organization_id=organization.id
    )
    other_approved = repository.list_approved_fact_versions(
        organization_id=other_organization.id
    )

    assert len(own_approved) == 1
    assert own_approved[0].fact_id == fact.id
    assert other_approved == []
