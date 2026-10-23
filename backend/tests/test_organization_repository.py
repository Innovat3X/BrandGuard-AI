from uuid import uuid4

import pytest

from app.infrastructure.db.repositories.organization_repository import (
    OrganizationRepository,
)


def test_create_organization_normalizes_name(db_session):
    repository = OrganizationRepository(db_session)

    organization = repository.create_organization(
        "  Test Organization  "
    )

    assert organization.id is not None
    assert organization.name == "Test Organization"
    assert organization.created_at is not None


def test_get_by_id_returns_existing_organization(db_session):
    repository = OrganizationRepository(db_session)

    created = repository.create_organization("Test Organization")

    retrieved = repository.get_by_id(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == "Test Organization"


def test_get_by_id_returns_none_for_missing_organization(db_session):
    repository = OrganizationRepository(db_session)

    assert repository.get_by_id(uuid4()) is None


@pytest.mark.parametrize("name", ["", " ", "   "])
def test_create_organization_rejects_empty_name(
    db_session,
    name,
):
    repository = OrganizationRepository(db_session)

    with pytest.raises(
        ValueError,
        match="Organization name must not be empty",
    ):
        repository.create_organization(name)