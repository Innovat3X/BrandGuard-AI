"""PostgreSQL integration test for the complete analysis worker flow."""

from uuid import uuid4
from unittest.mock import Mock

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
from app.infrastructure.db.repositories.brand_rule_repository import (
    BrandRuleRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)
from app.services.analysis_worker_factory import (
    build_analysis_worker_service,
)


def test_postgres_worker_persists_findings_and_finalises_job(db_session):
    """Exercise real PostgreSQL repositories, pipeline, and worker."""

    suffix = uuid4().hex
    organization = Organization(
        name=f"PostgreSQL integration {suffix}",
    )
    user = User(
        full_name="Integration Test User",
        email=f"{suffix}@example.com",
        password_hash="test-only-password-hash",
    )

    db_session.add_all([organization, user])
    db_session.flush()

    # Create a real submission and immutable version.
    submission_repository = SubmissionRepository(db_session)

    submission = submission_repository.create_submission(
        organization_id=organization.id,
        title="Terminology integration test",
        created_by=user.id,
    )

    original_text = "Our cheap product is available today."

    version = submission_repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text=original_text,
    )

    # Create and approve a real rule so persistence can validate provenance.
    rule_repository = BrandRuleRepository(db_session)

    rule, rule_version = rule_repository.create_rule(
        organization_id=organization.id,
        title="Approved terminology",
        created_by=user.id,
        category="terminology",
        rule_text="forbidden_term: cheap",
        severity="medium",
        description="Integration-test terminology rule",
    )

    rule_version = rule_repository.approve_rule_version(
        organization_id=organization.id,
        rule_id=rule.id,
        version_number=rule_version.version_number,
        approved_by=user.id,
    )

    # Create a real queued analysis job.
    job_repository = AnalysisJobRepository(db_session)

    job = job_repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key=f"postgres-worker-{suffix}",
    )

    queue = Mock()

    # The empty claim list represents a completed extraction that found
    # no claim candidates. Terminology analysis uses the real pipeline.
    worker = build_analysis_worker_service(
        db_session,
        queue,
        claim_extractor=lambda _text: [],
    )

    result = worker.process_job(job.id)

    # Verify committed ORM changes by reloading from PostgreSQL.
    db_session.expire_all()

    saved_job = db_session.scalar(
        select(AnalysisJob).where(AnalysisJob.id == job.id)
    )

    assert saved_job is not None
    assert saved_job.status == "completed"
    assert saved_job.attempts == 1
    assert saved_job.completed_at is not None
    assert saved_job.error_code is None

    saved_findings = list(
        db_session.scalars(
            select(Finding).where(
                Finding.organization_id == organization.id,
                Finding.analysis_job_id == job.id,
                Finding.submission_version_id == version.id,
            )
        ).all()
    )

    assert len(saved_findings) == 1

    finding = saved_findings[0]
    assert finding.category == "terminology"
    assert finding.severity == "medium"
    assert finding.result == "conflict"
    assert finding.source_rule_version_id == rule_version.id
    assert finding.finding_fingerprint
    assert finding.requires_human_review is True

    # Analysis moves the current submission into review, not approval.
    saved_submission = db_session.scalar(
        select(Submission).where(Submission.id == submission.id)
    )

    assert saved_submission is not None
    assert saved_submission.status == "under_review"

    finding_count = db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    )

    assert finding_count == 1
    queue.enqueue_analysis.assert_not_called()
    assert result is not None