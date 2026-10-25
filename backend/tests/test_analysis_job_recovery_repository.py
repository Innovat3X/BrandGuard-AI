from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from app.infrastructure.db import (
    AnalysisJob,
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


def create_job(db_session, key: str):
    suffix = uuid4().hex

    organization = Organization(name=f"Recovery Test Org {suffix}")
    user = User(
        full_name="Recovery Test User",
        email=f"{suffix}@example.com",
        password_hash="test-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    submissions = SubmissionRepository(db_session)

    submission = submissions.create_submission(
        organization_id=organization.id,
        title="Recovery test submission",
        created_by=user.id,
    )

    version = submissions.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text="Recovery test content",
    )

    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key=key,
    )

    return repository, job, submission, version


def test_claim_initializes_heartbeat_and_clears_dispatch_lease(db_session):
    repository, job, _, _ = create_job(
        db_session,
        "recovery-claim-initializes-heartbeat",
    )

    job.dispatch_lease_token = str(uuid4())
    job.dispatch_lease_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db_session.flush()

    claimed = repository.claim_queued_job(job.id)

    assert claimed is not None
    assert claimed.status == "processing"
    assert claimed.attempts == 1
    assert claimed.heartbeat_at is not None
    assert claimed.dispatch_lease_token is None
    assert claimed.dispatch_lease_expires_at is None


def test_heartbeat_requires_current_processing_attempt(db_session):
    repository, job, _, _ = create_job(
        db_session,
        "recovery-heartbeat-fencing",
    )

    claimed = repository.claim_queued_job(job.id)
    assert claimed is not None
    assert claimed.attempts == 1

    assert repository.heartbeat_processing_job(
        job_id=job.id,
        claimed_attempt=1,
    ) is True

    job.attempts = 2
    db_session.flush()

    assert repository.heartbeat_processing_job(
        job_id=job.id,
        claimed_attempt=1,
    ) is False


def test_stale_processing_jobs_are_listed_in_bounded_batch(db_session):
    repository, stale_job, _, _ = create_job(
        db_session,
        "recovery-stale-candidate",
    )
    _, active_job, _, _ = create_job(
        db_session,
        "recovery-active-candidate",
    )

    assert repository.claim_queued_job(stale_job.id) is not None
    assert repository.claim_queued_job(active_job.id) is not None

    stale_job.heartbeat_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    db_session.flush()

    candidates = repository.list_stale_processing_jobs(
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        limit=1,
    )

    candidate_ids = {candidate.id for candidate in candidates}

    assert len(candidates) <= 1
    assert stale_job.id in candidate_ids
    assert active_job.id not in candidate_ids


def test_stale_processing_job_is_requeued_before_attempt_limit(db_session):
    repository, job, _, _ = create_job(
        db_session,
        "recovery-requeue-stale-job",
    )

    claimed = repository.claim_queued_job(job.id)
    assert claimed is not None

    job.heartbeat_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    job.dispatch_lease_token = str(uuid4())
    job.dispatch_lease_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db_session.flush()

    recovered = repository.recover_stale_processing_job(
        job_id=job.id,
        expected_attempt=claimed.attempts,
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        max_attempts=3,
    )

    assert recovered is True

    db_session.refresh(job)

    assert job.status == "queued"
    assert job.completed_at is None
    assert job.error_code == "WORKER_HEARTBEAT_TIMEOUT"
    assert job.heartbeat_at is None
    assert job.dispatch_lease_token is None
    assert job.dispatch_lease_expires_at is None


def test_recovery_rejects_recent_heartbeat(db_session):
    repository, job, _, _ = create_job(
        db_session,
        "recovery-reject-recent-heartbeat",
    )

    claimed = repository.claim_queued_job(job.id)
    assert claimed is not None

    recovered = repository.recover_stale_processing_job(
        job_id=job.id,
        expected_attempt=claimed.attempts,
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        max_attempts=3,
    )

    assert recovered is False

    db_session.refresh(job)
    assert job.status == "processing"
    assert job.attempts == 1


def test_recovery_rejects_wrong_attempt(db_session):
    repository, job, _, _ = create_job(
        db_session,
        "recovery-reject-wrong-attempt",
    )

    claimed = repository.claim_queued_job(job.id)
    assert claimed is not None

    job.heartbeat_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    db_session.flush()

    recovered = repository.recover_stale_processing_job(
        job_id=job.id,
        expected_attempt=claimed.attempts + 1,
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        max_attempts=3,
    )

    assert recovered is False

    db_session.refresh(job)
    assert job.status == "processing"
    assert job.attempts == 1


def test_exhausted_stale_job_fails_and_updates_current_submission(db_session):
    repository, job, submission, version = create_job(
        db_session,
        "recovery-exhausted-job",
    )

    claimed = repository.claim_queued_job(job.id)
    assert claimed is not None

    job.heartbeat_at = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    )
    db_session.flush()

    recovered = repository.recover_stale_processing_job(
        job_id=job.id,
        expected_attempt=claimed.attempts,
        stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
        max_attempts=1,
    )

    assert recovered is True

    db_session.refresh(job)
    saved_submission = db_session.scalar(
        select(Submission).where(Submission.id == submission.id)
    )

    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.error_code == "WORKER_HEARTBEAT_TIMEOUT"
    assert saved_submission is not None
    assert saved_submission.status == "failed_needs_attention"
    assert version.version_number == saved_submission.current_version_number


def test_dispatch_lease_is_exclusive_and_owner_only_can_release(db_session):
    repository, job, _, _ = create_job(
        db_session,
        "recovery-dispatch-lease",
    )

    owner_token = uuid4()
    other_token = uuid4()
    lease_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    assert repository.acquire_dispatch_lease(
        job_id=job.id,
        lease_token=owner_token,
        lease_expires_at=lease_expiry,
    ) is True

    assert repository.acquire_dispatch_lease(
        job_id=job.id,
        lease_token=other_token,
        lease_expires_at=lease_expiry,
    ) is False

    db_session.refresh(job)
    assert job.dispatch_lease_token == str(owner_token)

    assert repository.release_dispatch_lease(
        job_id=job.id,
        lease_token=other_token,
    ) is False

    assert repository.release_dispatch_lease(
        job_id=job.id,
        lease_token=owner_token,
    ) is True

    db_session.refresh(job)
    assert job.dispatch_lease_token is None
    assert job.dispatch_lease_expires_at is None


def test_queued_recovery_listing_excludes_active_dispatch_lease(db_session):
    repository, available_job, _, _ = create_job(
        db_session,
        "recovery-queued-without-lease",
    )
    _, leased_job, _, _ = create_job(
        db_session,
        "recovery-queued-with-active-lease",
    )

    lease_expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    assert repository.acquire_dispatch_lease(
        job_id=leased_job.id,
        lease_token=uuid4(),
        lease_expires_at=lease_expiry,
    ) is True

    candidates = repository.list_queued_jobs_for_recovery(limit=100)
    candidate_ids = {candidate.id for candidate in candidates}

    assert available_job.id in candidate_ids
    assert leased_job.id not in candidate_ids