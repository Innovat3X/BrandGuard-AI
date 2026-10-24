from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.infrastructure.db import Organization, User
from app.infrastructure.db.repositories.organization_membership_repository import (
    OrganizationMembershipRepository,
)


def create_org_user(db_session, suffix: str):
    organization = Organization(name=f"Organization {suffix}")
    user = User(
        full_name=f"User {suffix}",
        email=f"{suffix}@example.test",
        password_hash="synthetic-test-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    return organization, user


def test_create_membership(db_session):
    organization, user = create_org_user(db_session, "create")
    repository = OrganizationMembershipRepository(db_session)

    membership = repository.create_membership(
        organization_id=organization.id,
        user_id=user.id,
        role="creator",
    )

    assert membership.id is not None
    assert membership.organization_id == organization.id
    assert membership.user_id == user.id
    assert membership.role == "creator"


def test_get_membership_returns_exact_membership(db_session):
    organization, user = create_org_user(db_session, "lookup")
    repository = OrganizationMembershipRepository(db_session)

    created = repository.create_membership(
        organization.id,
        user.id,
        "reviewer",
    )

    retrieved = repository.get_membership(
        organization.id,
        user.id,
    )

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.role == "reviewer"


def test_membership_lookup_is_organization_scoped(db_session):
    organization_a, user = create_org_user(db_session, "tenant-a")
    organization_b, _ = create_org_user(db_session, "tenant-b")
    repository = OrganizationMembershipRepository(db_session)

    created = repository.create_membership(
        organization_a.id,
        user.id,
        "creator",
    )

    assert repository.get_membership(
        organization_b.id,
        user.id,
    ) is None

    assert repository.get_by_id(
        organization_b.id,
        created.id,
    ) is None


def test_list_for_organization_excludes_other_organizations(db_session):
    organization_a, user_a = create_org_user(db_session, "list-a")
    organization_b, user_b = create_org_user(db_session, "list-b")
    repository = OrganizationMembershipRepository(db_session)

    membership_a = repository.create_membership(
        organization_a.id,
        user_a.id,
        "creator",
    )
    membership_b = repository.create_membership(
        organization_b.id,
        user_b.id,
        "reviewer",
    )

    result = repository.list_for_organization(organization_a.id)

    assert [item.id for item in result] == [membership_a.id]
    assert membership_b.id not in [item.id for item in result]


def test_list_for_user_returns_empty_list_without_memberships(db_session):
    _, user = create_org_user(db_session, "list-user-empty")
    repository = OrganizationMembershipRepository(db_session)

    assert repository.list_for_user(user.id) == []


def test_list_for_user_returns_single_membership_and_role(db_session):
    organization, user = create_org_user(db_session, "list-user-single")
    repository = OrganizationMembershipRepository(db_session)

    membership = repository.create_membership(
        organization.id,
        user.id,
        "reviewer",
    )

    result = repository.list_for_user(user.id)

    assert len(result) == 1
    assert result[0].id == membership.id
    assert result[0].organization_id == organization.id
    assert result[0].user_id == user.id
    assert result[0].role == "reviewer"


def test_list_for_user_returns_all_memberships_for_that_user(db_session):
    organization_a, user = create_org_user(
        db_session,
        "list-user-multiple",
    )
    organization_b, other_user = create_org_user(
        db_session,
        "list-user-other",
    )
    repository = OrganizationMembershipRepository(db_session)

    membership_a = repository.create_membership(
        organization_a.id,
        user.id,
        "creator",
    )
    membership_b = repository.create_membership(
        organization_b.id,
        user.id,
        "admin",
    )

    # This membership must not be returned for the original user.
    repository.create_membership(
        organization_b.id,
        other_user.id,
        "reviewer",
    )

    result = repository.list_for_user(user.id)

    assert {item.id for item in result} == {
        membership_a.id,
        membership_b.id,
    }
    assert {
        item.organization_id: item.role
        for item in result
    } == {
        organization_a.id: "creator",
        organization_b.id: "admin",
    }
    assert all(item.user_id == user.id for item in result)


def test_update_role_changes_existing_membership(db_session):
    organization, user = create_org_user(db_session, "update-role")
    repository = OrganizationMembershipRepository(db_session)

    repository.create_membership(
        organization.id,
        user.id,
        "creator",
    )

    updated = repository.update_role(
        organization.id,
        user.id,
        "reviewer",
    )

    assert updated is not None
    assert updated.role == "reviewer"


def test_update_role_returns_none_for_missing_membership(db_session):
    organization, user = create_org_user(db_session, "missing-role")
    repository = OrganizationMembershipRepository(db_session)

    assert repository.update_role(
        organization.id,
        user.id,
        "reviewer",
    ) is None


@pytest.mark.parametrize("role", ["owner", "member", "", "ADMIN"])
def test_create_membership_rejects_invalid_role(db_session, role):
    organization, user = create_org_user(
        db_session,
        f"invalid-{uuid4().hex}",
    )
    repository = OrganizationMembershipRepository(db_session)

    with pytest.raises(ValueError, match="Unsupported membership role"):
        repository.create_membership(
            organization.id,
            user.id,
            role,
        )


def test_update_role_rejects_invalid_role(db_session):
    organization, user = create_org_user(db_session, "bad-update")
    repository = OrganizationMembershipRepository(db_session)

    with pytest.raises(ValueError, match="Unsupported membership role"):
        repository.update_role(
            organization.id,
            user.id,
            "owner",
        )


def test_duplicate_membership_is_rejected_by_database(db_session):
    organization, user = create_org_user(db_session, "duplicate")
    repository = OrganizationMembershipRepository(db_session)

    repository.create_membership(
        organization.id,
        user.id,
        "creator",
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            repository.create_membership(
                organization.id,
                user.id,
                "reviewer",
            )


def test_list_for_organization_rejects_invalid_limit(db_session):
    organization, _ = create_org_user(db_session, "bad-limit")
    repository = OrganizationMembershipRepository(db_session)

    with pytest.raises(ValueError, match="Limit must be at least 1"):
        repository.list_for_organization(
            organization.id,
            limit=0,
        )