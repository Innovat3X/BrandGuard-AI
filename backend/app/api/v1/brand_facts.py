"""Organisation-scoped brand fact API."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.auth import AuthenticatedActor, get_current_actor
from app.infrastructure.db import BrandFact, BrandFactVersion
from app.infrastructure.db.session import get_db
from app.schemas.brand_facts import (
    BrandFactResponse,
    BrandFactsListResponse,
    BrandFactVersionResponse,
    CreateBrandFactRequest,
)
from app.services.brand_fact_service import (
    BrandFactConflictError,
    BrandFactNotFoundError,
    BrandFactService,
)

router = APIRouter(prefix="/brand/facts", tags=["brand facts"])


def require_creator_or_admin(actor: AuthenticatedActor) -> None:
    if actor.role not in {"admin", "creator"}:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and creators can create brand facts.",
        )


def require_reviewer_or_admin(actor: AuthenticatedActor) -> None:
    if actor.role not in {"admin", "reviewer"}:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and reviewers can approve brand facts.",
        )


def _version_response(
    version: BrandFactVersion,
) -> BrandFactVersionResponse:
    return BrandFactVersionResponse(
        id=version.id,
        version_number=version.version_number,
        fact_text=version.fact_text,
        source_url=version.source_url,
        fact_key=version.fact_key,
        structured_value=version.structured_value,
        status=version.status,
        effective_from=version.effective_from,
        expires_at=version.expires_at,
        created_by=version.created_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        created_at=version.created_at,
    )


def _fact_response(
    fact: BrandFact,
    versions: list[BrandFactVersion],
) -> BrandFactResponse:
    return BrandFactResponse(
        id=fact.id,
        label=fact.label,
        created_at=fact.created_at,
        versions=[_version_response(version) for version in versions],
    )


@router.get("", response_model=BrandFactsListResponse)
def list_brand_facts(
    limit: int = Query(default=100, ge=1, le=100),
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandFactsListResponse:
    """List facts and their version history for the current organisation."""
    service = BrandFactService(db)

    items = [
        _fact_response(fact, versions)
        for fact, versions in service.list_facts(
            organization_id=actor.organization.id,
            limit=limit,
        )
    ]

    return BrandFactsListResponse(items=items)


@router.post(
    "",
    response_model=BrandFactResponse,
    status_code=201,
)
def create_brand_fact(
    request: CreateBrandFactRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandFactResponse:
    """Create a draft fact with optional structured values."""
    require_creator_or_admin(actor)

    structured_value: dict[str, Any] | None = (
        request.structured_value.model_dump(mode="json")
        if request.structured_value is not None
        else None
    )

    try:
        fact, versions = BrandFactService(db).create_draft_fact(
            organization_id=actor.organization.id,
            created_by=actor.user.id,
            label=request.label,
            fact_text=request.fact_text,
            source_url=request.source_url,
            fact_key=request.fact_key,
            structured_value=structured_value,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return _fact_response(fact, versions)


@router.post(
    "/{fact_id}/approve",
    response_model=BrandFactResponse,
)
def approve_brand_fact(
    fact_id: UUID,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandFactResponse:
    """Approve the latest draft version of a fact."""
    require_reviewer_or_admin(actor)

    try:
        fact, versions = BrandFactService(db).approve_latest_draft(
            organization_id=actor.organization.id,
            fact_id=fact_id,
            approved_by=actor.user.id,
        )
    except BrandFactNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except BrandFactConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return _fact_response(fact, versions)