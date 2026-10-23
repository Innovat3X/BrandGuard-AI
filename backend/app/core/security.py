from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=30)

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a password before storing it."""
    if not password:
        raise ValueError("Password must not be empty.")

    return _password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    """Check a password against its stored hash."""
    if not password or not stored_hash:
        return False

    try:
        return _password_hash.verify(password, stored_hash)
    except UnknownHashError:
        return False


def create_access_token(
    *,
    subject: str,
    secret_key: str,
    expires_delta: timedelta = DEFAULT_ACCESS_TOKEN_LIFETIME,
) -> str:
    """Create a signed JWT for a user."""
    if not subject.strip():
        raise ValueError("Token subject must not be empty.")

    if not secret_key:
        raise ValueError("JWT secret key is not configured.")

    if expires_delta <= timedelta(0):
        raise ValueError("Token lifetime must be positive.")

    now = datetime.now(timezone.utc)

    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expires_delta,
    }

    return jwt.encode(
        payload,
        secret_key,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(
    *,
    token: str,
    secret_key: str,
) -> dict[str, Any]:
    """Verify a JWT signature and expiry, then return its claims."""
    if not secret_key:
        raise ValueError("JWT secret key is not configured.")

    return jwt.decode(
        token,
        secret_key,
        algorithms=[JWT_ALGORITHM],
    )