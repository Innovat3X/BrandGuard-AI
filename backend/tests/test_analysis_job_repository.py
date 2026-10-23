from uuid import uuid4

import pytest
from sqlalchemy import func, select

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


def create_org_user(db_session):
    suffix = uuid4().hex
    organization = Organization(name=f"Test Organization {suffix}")
    user = User(
        full_name="Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    return organization, user


def create_submission_version(db_session, organization, user):
    submissions = SubmissionRepository(db_session)

    submission = submissions.create_submission(
        organization_id=organization.id,
        title="Test submission",
        created_by=user.id,
    )

    version = submissions.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text="Test submission content",
    )

    return submission, version


def create_finding(fingerprint="finding-001"):
    return {
        "category": "tone",
        "severity": "medium",
        "result": "conflict",
        "explanation": (
            "The submitted tone conflicts with the approved rule."
        ),
        "detection_method": "deterministic",
        "requires_human_review": True,
        "finding_fingerprint": fingerprint,
    }


def test_create_or_get_job_is_idempotent(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)
    requested_checks = {"tone": True, "terminology": True}

    first = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-001",
        requested_checks=requested_checks,
    )

    second = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-001",
        requested_checks=requested_checks,
    )

    assert first.id == second.id
    assert first.status == "queued"
    assert first.attempts == 0

    count = db_session.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.organization_id == organization.id
        )
    )

    assert count == 1


def test_idempotency_key_cannot_be_reused_for_another_submission(
    db_session,
):
    organization, user = create_org_user(db_session)

    _, first_version = create_submission_version(
        db_session, organization, user
    )
    _, second_version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=first_version.id,
        idempotency_key="request-002",
    )

    with pytest.raises(ValueError, match="idempotency key"):
        repository.create_or_get_analysis_job(
            organization_id=organization.id,
            submission_version_id=second_version.id,
            idempotency_key="request-002",
        )


def test_job_reads_are_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-003",
    )

    other_organization, _ = create_org_user(db_session)

    assert repository.get_analysis_job(
        organization_id=other_organization.id,
        job_id=job.id,
    ) is None

    assert repository.get_analysis_job(
        organization_id=organization.id,
        job_id=job.id,
    ) is not None


def test_only_one_claim_can_succeed(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-004",
    )

    claimed = repository.claim_queued_job(job.id)

    assert claimed is not None
    assert claimed.status == "processing"
    assert claimed.attempts == 1
    assert claimed.organization_id == organization.id

    second_claim = repository.claim_queued_job(job.id)

    assert second_claim is None


def test_claim_unknown_job_returns_none(db_session):
    repository = AnalysisJobRepository(db_session)

    claimed = repository.claim_queued_job(uuid4())

    assert claimed is None


def test_job_status_update_checks_expected_status(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-005",
    )

    rejected_update = repository.update_job_status(
        organization_id=organization.id,
        job_id=job.id,
        expected_status="processing",
        new_status="completed",
    )

    assert rejected_update is None

    accepted_update = repository.update_job_status(
        organization_id=organization.id,
        job_id=job.id,
        expected_status="queued",
        new_status="processing",
    )

    assert accepted_update is not None
    assert accepted_update.status == "processing"


def test_findings_are_deduplicated_and_job_is_finalized(db_session):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-006",
    )

    claimed = repository.claim_queued_job(job.id)

    assert claimed is not None

    finding = create_finding()

    finalized = repository.persist_findings_and_finish_job(
        organization_id=organization.id,
        job_id=job.id,
        submission_version_id=version.id,
        claimed_attempt=claimed.attempts,
        findings=[finding, finding],
        final_status="completed",
        submission_status="under_review",
    )

    assert finalized is True

    db_session.expire_all()

    saved_job = repository.get_analysis_job(
        organization.id,
        job.id,
    )

    assert saved_job is not None
    assert saved_job.status == "completed"
    assert saved_job.completed_at is not None

    finding_count = db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    )

    assert finding_count == 1

    saved_submission = db_session.scalar(
        select(Submission).where(
            Submission.id == submission.id
        )
    )

    assert saved_submission is not None
    assert saved_submission.status == "under_review"


def test_stale_worker_cannot_persist_findings(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key="request-007",
    )

    claimed = repository.claim_queued_job(job.id)

    assert claimed is not None
    assert claimed.attempts == 1

    # Simulate a newer attempt becoming authoritative.
    claimed.attempts = 2
    db_session.flush()

    finalized = repository.persist_findings_and_finish_job(
        organization_id=organization.id,
        job_id=job.id,
        submission_version_id=version.id,
        claimed_attempt=1,
        findings=[create_finding()],
        final_status="completed",
    )

    assert finalized is False

    finding_count = db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    )

    assert finding_count == 0

    db_session.refresh(claimed)

    assert claimed.status == "processing"


def test_empty_idempotency_key_is_rejected(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_version(
        db_session, organization, user
    )

    repository = AnalysisJobRepository(db_session)

    with pytest.raises(ValueError, match="Idempotency key"):
        repository.create_or_get_analysis_job(
            organization_id=organization.id,
            submission_version_id=version.id,
            idempotency_key="   ",
        )