from datetime import datetime, timedelta, timezone

import jwt
import pytest
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

TEST_SECRET = "test-only-secret-for-unit-tests-123456789"


def test_password_is_hashed_and_can_be_verified() -> None:
    password = "correct-test-password"
    stored_hash = hash_password(password)

    assert stored_hash != password
    assert verify_password(password, stored_hash) is True


def test_wrong_password_is_rejected() -> None:
    stored_hash = hash_password("correct-test-password")

    assert verify_password("wrong-password", stored_hash) is False


def test_access_token_contains_subject() -> None:
    token = create_access_token(
        subject="user-123",
        secret_key=TEST_SECRET,
    )

    claims = decode_access_token(
        token=token,
        secret_key=TEST_SECRET,
    )

    assert claims["sub"] == "user-123"
    assert "exp" in claims
    assert "iat" in claims


def test_invalid_token_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(
            token="not-a-valid-token",
            secret_key=TEST_SECRET,
        )


def test_expired_token_is_rejected() -> None:
    expired_token = jwt.encode(
        {
            "sub": "user-123",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        TEST_SECRET,
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(ExpiredSignatureError):
        decode_access_token(
            token=expired_token,
            secret_key=TEST_SECRET,
        )