import pytest
from sqlalchemy import func, select

from app.infrastructure.db import (
    AnalysisJob,
    Finding,
    Organization,
    User,
)
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)


def test_findings_and_job_completion_roll_back_together(db_session):
    organization = Organization(name="Atomicity Test Organization")
    user = User(
        full_name="Atomicity Test User",
        email="atomicity@example.test",
        password_hash="synthetic-test-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    submissions = SubmissionRepository(db_session)

    submission = submissions.create_submission(
        organization_id=organization.id,
        title="Atomicity Test Submission",
        created_by=user.id,
    )

    version = submissions.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        original_text="Synthetic content for rollback testing.",
        sha256="a" * 64,
        created_by=user.id,
    )

    jobs = AnalysisJobRepository(db_session)

    job = jobs.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="atomicity-test-job",
    )

    claimed = jobs.claim_queued_job(job.id)

    assert claimed is not None
    assert claimed.status == "processing"

    finding_data = {
        "category": "tone",
        "severity": "medium",
        "result": "conflict",
        "explanation": "Synthetic finding for rollback verification.",
        "detection_method": "deterministic",
        "requires_human_review": True,
        "finding_fingerprint": "atomicity-test-finding",
    }

    with pytest.raises(RuntimeError, match="force rollback"):
        with db_session.begin_nested():
            result = jobs.persist_findings_and_finish_job(
                organization_id=organization.id,
                job_id=job.id,
                submission_version_id=version.id,
                claimed_attempt=claimed.attempts,
                findings=[finding_data],
                final_status="completed",
            )

            assert result is True

            raise RuntimeError("force rollback")

    db_session.expire_all()

    stored_job = db_session.get(AnalysisJob, job.id)

    finding_count = db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    )

    assert stored_job is not None
    assert stored_job.status == "processing"
    assert stored_job.completed_at is None
    assert finding_count == 0