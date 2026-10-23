from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.db import Organization, Submission, User
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)


def create_org_user(
    session: Session,
    suffix: str,
) -> tuple[Organization, User]:
    organization = Organization(
        name=f"Test Organisation {suffix}"
    )
    user = User(
        full_name=f"Test User {suffix}",
        email=f"{suffix}-{uuid4().hex}@example.test",
        password_hash="synthetic-test-hash",
        is_active=True,
    )

    session.add_all([organization, user])
    session.flush()

    return organization, user


def create_initial_submission(
    session: Session,
    repository: SubmissionRepository,
    organization: Organization,
    user: User,
    suffix: str,
) -> tuple[Submission, object]:
    submission = repository.create_submission(
        organization_id=organization.id,
        title=f"Test submission {suffix}",
        created_by=user.id,
    )

    version = repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        original_text=f"Original submitted content {suffix}.",
        sha256="a" * 64,
        created_by=user.id,
    )

    return submission, version


def test_create_submission_and_initial_version(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "initial",
    )
    repository = SubmissionRepository(db_session)

    submission, version = create_initial_submission(
        db_session,
        repository,
        organization,
        user,
        "initial",
    )

    assert submission.organization_id == organization.id
    assert submission.status == "submitted"
    assert submission.current_version_number == 1

    assert version.submission_id == submission.id
    assert version.organization_id == organization.id
    assert version.version_number == 1
    assert version.original_text == "Original submitted content initial."


def test_submission_and_version_reads_are_organization_scoped(
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
    repository = SubmissionRepository(db_session)

    submission, version = create_initial_submission(
        db_session,
        repository,
        organization_a,
        user_a,
        "tenant-a",
    )

    assert (
        repository.get_submission(
            organization_a.id,
            submission.id,
        )
        is not None
    )

    assert (
        repository.get_submission_version(
            organization_a.id,
            submission.id,
            1,
        )
        is not None
    )

    assert (
        repository.get_submission(
            organization_b.id,
            submission.id,
        )
        is None
    )

    assert (
        repository.get_submission_version(
            organization_b.id,
            submission.id,
            version.version_number,
        )
        is None
    )


def test_new_version_preserves_original_and_advances_pointer(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "revision",
    )
    repository = SubmissionRepository(db_session)

    submission, original_version = create_initial_submission(
        db_session,
        repository,
        organization,
        user,
        "revision",
    )

    repository.update_current_version(
        organization.id,
        submission.id,
        1,
    )

    revised_version = repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=2,
        source_type="text",
        original_text="Revised content for version two.",
        sha256="b" * 64,
        created_by=user.id,
    )

    updated_submission = repository.update_current_version(
        organization.id,
        submission.id,
        2,
    )

    db_session.flush()

    stored_original = repository.get_submission_version(
        organization.id,
        submission.id,
        1,
    )
    stored_revision = repository.get_submission_version(
        organization.id,
        submission.id,
        2,
    )

    assert updated_submission.current_version_number == 2

    assert stored_original is not None
    assert stored_original.id == original_version.id
    assert (
        stored_original.original_text
        == "Original submitted content revision."
    )

    assert stored_revision is not None
    assert stored_revision.id == revised_version.id
    assert stored_revision.original_text == (
        "Revised content for version two."
    )


def test_repository_rejects_skipped_version_number(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "version-sequence",
    )
    repository = SubmissionRepository(db_session)

    submission, original_version = create_initial_submission(
        db_session,
        repository,
        organization,
        user,
        "version-sequence",
    )

    with pytest.raises(ValueError, match="Expected submission version"):
        repository.create_submission_version(
            organization_id=organization.id,
            submission_id=submission.id,
            version_number=3,
            source_type="text",
            original_text="Invalid skipped version.",
            sha256="c" * 64,
            created_by=user.id,
        )

    stored_original = repository.get_submission_version(
        organization.id,
        submission.id,
        1,
    )
    skipped_version = repository.get_submission_version(
        organization.id,
        submission.id,
        3,
    )

    assert stored_original is not None
    assert stored_original.id == original_version.id
    assert skipped_version is None


def test_current_version_cannot_move_backwards(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "pointer",
    )
    repository = SubmissionRepository(db_session)

    submission, _ = create_initial_submission(
        db_session,
        repository,
        organization,
        user,
        "pointer",
    )

    repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=2,
        source_type="text",
        original_text="Second version.",
        sha256="d" * 64,
        created_by=user.id,
    )

    repository.update_current_version(
        organization.id,
        submission.id,
        2,
    )

    with pytest.raises(ValueError, match="only advance"):
        repository.update_current_version(
            organization.id,
            submission.id,
            1,
        )

    stored_submission = repository.get_submission(
        organization.id,
        submission.id,
    )

    assert stored_submission is not None
    assert stored_submission.current_version_number == 2


def test_submission_status_update_is_organization_scoped(
    db_session: Session,
) -> None:
    organization_a, user_a = create_org_user(
        db_session,
        "status-a",
    )
    organization_b, _ = create_org_user(
        db_session,
        "status-b",
    )
    repository = SubmissionRepository(db_session)

    submission, _ = create_initial_submission(
        db_session,
        repository,
        organization_a,
        user_a,
        "status",
    )

    result = repository.update_submission_status(
        organization_id=organization_b.id,
        submission_id=submission.id,
        status="processing",
    )

    assert result is None

    stored_submission = repository.get_submission(
        organization_a.id,
        submission.id,
    )

    assert stored_submission is not None
    assert stored_submission.status == "submitted"


def test_submission_and_initial_version_roll_back_together(
    db_session: Session,
) -> None:
    organization, user = create_org_user(
        db_session,
        "rollback-version",
    )
    repository = SubmissionRepository(db_session)

    submission_id = None

    with pytest.raises(RuntimeError, match="force transaction rollback"):
        with db_session.begin_nested():
            submission = repository.create_submission(
                organization_id=organization.id,
                title="Rollback test submission",
                created_by=user.id,
            )
            submission_id = submission.id

            repository.create_submission_version(
                organization_id=organization.id,
                submission_id=submission.id,
                version_number=1,
                source_type="text",
                original_text="Synthetic rollback content.",
                sha256="e" * 64,
                created_by=user.id,
            )

            raise RuntimeError("force transaction rollback")

    assert submission_id is not None

    assert repository.get_submission(
        organization.id,
        submission_id,
    ) is None

    assert repository.get_submission_version(
        organization.id,
        submission_id,
        1,
    ) is None