from uuid import uuid4

from sqlalchemy import select

from app.infrastructure.db import (
    Finding,
    Organization,
    SubmissionVersion,
    User,
)
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.finding_repository import (
    FindingRepository,
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


def create_submission_and_version(db_session, organization, user):
    repository = SubmissionRepository(db_session)

    submission = repository.create_submission(
        organization_id=organization.id,
        title="Test submission",
        created_by=user.id,
    )

    version = repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text="Original submission text",
    )

    return submission, version


def persist_test_finding(db_session, organization, version, fingerprint):
    jobs = AnalysisJobRepository(db_session)

    job = jobs.create_or_get_analysis_job(
        organization_id=organization.id,
        submission_version_id=version.id,
        idempotency_key=f"test-{uuid4().hex}",
    )

    claimed = jobs.claim_queued_job(job.id)
    assert claimed is not None

    success = jobs.persist_findings_and_finish_job(
        organization_id=organization.id,
        job_id=job.id,
        submission_version_id=version.id,
        claimed_attempt=claimed.attempts,
        findings=[
            {
                "category": "tone",
                "severity": "medium",
                "result": "conflict",
                "explanation": "Test finding for repository verification.",
                "detection_method": "deterministic",
                "requires_human_review": True,
                "finding_fingerprint": fingerprint,
            }
        ],
        final_status="completed",
    )
    assert success is True

    return db_session.scalar(
        select(Finding).where(
            Finding.analysis_job_id == job.id,
            Finding.finding_fingerprint == fingerprint,
        )
    )


def test_findings_are_isolated_by_submission_version(db_session):
    organization, user = create_org_user(db_session)
    submission, version1 = create_submission_and_version(
        db_session, organization, user
    )

    submissions = SubmissionRepository(db_session)

    version2 = submissions.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=2,
        source_type="text",
        sha256="b" * 64,
        created_by=user.id,
        original_text="Revised submission text",
    )
    submissions.update_current_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=2,
    )

    finding1 = persist_test_finding(
        db_session, organization, version1, "finding-version-1"
    )
    finding2 = persist_test_finding(
        db_session, organization, version2, "finding-version-2"
    )

    repository = FindingRepository(db_session)

    version1_findings = repository.list_for_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
    )
    version2_findings = repository.list_for_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=2,
    )

    assert version1_findings is not None
    assert version2_findings is not None
    assert [item.id for item in version1_findings] == [finding1.id]
    assert [item.id for item in version2_findings] == [finding2.id]


def test_existing_version_without_findings_returns_empty_list(db_session):
    organization, user = create_org_user(db_session)
    submission, _ = create_submission_and_version(
        db_session, organization, user
    )

    repository = FindingRepository(db_session)

    result = repository.list_for_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
    )

    assert result == []


def test_missing_version_returns_none(db_session):
    organization, user = create_org_user(db_session)
    submission, _ = create_submission_and_version(
        db_session, organization, user
    )

    repository = FindingRepository(db_session)

    result = repository.list_for_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=99,
    )

    assert result is None


def test_findings_are_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_and_version(
        db_session, organization, user
    )

    finding = persist_test_finding(
        db_session, organization, version, "organization-scoped-finding"
    )

    other_organization = Organization(name="Unrelated Organization")
    db_session.add(other_organization)
    db_session.flush()

    repository = FindingRepository(db_session)

    assert repository.get_finding(
        organization_id=other_organization.id,
        finding_id=finding.id,
    ) is None

    assert repository.list_for_submission_version(
        organization_id=other_organization.id,
        submission_id=version.submission_id,
        version_number=1,
    ) is None


def test_get_finding_returns_record_within_organization(db_session):
    organization, user = create_org_user(db_session)
    _, version = create_submission_and_version(
        db_session, organization, user
    )

    finding = persist_test_finding(
        db_session, organization, version, "lookup-finding"
    )

    repository = FindingRepository(db_session)

    result = repository.get_finding(
        organization_id=organization.id,
        finding_id=finding.id,
    )

    assert result is not None
    assert result.id == finding.id
    assert result.submission_version_id == version.id