from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.core.settings import get_settings
from app.infrastructure.db.repositories.organization_membership_repository import (
    OrganizationMembershipRepository,
)
from app.infrastructure.db.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.db.repositories.user_repository import UserRepository
from app.infrastructure.db.session import get_db
from app.schemas.auth import RegisterRequest
from app.schemas.auth_responses import (
    AuthResponse,
    OrganizationResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def get_jwt_secret() -> str:
    settings = get_settings()

    secret = (
        settings.jwt_secret_key.get_secret_value()
        if settings.jwt_secret_key is not None
        else ""
    )

    if (
        len(secret) < 32
        or secret == "replace-this-before-authentication"
    ):
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured.",
        )

    return secret


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    settings = get_settings()
    secret = get_jwt_secret()
    lifetime = timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )

    users = UserRepository(db)

    try:
        existing_user = users.get_by_email(request.email)

        if existing_user is not None:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists.",
            )

        # All three records are committed together.
        user = users.create_user(
            full_name=request.full_name,
            email=request.email,
            password_hash=hash_password(request.password),
        )

        organization = OrganizationRepository(db).create_organization(
            request.organization_name
        )

        membership = OrganizationMembershipRepository(db).create_membership(
            organization_id=organization.id,
            user_id=user.id,
            role="admin",
        )

        token = create_access_token(
            subject=str(user.id),
            secret_key=secret,
            expires_delta=lifetime,
            organization_id=str(organization.id),
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except IntegrityError:
        db.rollback()

        # Handles a duplicate email created by a concurrent request.
        if UserRepository(db).get_by_email(request.email) is not None:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists.",
            ) from None

        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Registration could not be completed.",
        ) from None

    except Exception:
        db.rollback()
        raise

    return AuthResponse(
        access_token=token,
        expires_in=int(lifetime.total_seconds()),
        user=UserResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
        ),
        organization=OrganizationResponse(
            id=organization.id,
            name=organization.name,
        ),
        role=membership.role,
    )