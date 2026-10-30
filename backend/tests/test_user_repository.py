
from uuid import uuid4

import pytest

from app.infrastructure.db.repositories.user_repository import (
    UserRepository,
)


def test_create_user_normalizes_identity_fields(db_session):
    repository = UserRepository(db_session)

    user = repository.create_user(
        full_name="  Test User  ",
        email="  Test.User@Example.Test  ",
        password_hash="synthetic-test-hash",
    )

    assert user.id is not None
    assert user.full_name == "Test User"
    assert user.email == "test.user@example.test"
    assert user.is_active is True


def test_get_by_id_returns_existing_user(db_session):
    repository = UserRepository(db_session)

    created = repository.create_user(
        full_name="Test User",
        email="user-id@example.test",
        password_hash="synthetic-test-hash",
    )

    retrieved = repository.get_by_id(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id


def test_get_by_id_returns_none_for_missing_user(db_session):
    repository = UserRepository(db_session)

    assert repository.get_by_id(uuid4()) is None


def test_get_by_email_ignores_case_and_outer_spaces(db_session):
    repository = UserRepository(db_session)

    created = repository.create_user(
        full_name="Test User",
        email="lookup@example.test",
        password_hash="synthetic-test-hash",
    )

    retrieved = repository.get_by_email(
        "  LOOKUP@Example.Test  "
    )

    assert retrieved is not None
    assert retrieved.id == created.id


def test_get_by_email_returns_none_for_missing_user(db_session):
    repository = UserRepository(db_session)

    assert repository.get_by_email(
        "missing@example.test"
    ) is None


def test_set_active_updates_existing_user(db_session):
    repository = UserRepository(db_session)

    user = repository.create_user(
        full_name="Test User",
        email="active@example.test",
        password_hash="synthetic-test-hash",
    )

    updated = repository.set_active(user.id, False)

    assert updated is not None
    assert updated.is_active is False


def test_set_active_returns_none_for_missing_user(db_session):
    repository = UserRepository(db_session)

    assert repository.set_active(uuid4(), False) is None


@pytest.mark.parametrize(
    ("full_name", "email", "password_hash"),
    [
        (" ", "valid@example.test", "synthetic-test-hash"),
        ("Test User", " ", "synthetic-test-hash"),
        ("Test User", "valid@example.test", " "),
    ],
)
def test_create_user_rejects_empty_required_fields(
    db_session,
    full_name,
    email,
    password_hash,
):
    repository = UserRepository(db_session)

    with pytest.raises(ValueError):
        repository.create_user(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
        )
