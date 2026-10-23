
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.infrastructure.db import Organization, User
from app.infrastructure.db.repositories.brand_rule_repository import (
    BrandRuleRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex
    organization = Organization(name=f"Test Organization {suffix}")
    user = User(
        full_name="Brand Rule Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    return organization, user


def create_rule(db_session, organization, user):
    repository = BrandRuleRepository(db_session)

    return repository.create_rule(
        organization_id=organization.id,
        title="Approved terminology",
        created_by=user.id,
        category="terminology",
        rule_text="Use the approved product name.",
        severity="medium",
        description="Terminology guidance",
    )


def approve_version(db_session, organization, rule, version, user):
    repository = BrandRuleRepository(db_session)

    return repository.approve_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        version_number=version.version_number,
        approved_by=user.id,
    )


def test_create_rule_creates_first_draft_version(db_session):
    organization, user = create_org_user(db_session)

    rule, version = create_rule(db_session, organization, user)

    assert rule.id is not None
    assert rule.organization_id == organization.id
    assert rule.title == "Approved terminology"

    assert version.rule_id == rule.id
    assert version.organization_id == organization.id
    assert version.version_number == 1
    assert version.status == "draft"
    assert version.rule_text == "Use the approved product name."
    assert version.created_by == user.id
    assert version.approved_by is None
    assert version.approved_at is None


def test_rule_reads_are_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    rule, version = create_rule(db_session, organization, user)

    other_organization, _ = create_org_user(db_session)
    repository = BrandRuleRepository(db_session)

    assert repository.get_rule(organization.id, rule.id) is not None
    assert repository.get_rule(other_organization.id, rule.id) is None

    assert (
        repository.get_rule_version(
            organization.id, rule.id, version.version_number
        )
        is not None
    )
    assert (
        repository.get_rule_version(
            other_organization.id, rule.id, version.version_number
        )
        is None
    )


def test_list_rules_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    rule, _ = create_rule(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    other_rule, _ = create_rule(
        db_session, other_organization, other_user
    )

    repository = BrandRuleRepository(db_session)

    organization_rules = repository.list_rules(organization.id)
    other_rules = repository.list_rules(other_organization.id)

    assert [item.id for item in organization_rules] == [rule.id]
    assert [item.id for item in other_rules] == [other_rule.id]


def test_new_version_preserves_existing_version(db_session):
    organization, user = create_org_user(db_session)
    rule, version1 = create_rule(db_session, organization, user)

    repository = BrandRuleRepository(db_session)
    version2 = repository.create_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        category="terminology",
        rule_text="Use the revised approved product name.",
        severity="high",
        created_by=user.id,
        description="Revised guidance",
    )

    assert version2.id != version1.id
    assert version2.version_number == 2
    assert version2.status == "draft"

    db_session.refresh(version1)
    assert version1.version_number == 1
    assert version1.rule_text == "Use the approved product name."
    assert version1.status == "draft"

    versions = repository.list_rule_versions(organization.id, rule.id)

    assert versions is not None
    assert [item.version_number for item in versions] == [1, 2]


def test_create_version_rejects_rule_from_another_organization(
    db_session,
):
    organization, user = create_org_user(db_session)
    rule, _ = create_rule(db_session, organization, user)

    other_organization, other_user = create_org_user(db_session)
    repository = BrandRuleRepository(db_session)

    with pytest.raises(LookupError, match="not found"):
        repository.create_rule_version(
            organization_id=other_organization.id,
            rule_id=rule.id,
            category="tone",
            rule_text="Keep the tone consistent.",
            severity="low",
            created_by=other_user.id,
        )


def test_list_rule_versions_returns_none_for_wrong_organization(
    db_session,
):
    organization, user = create_org_user(db_session)
    rule, _ = create_rule(db_session, organization, user)

    other_organization, _ = create_org_user(db_session)
    repository = BrandRuleRepository(db_session)

    assert (
        repository.list_rule_versions(other_organization.id, rule.id)
        is None
    )


def test_approve_draft_version_records_approval_metadata(db_session):
    organization, user = create_org_user(db_session)
    rule, version = create_rule(db_session, organization, user)

    approved = approve_version(
        db_session, organization, rule, version, user
    )

    assert approved.status == "approved"
    assert approved.approved_by == user.id
    assert approved.approved_at is not None
    assert approved.approved_at.tzinfo is not None
    assert approved.rule_text == version.rule_text


def test_reapproving_version_preserves_original_approval(db_session):
    organization, user = create_org_user(db_session)
    rule, version = create_rule(db_session, organization, user)

    first = approve_version(
        db_session, organization, rule, version, user
    )
    original_approved_at = first.approved_at

    second = approve_version(
        db_session, organization, rule, version, user
    )

    assert second.status == "approved"
    assert second.approved_at == original_approved_at
    assert second.approved_by == user.id


def test_archived_version_cannot_be_approved(db_session):
    organization, user = create_org_user(db_session)
    rule, version = create_rule(db_session, organization, user)

    version.status = "archived"
    db_session.flush()

    repository = BrandRuleRepository(db_session)

    with pytest.raises(ValueError, match="Only a draft"):
        repository.approve_rule_version(
            organization_id=organization.id,
            rule_id=rule.id,
            version_number=version.version_number,
            approved_by=user.id,
        )


@pytest.mark.parametrize(
    ("category", "rule_text", "severity"),
    [
        ("invalid", "Valid text", "medium"),
        ("tone", "Valid text", "critical"),
        ("tone", " ", "medium"),
    ],
)
def test_create_rule_rejects_invalid_version_fields(
    db_session, category, rule_text, severity
):
    organization, user = create_org_user(db_session)
    repository = BrandRuleRepository(db_session)

    with pytest.raises(ValueError):
        repository.create_rule(
            organization_id=organization.id,
            title="Test rule",
            created_by=user.id,
            category=category,
            rule_text=rule_text,
            severity=severity,
        )


def test_active_rules_exclude_drafts(db_session):
    organization, user = create_org_user(db_session)
    create_rule(db_session, organization, user)

    repository = BrandRuleRepository(db_session)

    assert repository.list_active_rule_versions(
        organization_id=organization.id,
    ) == []


def test_active_rules_return_only_approved_versions(db_session):
    organization, user = create_org_user(db_session)
    rule, version = create_rule(db_session, organization, user)

    approve_version(db_session, organization, rule, version, user)

    repository = BrandRuleRepository(db_session)
    active = repository.list_active_rule_versions(
        organization_id=organization.id,
    )

    assert len(active) == 1
    assert active[0].rule_id == rule.id
    assert active[0].version_number == 1
    assert active[0].status == "approved"


def test_active_rules_return_latest_approved_version(db_session):
    organization, user = create_org_user(db_session)
    rule, version1 = create_rule(db_session, organization, user)

    approve_version(db_session, organization, rule, version1, user)

    repository = BrandRuleRepository(db_session)
    version2 = repository.create_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        category="terminology",
        rule_text="Use the new approved product name.",
        severity="high",
        created_by=user.id,
    )

    approve_version(db_session, organization, rule, version2, user)

    active = repository.list_active_rule_versions(
        organization_id=organization.id,
    )

    assert len(active) == 1
    assert active[0].rule_id == rule.id
    assert active[0].version_number == 2
    assert active[0].rule_text == "Use the new approved product name."

    # The original approved version remains in history.
    db_session.refresh(version1)
    assert version1.status == "approved"
    assert version1.rule_text == "Use the approved product name."


def test_active_rules_exclude_future_effective_version(db_session):
    organization, user = create_org_user(db_session)
    rule, version1 = create_rule(db_session, organization, user)

    approve_version(db_session, organization, rule, version1, user)

    repository = BrandRuleRepository(db_session)

    version2 = repository.create_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        category="terminology",
        rule_text="Use the future product name.",
        severity="high",
        created_by=user.id,
        effective_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )

    approve_version(db_session, organization, rule, version2, user)

    active = repository.list_active_rule_versions(
        organization_id=organization.id,
        as_of=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )

    assert len(active) == 1
    assert active[0].version_number == 1
    assert active[0].rule_text == "Use the approved product name."


def test_active_rules_include_version_when_effective(db_session):
    organization, user = create_org_user(db_session)
    rule, version1 = create_rule(db_session, organization, user)

    approve_version(db_session, organization, rule, version1, user)

    repository = BrandRuleRepository(db_session)
    effective_from = datetime(2026, 5, 1, tzinfo=timezone.utc)

    version2 = repository.create_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        category="terminology",
        rule_text="Use the future product name.",
        severity="high",
        created_by=user.id,
        effective_from=effective_from,
    )

    approve_version(db_session, organization, rule, version2, user)

    active = repository.list_active_rule_versions(
        organization_id=organization.id,
        as_of=effective_from,
    )

    assert len(active) == 1
    assert active[0].version_number == 2


def test_active_rules_are_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    rule, version = create_rule(db_session, organization, user)

    approve_version(db_session, organization, rule, version, user)

    other_organization, other_user = create_org_user(db_session)
    other_rule, other_version = create_rule(
        db_session, other_organization, other_user
    )

    approve_version(
        db_session, other_organization, other_rule, other_version, other_user
    )

    repository = BrandRuleRepository(db_session)

    own_active = repository.list_active_rule_versions(
        organization_id=organization.id,
    )
    other_active = repository.list_active_rule_versions(
        organization_id=other_organization.id,
    )

    assert len(own_active) == 1
    assert own_active[0].rule_id == rule.id

    assert len(other_active) == 1
    assert other_active[0].rule_id == other_rule.id


def test_active_rules_reject_naive_as_of_datetime(db_session):
    organization, _ = create_org_user(db_session)
    repository = BrandRuleRepository(db_session)

    with pytest.raises(ValueError, match="timezone-aware"):
        repository.list_active_rule_versions(
            organization_id=organization.id,
            as_of=datetime(2026, 4, 1),
        )


def test_active_rules_reject_invalid_limit(db_session):
    organization, _ = create_org_user(db_session)
    repository = BrandRuleRepository(db_session)

    with pytest.raises(ValueError, match="at least 1"):
        repository.list_active_rule_versions(
            organization_id=organization.id,
            limit=0,
        )
