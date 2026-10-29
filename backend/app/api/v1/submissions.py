from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.contracts import Finding
from app.api.v1.auth import AuthenticatedActor, get_current_actor
from app.infrastructure.db import AnalysisJob, SubmissionVersion
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.finding_repository import (
    FindingRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)
from app.infrastructure.db.session import get_db
from app.schemas.submissions import (
    AnalysisAcceptedResponse,
    AnalysisJobStatusResponse,
    FindingsListResponse,
    QueueAnalysisRequest,
    SubmissionCreatedResponse,
)
from app.services.submission_analysis_service import (
    AnalysisQueueDispatchError,
    SubmissionAnalysisService,
)
from app.workers.analysis_tasks import CeleryAnalysisJobQueue


router = APIRouter(tags=["submissions"])


def require_creator_or_admin(actor: AuthenticatedActor) -> None:
    if actor.role not in {"admin", "creator"}:
        raise HTTPException(
            status_code=403,
            detail="Only administrators and creators can submit content.",
        )


@router.post(
    "/submissions",
    response_model=SubmissionCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_submission(
    title: str = Form(...),
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> SubmissionCreatedResponse:
    """Create a submission with its immutable first text version."""

    require_creator_or_admin(actor)

    if file is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "File-based submission is not enabled in this prototype "
                "slice. Paste the content as text instead."
            ),
        )

    if text is None or not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Non-empty submission text is required.",
        )

    service = SubmissionAnalysisService(
        db,
        CeleryAnalysisJobQueue(),
    )

    try:
        created = service.create_text_submission(
            organization_id=actor.organization.id,
            actor_id=actor.user.id,
            title=title,
            text=text,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    submission = SubmissionRepository(db).get_submission(
        organization_id=actor.organization.id,
        submission_id=created.submission_id,
    )

    if submission is None:
        raise HTTPException(
            status_code=500,
            detail="The created submission could not be retrieved.",
        )

    return SubmissionCreatedResponse(
        submission_id=created.submission_id,
        version_number=created.version_number,
        status=created.status,
        created_at=submission.created_at,
    )


@router.post(
    "/submissions/{submission_id}/analysis",
    response_model=AnalysisAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def queue_submission_analysis(
    submission_id: UUID,
    request: QueueAnalysisRequest | None = Body(default=None),
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> AnalysisAcceptedResponse:
    """Persist and dispatch an idempotent analysis job."""

    require_creator_or_admin(actor)

    submissions = SubmissionRepository(db)

    submission = submissions.get_submission(
        organization_id=actor.organization.id,
        submission_id=submission_id,
    )

    if submission is None:
        raise HTTPException(
            status_code=404,
            detail="Submission not found.",
        )

    version_number = (
        request.version_number
        if request is not None and request.version_number is not None
        else submission.current_version_number
    )

    requested_checks = (
        request.requested_checks if request is not None else None
    )

    base_idempotency_key = (
        f"submission:{submission_id}:version:{version_number}:analysis:v1"
    )

    if requested_checks is None:
        # Preserve the existing key format for default requests.
        idempotency_key = base_idempotency_key
    else:
        # Canonicalize every supported check so equivalent selections
        # produce the same key regardless of dictionary contents or order.
        check_names = (
            "tone",
            "messaging",
            "terminology",
            "factual_claim",
        )
        checks_key = ",".join(
            f"{check}={str(requested_checks.get(check, False)).lower()}"
            for check in check_names
        )
        idempotency_key = f"{base_idempotency_key}:checks:{checks_key}"
    service = SubmissionAnalysisService(
        db,
        CeleryAnalysisJobQueue(),
    )

    try:
        requested = service.request_analysis(
            organization_id=actor.organization.id,
            submission_id=submission_id,
            version_number=version_number,
            requested_checks=requested_checks,
            idempotency_key=idempotency_key,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail="Submission or requested version not found.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc
    except AnalysisQueueDispatchError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "The analysis job was saved but could not be dispatched. "
                "Retry the same request."
            ),
        ) from exc

    return AnalysisAcceptedResponse(
        job_id=requested.job_id,
        submission_id=requested.submission_id,
        version_number=requested.version_number,
        status=requested.status,
    )


@router.get(
    "/analysis-jobs/{job_id}",
    response_model=AnalysisJobStatusResponse,
)
def get_analysis_job_status(
    job_id: UUID,
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> AnalysisJobStatusResponse:
    """Return status only for a job owned by the actor's organisation."""

    job = AnalysisJobRepository(db).get_analysis_job(
        organization_id=actor.organization.id,
        job_id=job_id,
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Analysis job not found.",
        )

    version = db.scalar(
        select(SubmissionVersion).where(
            SubmissionVersion.organization_id == actor.organization.id,
            SubmissionVersion.id == job.submission_version_id,
        )
    )

    if version is None:
        raise HTTPException(
            status_code=404,
            detail="Submission version for this job was not found.",
        )

    return AnalysisJobStatusResponse(
        job_id=job.id,
        submission_id=version.submission_id,
        version_number=version.version_number,
        status=job.status,
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_code=job.error_code,
        error_message=job.error_message,
    )


@router.get(
    "/submissions/{submission_id}/findings",
    response_model=FindingsListResponse,
)
def get_submission_findings(
    submission_id: UUID,
    version: int = Query(ge=1),
    actor: AuthenticatedActor = Depends(get_current_actor),
    db: Session = Depends(get_db),
) -> FindingsListResponse:
    """Return findings for exactly one immutable submission version."""

    rows = FindingRepository(db).list_for_submission_version(
        organization_id=actor.organization.id,
        submission_id=submission_id,
        version_number=version,
    )

    if rows is None:
        raise HTTPException(
            status_code=404,
            detail="Submission version not found.",
        )

    findings = [
        Finding.model_validate(
            {
                "id": row.id,
                "category": row.category,
                "severity": row.severity,
                "result": row.result,
                "explanation": row.explanation,
                "evidence": row.evidence or {},
                "source_rule_version_id": row.source_rule_version_id,
                "source_fact_version_id": row.source_fact_version_id,
                "location": row.location,
                "suggested_correction": row.suggested_correction,
                "detection_method": row.detection_method,
                "requires_human_review": row.requires_human_review,
            }
        )
        for row in rows
    ]

    return FindingsListResponse(
        submission_id=submission_id,
        version_number=version,
        findings=findings,
    )