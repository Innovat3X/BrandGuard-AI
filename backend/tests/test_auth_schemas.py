import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest


def test_register_normalizes_email_and_names() -> None:
    request = RegisterRequest(
        full_name="  Bhumika  ",
        email="  Bhumika@Example.com ",
        password="test-password",
        organization_name="  Example Org  ",
    )

    assert request.full_name == "Bhumika"
    assert request.email == "bhumika@example.com"
    assert request.organization_name == "Example Org"


def test_login_normalizes_email() -> None:
    request = LoginRequest(
        email=" USER@EXAMPLE.COM ",
        password="test-password",
    )

    assert request.email == "user@example.com"


def test_invalid_email_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(
            email="not-an-email",
            password="test-password",
        )


def test_blank_organization_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            full_name="Example User",
            email="user@example.com",
            password="test-password",
            organization_name="   ",
        )


def test_empty_password_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(
            email="user@example.com",
            password="",
        )