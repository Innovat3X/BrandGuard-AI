import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.db import (
    AnalysisJob,
    BrandFact,
    BrandFactVersion,
    BrandRule,
    BrandRuleVersion,
    Finding,
    Organization,
    OrganizationMembership,
    ReviewAction,
    Submission,
    SubmissionVersion,
    User,
)


def create_org_user(
    session: Session,
    suffix: str,
) -> tuple[Organization, User]:
    """Create synthetic organisation and user records."""
    organization = Organization(
        name=f"Test Organisation {suffix}"
    )

    user = User(
        full_name=f"Test User {suffix}",
        email=f"{suffix}@example.test",
        password_hash="synthetic-test-hash",
        is_active=True,
    )

    session.add_all([organization, user])
    session.flush()

    return organization, user


def create_submission_version(
    session: Session,
    organization: Organization,
    user: User,
) -> tuple[Submission, SubmissionVersion]:
    """Create a submission and its first immutable version."""
    submission = Submission(
        organization_id=organization.id,
        title="Synthetic test submission",
        status="draft",
        current_version_number=1,
        created_by=user.id,
    )

    session.add(submission)
    session.flush()

    version = SubmissionVersion(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        original_text="Synthetic content for database testing.",
        sha256="a" * 64,
        created_by=user.id,
    )

    session.add(version)
    session.flush()

    return submission, version


def create_analysis_job(
    session: Session,
    organization: Organization,
    version: SubmissionVersion,
    idempotency_key: str,
) -> AnalysisJob:
    """Create a synthetic analysis job for an exact version."""
    job = AnalysisJob(
        organization_id=organization.id,
        submission_version_id=version.id,
        status="queued",
        idempotency_key=idempotency_key,
        attempts=0,
    )

    session.add(job)
    session.flush()

    return job


def test_duplicate_organization_membership_is_rejected(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "membership",
    )

    membership = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role="creator",
    )

    db_session.add(membership)
    db_session.flush()

    duplicate = OrganizationMembership(
        organization_id=organization.id,
        user_id=user.id,
        role="reviewer",
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_duplicate_rule_version_number_is_rejected(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "rule-version",
    )

    rule = BrandRule(
        organization_id=organization.id,
        title="Synthetic brand rule",
        created_by=user.id,
    )

    db_session.add(rule)
    db_session.flush()

    version = BrandRuleVersion(
        organization_id=organization.id,
        rule_id=rule.id,
        version_number=1,
        category="tone",
        rule_text="Use clear and consistent language.",
        severity="low",
        status="draft",
        created_by=user.id,
    )

    db_session.add(version)
    db_session.flush()

    duplicate = BrandRuleVersion(
        organization_id=organization.id,
        rule_id=rule.id,
        version_number=1,
        category="tone",
        rule_text="A duplicate version for testing.",
        severity="low",
        status="draft",
        created_by=user.id,
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_duplicate_fact_version_number_is_rejected(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "fact-version",
    )

    fact = BrandFact(
        organization_id=organization.id,
        label="Synthetic fact",
        created_by=user.id,
    )

    db_session.add(fact)
    db_session.flush()

    version = BrandFactVersion(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=1,
        fact_text="Synthetic fact content.",
        status="draft",
        created_by=user.id,
    )

    db_session.add(version)
    db_session.flush()

    duplicate = BrandFactVersion(
        organization_id=organization.id,
        fact_id=fact.id,
        version_number=1,
        fact_text="Duplicate version for testing.",
        status="draft",
        created_by=user.id,
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_duplicate_submission_version_number_is_rejected(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "submission-version",
    )

    submission, _ = create_submission_version(
        db_session,
        organization,
        user,
    )

    duplicate = SubmissionVersion(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        original_text="Duplicate version test content.",
        sha256="b" * 64,
        created_by=user.id,
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_duplicate_job_idempotency_key_is_rejected(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "job-idempotency",
    )

    _, version = create_submission_version(
        db_session,
        organization,
        user,
    )

    create_analysis_job(
        db_session,
        organization,
        version,
        idempotency_key="synthetic-request-001",
    )

    duplicate = AnalysisJob(
        organization_id=organization.id,
        submission_version_id=version.id,
        status="queued",
        idempotency_key="synthetic-request-001",
        attempts=0,
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_duplicate_finding_fingerprint_in_one_job_is_rejected(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "finding-fingerprint",
    )

    _, version = create_submission_version(
        db_session,
        organization,
        user,
    )

    job = create_analysis_job(
        db_session,
        organization,
        version,
        idempotency_key="synthetic-finding-job-001",
    )

    finding_data = {
        "organization_id": organization.id,
        "analysis_job_id": job.id,
        "submission_version_id": version.id,
        "category": "tone",
        "severity": "low",
        "result": "conflict",
        "explanation": "Synthetic finding for constraint testing.",
        "detection_method": "deterministic",
        "requires_human_review": True,
        "finding_fingerprint": "synthetic-fingerprint-001",
    }

    db_session.add(Finding(**finding_data))
    db_session.flush()

    duplicate = Finding(**finding_data)

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()


def test_analysis_job_cannot_reference_another_orgs_version(
    db_session: Session,
) -> None:
    organization_a, user_a = create_org_user(
        db_session,
        "tenant-a",
    )

    organization_b, _ = create_org_user(
        db_session,
        "tenant-b",
    )

    _, version_a = create_submission_version(
        db_session,
        organization_a,
        user_a,
    )

    cross_tenant_job = AnalysisJob(
        organization_id=organization_b.id,
        submission_version_id=version_a.id,
        status="queued",
        idempotency_key="cross-tenant-job-001",
        attempts=0,
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(cross_tenant_job)
            db_session.flush()


def test_review_action_must_reference_its_exact_submission_version(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "review-version",
    )

    submission_a, version_a = create_submission_version(
        db_session,
        organization,
        user,
    )

    submission_b, _ = create_submission_version(
        db_session,
        organization,
        user,
    )

    incorrect_review = ReviewAction(
        organization_id=organization.id,
        submission_id=submission_b.id,
        submission_version_id=version_a.id,
        reviewer_id=user.id,
        action="approve",
    )

    assert submission_a.id != submission_b.id

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(incorrect_review)
            db_session.flush()


def test_user_email_is_normalized_and_unique(
    db_session: Session,
) -> None:
    user = User(
        full_name="Synthetic Email Test",
        email="  GiRiSh@Example.Test  ",
        password_hash="synthetic-test-hash",
        is_active=True,
    )

    db_session.add(user)
    db_session.flush()

    assert user.email == "girish@example.test"

    duplicate = User(
        full_name="Duplicate Email Test",
        email="GIRISH@example.test",
        password_hash="synthetic-test-hash",
        is_active=True,
    )

    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(duplicate)
            db_session.flush()