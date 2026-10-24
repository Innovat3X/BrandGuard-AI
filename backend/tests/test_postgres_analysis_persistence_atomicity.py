"""PostgreSQL integration tests for atomic analysis-result persistence."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.db import (
    AnalysisJob,
    Finding,
    Organization,
    Submission,
    User,
)
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)


def make_finding(fingerprint: str, severity: str) -> dict:
    """Create a persistence payload with configurable severity."""

    return {
        "category": "terminology",
        "severity": severity,
        "result": "conflict",
        "explanation": "Integration-test terminology finding.",
        "detection_method": "deterministic",
        "requires_human_review": True,
        "finding_fingerprint": fingerprint,
    }


def test_database_failure_rolls_back_findings_and_finalisation(db_session):
    """A failed second insert must not leave the first finding persisted."""

    suffix = uuid4().hex

    organization = Organization(
        name=f"Atomicity test {suffix}",
    )
    user = User(
        full_name="Atomicity Test User",
        email=f"{suffix}@example.com",
        password_hash="test-only-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    submission_repository = SubmissionRepository(db_session)

    submission = submission_repository.create_submission(
        organization_id=organization.id,
        title="Persistence atomicity test",
        created_by=user.id,
    )

    version = submission_repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text="Test content for atomic persistence.",
    )

    job_repository = AnalysisJobRepository(db_session)

    job = job_repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key=f"atomicity-{suffix}",
    )

    claimed = job_repository.claim_queued_job(job.id)

    assert claimed is not None
    assert claimed.status == "processing"
    assert claimed.attempts == 1

    # Preserve the setup in the fixture's outer transaction. The fixture
    # will still roll back the entire test transaction at teardown.
    db_session.commit()

    # The first finding is valid. The second violates the database
    # severity constraint, forcing PostgreSQL to reject the insert.
    findings = [
        make_finding("valid-finding-first", "medium"),
        make_finding("invalid-finding-second", "critical"),
    ]

    with pytest.raises(IntegrityError):
        job_repository.persist_findings_and_finish_job(
            organization_id=organization.id,
            job_id=job.id,
            submission_version_id=version.id,
            claimed_attempt=claimed.attempts,
            findings=findings,
            final_status="completed",
            submission_status="under_review",
        )

    # Roll back the failed transaction/savepoint before querying again.
    db_session.rollback()
    db_session.expire_all()

    saved_job = job_repository.get_analysis_job(
        organization_id=organization.id,
        job_id=job.id,
    )

    assert saved_job is not None
    assert saved_job.status == "processing"
    assert saved_job.attempts == 1
    assert saved_job.completed_at is None

    persisted_count = db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    )

    assert persisted_count == 0

    saved_submission = db_session.scalar(
        select(Submission).where(
            Submission.organization_id == organization.id,
            Submission.id == submission.id,
        )
    )

    assert saved_submission is not None
    assert saved_submission.status == "submitted"