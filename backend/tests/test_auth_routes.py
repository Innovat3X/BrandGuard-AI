import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, verify_password
from app.core.settings import get_settings
from app.infrastructure.db import Organization, User
from app.infrastructure.db.repositories.organization_membership_repository import (
    OrganizationMembershipRepository,
)
from app.infrastructure.db.repositories.user_repository import UserRepository
from app.infrastructure.db.session import get_db
from app.main import app

TEST_SECRET = "registration-test-secret-123456789-abcdef"


@pytest.fixture
def client(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    get_settings.cache_clear()

    original_overrides = app.dependency_overrides.copy()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        get_settings.cache_clear()


def registration_payload() -> dict[str, str]:
    return {
        "full_name": "Test Registration User",
        "email": "registration@example.test",
        "password": "registration-test-password",
        "organization_name": "Registration Test Organisation",
    }


def test_register_creates_user_organization_and_admin_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )

    assert response.status_code == 201
    data = response.json()

    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 1800
    assert data["user"]["email"] == "registration@example.test"
    assert data["organization"]["name"] == (
        "Registration Test Organisation"
    )
    assert data["role"] == "admin"

    user = UserRepository(db_session).get_by_email(
        "registration@example.test"
    )

    assert user is not None
    assert user.password_hash != "registration-test-password"
    assert verify_password(
        "registration-test-password",
        user.password_hash,
    )

    membership = OrganizationMembershipRepository(
        db_session
    ).get_membership(
        organization_id=data["organization"]["id"],
        user_id=user.id,
    )

    assert membership is not None
    assert membership.role == "admin"

    claims = decode_access_token(
        token=data["access_token"],
        secret_key=TEST_SECRET,
    )

    assert claims["sub"] == str(user.id)
    assert claims["organization_id"] == data["organization"]["id"]


def test_register_rejects_duplicate_email_without_extra_records(
    client: TestClient,
    db_session: Session,
) -> None:
    first = client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )
    assert first.status_code == 201

    second_payload = registration_payload()
    second_payload["organization_name"] = "Should Not Be Created"

    second = client.post(
        "/api/v1/auth/register",
        json=second_payload,
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"

    user_count = db_session.scalar(
        select(func.count()).select_from(User)
    )
    organization_count = db_session.scalar(
        select(func.count()).select_from(Organization)
    )

    assert user_count == 1
    assert organization_count == 1


def test_register_rolls_back_if_membership_creation_fails(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_membership_creation(self, organization_id, user_id, role):
        raise RuntimeError("simulated membership failure")

    monkeypatch.setattr(
        OrganizationMembershipRepository,
        "create_membership",
        fail_membership_creation,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated membership failure",
    ):
        client.post(
            "/api/v1/auth/register",
            json=registration_payload(),
        )

    assert UserRepository(db_session).get_by_email(
        "registration@example.test"
    ) is None

    organization_count = db_session.scalar(
        select(func.count()).select_from(Organization)
    )
    assert organization_count == 0


def test_register_validates_request_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "",
            "email": "not-an-email",
            "password": "",
            "organization_name": "",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"