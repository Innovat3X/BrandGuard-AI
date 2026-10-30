"""Organisation-scoped API for versioned brand rules."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.auth import AuthenticatedActor, get_current_actor
from app.infrastructure.db import BrandRule, BrandRuleVersion
from app.infrastructure.db.session import get_db
from app.schemas.brand_rules import (
    BrandRuleResponse,
    BrandRuleVersionResponse,
    BrandRulesListResponse,
    CreateBrandRuleRequest,
    CreateBrandRuleVersionRequest,
    UpdateBrandRuleRequest,
)
from app.services.brand_rule_service import (
    BrandRuleConflictError,
    BrandRuleNotFoundError,
    BrandRuleService,
)

router = APIRouter(prefix="/brand/rules", tags=["brand rules"])


def require_creator_or_admin(actor: AuthenticatedActor) -> None:
    if actor.role not in {"admin", "creator"}:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and creators can manage brand rules.",
        )


def require_reviewer_or_admin(actor: AuthenticatedActor) -> None:
    if actor.role not in {"admin", "reviewer"}:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and reviewers can approve brand rules.",
        )


def _version_response(
    version: BrandRuleVersion,
) -> BrandRuleVersionResponse:
    return BrandRuleVersionResponse(
        id=version.id,
        version_number=version.version_number,
        category=version.category,
        description=version.description,
        rule_text=version.rule_text,
        severity=version.severity,
        status=version.status,
        effective_from=version.effective_from,
        created_by=version.created_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        created_at=version.created_at,
    )


def _rule_response(
    rule: BrandRule,
    versions: list[BrandRuleVersion],
) -> BrandRuleResponse:
    return BrandRuleResponse(
        id=rule.id,
        title=rule.title,
        created_at=rule.created_at,
        versions=[_version_response(version) for version in versions],
    )


@router.get("", response_model=BrandRulesListResponse)
def list_brand_rules(
    limit: int = Query(default=100, ge=1, le=100),
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandRulesListResponse:
    """List rules and version history for the current organisation."""
    entries = BrandRuleService(db).list_rules(
        organization_id=actor.organization.id,
        limit=limit,
    )
    return BrandRulesListResponse(
        items=[_rule_response(rule, versions) for rule, versions in entries]
    )


@router.post("", response_model=BrandRuleResponse, status_code=201)
def create_brand_rule(
    request: CreateBrandRuleRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandRuleResponse:
    """Create a draft rule for the authenticated organisation."""
    require_creator_or_admin(actor)
    try:
        rule, versions = BrandRuleService(db).create_draft_rule(
            organization_id=actor.organization.id,
            created_by=actor.user.id,
            title=request.title,
            category=request.category,
            description=request.description,
            rule_text=request.rule_text,
            severity=request.severity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _rule_response(rule, versions)


@router.put("/{rule_id}", response_model=BrandRuleResponse)
def update_brand_rule(
    rule_id: UUID,
    request: UpdateBrandRuleRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandRuleResponse:
    """Update the latest draft version without modifying approved history."""
    require_creator_or_admin(actor)
    try:
        rule, versions = BrandRuleService(db).update_latest_draft(
            organization_id=actor.organization.id,
            rule_id=rule_id,
            title=request.title,
            category=request.category,
            description=request.description,
            rule_text=request.rule_text,
            severity=request.severity,
        )
    except BrandRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrandRuleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _rule_response(rule, versions)


@router.post(
    "/{rule_id}/versions",
    response_model=BrandRuleResponse,
    status_code=201,
)
def create_brand_rule_version(
    rule_id: UUID,
    request: CreateBrandRuleVersionRequest,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandRuleResponse:
    """Append a draft version while keeping previous versions unchanged."""
    require_creator_or_admin(actor)
    try:
        rule, versions = BrandRuleService(db).create_draft_version(
            organization_id=actor.organization.id,
            rule_id=rule_id,
            created_by=actor.user.id,
            category=request.category,
            description=request.description,
            rule_text=request.rule_text,
            severity=request.severity,
            effective_from=request.effective_from,
        )
    except BrandRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrandRuleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _rule_response(rule, versions)


@router.post("/{rule_id}/approve", response_model=BrandRuleResponse)
def approve_brand_rule(
    rule_id: UUID,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> BrandRuleResponse:
    """Approve the latest draft; only reviewers and administrators may do so."""
    require_reviewer_or_admin(actor)
    try:
        rule, versions = BrandRuleService(db).approve_latest_draft(
            organization_id=actor.organization.id,
            rule_id=rule_id,
            approved_by=actor.user.id,
        )
    except BrandRuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrandRuleConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _rule_response(rule, versions)
