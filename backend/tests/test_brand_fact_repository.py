from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.infrastructure.db import BrandFact, BrandFactVersion, Organization, User
from app.infrastructure.db.repositories.brand_fact_repository import (
    BrandFactRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex

    organization = Organization(name=f"Test Organization {suffix}")
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
        label="Product price",
        fact_text="The approved product price is ₹999.",
        created_by=user.id,
        source_url="https://example.com/source",
    )


def test_create_fact_creates_first_draft_version(db_session):
    organization, user = create_org_user(db_session)

    fact, version = create_fact(db_session, organization, user)

    assert fact.id is not None
    assert fact.organization_id == organization.id
    assert fact.label == "Product price"

    assert version.fact_id == fact.id
    assert version.organization_id == organization.id
    assert version.version_number == 1
    assert version.status == "draft"
    assert version.fact_text == "The approved product price is ₹999."
    assert version.source_url == "https://example.com/source"
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
        repository.get_fact_version(organization.id, fact.id, 1)
        is not None
    )
    assert (
        repository.get_fact_version(other_organization.id, fact.id, 1)
        is None
    )


def test_list_facts_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    fact, _ = create_fact(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    other_fact, _ = create_fact(db_session, other_organization, other_user)

    repository = BrandFactRepository(db_session)

    assert [
        item.id for item in repository.list_facts(organization.id)
    ] == [fact.id]

    assert [
        item.id for item in repository.list_facts(other_organization.id)
    ] == [other_fact.id]


def test_new_fact_version_preserves_original_history(db_session):
    organization, user = create_org_user(db_session)
    fact, version1 = create_fact(db_session, organization, user)

    repository = BrandFactRepository(db_session)

    version2 = repository.create_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        fact_text="The revised approved product price is ₹1099.",
        created_by=user.id,
        source_url="https://example.com/revised-source",
    )

    assert version2.id != version1.id
    assert version2.version_number == 2
    assert version2.status == "draft"

    db_session.refresh(version1)
    assert version1.version_number == 1
    assert version1.fact_text == "The approved product price is ₹999."
    assert version1.status == "draft"

    versions = repository.list_fact_versions(organization.id, fact.id)

    assert versions is not None
    assert [item.version_number for item in versions] == [1, 2]


def test_create_version_rejects_fact_from_another_organization(
    db_session,
):
    organization, user = create_org_user(db_session)
    fact, _ = create_fact(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(LookupError, match="not found"):
        repository.create_fact_version(
            organization_id=other_organization.id,
            fact_id=fact.id,
            fact_text="A different organization's fact.",
            created_by=other_user.id,
        )


def test_list_fact_versions_returns_none_for_wrong_organization(
    db_session,
):
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

    repository = BrandFactRepository(db_session)

    approved = repository.approve_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=version.version_number,
        approved_by=user.id,
    )

    assert approved.status == "approved"
    assert approved.approved_by == user.id
    assert approved.approved_at is not None
    assert approved.approved_at.tzinfo is not None
    assert approved.fact_text == version.fact_text


def test_reapproving_version_preserves_original_approval(db_session):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    repository = BrandFactRepository(db_session)

    first = repository.approve_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=version.version_number,
        approved_by=user.id,
    )
    original_approved_at = first.approved_at
    original_approver = first.approved_by

    second = repository.approve_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=version.version_number,
        approved_by=user.id,
    )

    assert second.status == "approved"
    assert second.approved_at == original_approved_at
    assert second.approved_by == original_approver


def test_archived_fact_version_cannot_be_approved(db_session):
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


def test_approved_fact_listing_excludes_drafts_and_other_organizations(
    db_session,
):
    organization, user = create_org_user(db_session)
    fact, version = create_fact(db_session, organization, user)

    repository = BrandFactRepository(db_session)

    repository.approve_fact_version(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=version.version_number,
        approved_by=user.id,
    )

    other_organization, other_user = create_org_user(db_session)
    other_fact, _ = create_fact(db_session, other_organization, other_user)

    approved = repository.list_approved_fact_versions(organization.id)

    assert len(approved) == 1
    assert approved[0].fact_id == fact.id
    assert approved[0].status == "approved"
    assert all(item.fact_id != other_fact.id for item in approved)


def test_create_fact_rejects_empty_label_or_fact_text(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="label"):
        repository.create_fact(
            organization_id=organization.id,
            label=" ",
            fact_text="Valid fact text",
            created_by=user.id,
        )

    with pytest.raises(ValueError, match="Fact text"):
        repository.create_fact(
            organization_id=organization.id,
            label="Valid label",
            fact_text=" ",
            created_by=user.id,
        )


def test_fact_dates_must_be_timezone_aware(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.create_fact(
            organization_id=organization.id,
            label="Timed fact",
            fact_text="Valid fact text",
            created_by=user.id,
            effective_from=datetime(2026, 1, 1),
        )


def test_fact_expiry_must_follow_effective_date(db_session):
    organization, user = create_org_user(db_session)
    repository = BrandFactRepository(db_session)

    effective_from = datetime(2026, 5, 1, tzinfo=timezone.utc)
    expires_at = effective_from - timedelta(days=1)

    with pytest.raises(ValueError, match="later than effective_from"):
        repository.create_fact(
            organization_id=organization.id,
            label="Timed fact",
            fact_text="Valid fact text",
            created_by=user.id,
            effective_from=effective_from,
            expires_at=expires_at,
        )