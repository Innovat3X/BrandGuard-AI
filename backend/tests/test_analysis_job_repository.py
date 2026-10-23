
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
from app.infrastructure.db.repositories.brand_fact_repository import (
    BrandFactRepository,
)
from app.infrastructure.db.repositories.brand_rule_repository import (
    BrandRuleRepository,
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


def create_finding(
    fingerprint="finding-001",
    source_rule_version_id=None,
    source_fact_version_id=None,
):
    finding = {
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

    if source_rule_version_id is not None:
        finding["source_rule_version_id"] = source_rule_version_id

    if source_fact_version_id is not None:
        finding["source_fact_version_id"] = source_fact_version_id

    return finding


def create_rule_version(
    db_session,
    organization,
    user,
    status="draft",
):
    repository = BrandRuleRepository(db_session)

    rule, version = repository.create_rule(
        organization_id=organization.id,
        title="Approved terminology",
        created_by=user.id,
        category="terminology",
        rule_text="Use the approved product name.",
        severity="medium",
        description="Terminology guidance",
    )

    if status == "approved":
        version = repository.approve_rule_version(
            organization_id=organization.id,
            rule_id=rule.id,
            version_number=version.version_number,
            approved_by=user.id,
        )
    elif status == "archived":
        version.status = "archived"
        db_session.flush()

    return rule, version


def create_fact_version(
    db_session,
    organization,
    user,
    status="draft",
):
    repository = BrandFactRepository(db_session)

    fact, version = repository.create_fact(
        organization_id=organization.id,
        label="Official product information",
        fact_text="The product has the approved specification.",
        created_by=user.id,
    )

    if status == "approved":
        version = repository.approve_fact_version(
            organization_id=organization.id,
            fact_id=fact.id,
            version_number=version.version_number,
            approved_by=user.id,
        )
    elif status == "archived":
        version.status = "archived"
        db_session.flush()

    return fact, version


def create_claimed_job(db_session, organization, user, key):
    _, version = create_submission_version(
        db_session, organization, user
    )
    repository = AnalysisJobRepository(db_session)

    job = repository.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key=key,
    )

    claimed = repository.claim_queued_job(job.id)
    assert claimed is not None

    return repository, job, version, claimed


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
        .where(AnalysisJob.organization_id == organization.id)
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
        select(Submission).where(Submission.id == submission.id)
    )

    assert saved_submission is not None
    assert saved_submission.status == "under_review"


def test_stale_worker_cannot_persist_findings(db_session):
    organization, user = create_org_user(db_session)
    repository, job, version, claimed = create_claimed_job(
        db_session, organization, user, "request-007"
    )

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


def test_draft_rule_version_cannot_be_used_by_finding(db_session):
    organization, user = create_org_user(db_session)
    repository, job, version, claimed = create_claimed_job(
        db_session, organization, user, "source-draft-rule"
    )
    _, rule_version = create_rule_version(
        db_session, organization, user, status="draft"
    )

    with pytest.raises(ValueError, match="approved rule version"):
        repository.persist_findings_and_finish_job(
            organization_id=organization.id,
            job_id=job.id,
            submission_version_id=version.id,
            claimed_attempt=claimed.attempts,
            findings=[
                create_finding(
                    source_rule_version_id=rule_version.id
                )
            ],
            final_status="completed",
        )

    assert db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    ) == 0


def test_rule_version_from_another_organization_is_rejected(db_session):
    organization, user = create_org_user(db_session)
    repository, job, version, claimed = create_claimed_job(
        db_session, organization, user, "source-cross-org-rule"
    )

    other_organization, other_user = create_org_user(db_session)
    _, other_rule_version = create_rule_version(
        db_session, other_organization, other_user, status="approved"
    )

    with pytest.raises(ValueError, match="approved rule version"):
        repository.persist_findings_and_finish_job(
            organization_id=organization.id,
            job_id=job.id,
            submission_version_id=version.id,
            claimed_attempt=claimed.attempts,
            findings=[
                create_finding(
                    source_rule_version_id=other_rule_version.id
                )
            ],
            final_status="completed",
        )


def test_draft_fact_version_cannot_be_used_by_finding(db_session):
    organization, user = create_org_user(db_session)
    repository, job, version, claimed = create_claimed_job(
        db_session, organization, user, "source-draft-fact"
    )
    _, fact_version = create_fact_version(
        db_session, organization, user, status="draft"
    )

    with pytest.raises(ValueError, match="approved fact version"):
        repository.persist_findings_and_finish_job(
            organization_id=organization.id,
            job_id=job.id,
            submission_version_id=version.id,
            claimed_attempt=claimed.attempts,
            findings=[
                create_finding(
                    source_fact_version_id=fact_version.id
                )
            ],
            final_status="completed",
        )

    assert db_session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.analysis_job_id == job.id)
    ) == 0


def test_fact_version_from_another_organization_is_rejected(db_session):
    organization, user = create_org_user(db_session)
    repository, job, version, claimed = create_claimed_job(
        db_session, organization, user, "source-cross-org-fact"
    )

    other_organization, other_user = create_org_user(db_session)
    _, other_fact_version = create_fact_version(
        db_session, other_organization, other_user, status="approved"
    )

    with pytest.raises(ValueError, match="approved fact version"):
        repository.persist_findings_and_finish_job(
            organization_id=organization.id,
            job_id=job.id,
            submission_version_id=version.id,
            claimed_attempt=claimed.attempts,
            findings=[
                create_finding(
                    source_fact_version_id=other_fact_version.id
                )
            ],
            final_status="completed",
        )


def test_finding_persists_exact_approved_rule_and_fact_versions(db_session):
    organization, user = create_org_user(db_session)
    repository, job, version, claimed = create_claimed_job(
        db_session, organization, user, "source-approved-versions"
    )

    _, rule_version = create_rule_version(
        db_session, organization, user, status="approved"
    )
    _, fact_version = create_fact_version(
        db_session, organization, user, status="approved"
    )

    finalized = repository.persist_findings_and_finish_job(
        organization_id=organization.id,
        job_id=job.id,
        submission_version_id=version.id,
        claimed_attempt=claimed.attempts,
        findings=[
            create_finding(
                source_rule_version_id=rule_version.id,
                source_fact_version_id=fact_version.id,
            )
        ],
        final_status="completed",
    )

    assert finalized is True

    saved_finding = db_session.scalar(
        select(Finding).where(
            Finding.analysis_job_id == job.id,
            Finding.finding_fingerprint == "finding-001",
        )
    )

    assert saved_finding is not None
    assert saved_finding.source_rule_version_id == rule_version.id
    assert saved_finding.source_fact_version_id == fact_version.id
