from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.core.settings import get_settings
from app.infrastructure.db import Organization, User
from app.infrastructure.db.repositories.organization_membership_repository import (
    OrganizationMembershipRepository,
)
from app.infrastructure.db.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.db.repositories.user_repository import UserRepository
from app.infrastructure.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.auth_responses import (
    AuthResponse,
    MeResponse,
    OrganizationResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


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


@dataclass(frozen=True)
class AuthenticatedActor:
    user: User
    organization: Organization
    role: str


def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> AuthenticatedActor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_access_token(
            token=credentials.credentials,
            secret_key=get_jwt_secret(),
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    subject = claims.get("sub")
    organization_claim = claims.get("organization_id")

    if (
        not isinstance(subject, str)
        or not subject.strip()
        or not isinstance(organization_claim, str)
        or not organization_claim.strip()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(subject)
        organization_id = UUID(organization_claim)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = UserRepository(db).get_by_id(user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    membership = OrganizationMembershipRepository(db).get_membership(
        organization_id=organization_id,
        user_id=user.id,
    )

    if membership is None:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this organization.",
        )

    organization = OrganizationRepository(db).get_by_id(
        organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this organization.",
        )

    return AuthenticatedActor(
        user=user,
        organization=organization,
        role=membership.role,
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
)
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

        if (
            UserRepository(db).get_by_email(request.email)
            is not None
        ):
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


@router.post("/login", response_model=AuthResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """Authenticate a user with one organisation membership."""
    settings = get_settings()
    secret = get_jwt_secret()
    lifetime = timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )

    user = UserRepository(db).get_by_email(request.email)

    # Use a generic response for unknown users and incorrect passwords.
    if (
        user is None
        or not user.is_active
        or not verify_password(
            request.password,
            user.password_hash,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    memberships = OrganizationMembershipRepository(db).list_for_user(
        user.id
    )

    if not memberships:
        raise HTTPException(
            status_code=403,
            detail=(
                "No organisation access is configured for this account."
            ),
        )

    # Do not arbitrarily select an organisation for a multi-organisation
    # user. Full organisation selection must be implemented separately.
    if len(memberships) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "This account belongs to multiple organisations; "
                "organisation selection is not yet available."
            ),
        )

    membership = memberships[0]

    organization = OrganizationRepository(db).get_by_id(
        membership.organization_id
    )

    if organization is None:
        raise HTTPException(
            status_code=403,
            detail=(
                "The organisation associated with this account "
                "is unavailable."
            ),
        )

    token = create_access_token(
        subject=str(user.id),
        secret_key=secret,
        expires_delta=lifetime,
        organization_id=str(organization.id),
    )

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


@me_router.get("/me", response_model=MeResponse)
def get_me(
    actor: AuthenticatedActor = Depends(get_current_actor),
) -> MeResponse:
    return MeResponse(
        user=UserResponse(
            id=actor.user.id,
            full_name=actor.user.full_name,
            email=actor.user.email,
        ),
        organization=OrganizationResponse(
            id=actor.organization.id,
            name=actor.organization.name,
        ),
        role=actor.role,
    )