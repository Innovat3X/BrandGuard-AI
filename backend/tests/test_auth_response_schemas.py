from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.auth_responses import (
    AuthResponse,
    MeResponse,
    OrganizationResponse,
    UserResponse,
)


@pytest.fixture
def user() -> UserResponse:
    return UserResponse(
        id=uuid4(),
        full_name="Example User",
        email="user@example.com",
    )


@pytest.fixture
def organization() -> OrganizationResponse:
    return OrganizationResponse(
        id=uuid4(),
        name="Example Organisation",
    )


def test_auth_response_contains_token_and_identity(
    user: UserResponse,
    organization: OrganizationResponse,
) -> None:
    response = AuthResponse(
        access_token="test-token",
        expires_in=1800,
        user=user,
        organization=organization,
        role="admin",
    )

    assert response.token_type == "bearer"
    assert response.expires_in == 1800
    assert response.user.email == "user@example.com"
    assert response.role == "admin"


def test_me_response_contains_user_organization_and_role(
    user: UserResponse,
    organization: OrganizationResponse,
) -> None:
    response = MeResponse(
        user=user,
        organization=organization,
        role="creator",
    )

    assert response.user.id == user.id
    assert response.organization.id == organization.id
    assert response.role == "creator"


def test_invalid_role_is_rejected(
    user: UserResponse,
    organization: OrganizationResponse,
) -> None:
    with pytest.raises(ValidationError):
        AuthResponse(
            access_token="test-token",
            expires_in=1800,
            user=user,
            organization=organization,
            role="superuser",
        )


def test_non_positive_expiry_is_rejected(
    user: UserResponse,
    organization: OrganizationResponse,
) -> None:
    with pytest.raises(ValidationError):
        AuthResponse(
            access_token="test-token",
            expires_in=0,
            user=user,
            organization=organization,
            role="admin",
        )