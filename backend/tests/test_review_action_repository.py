from uuid import uuid4

import pytest
from sqlalchemy import select

from app.infrastructure.db import (
    Organization,
    ReviewAction,
    Submission,
    User,
)
from app.infrastructure.db.repositories.review_action_repository import (
    ReviewActionRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)


def create_org_user(db_session):
    suffix = uuid4().hex

    organization = Organization(name=f"Test Organization {suffix}")
    user = User(
        full_name="Test Reviewer",
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
        title="Review test submission",
        created_by=user.id,
    )

    version = repository.create_submission_version(
        organization_id=organization.id,
        submission_id=submission.id,
        version_number=1,
        source_type="text",
        sha256="a" * 64,
        created_by=user.id,
        original_text="Original content for review",
    )

    return submission, version


def test_create_review_action_preserves_version_reference(db_session):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)

    action = repository.create_review_action(
        organization_id=organization.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=user.id,
        action="approve",
    )

    assert action.id is not None
    assert action.organization_id == organization.id
    assert action.submission_id == submission.id
    assert action.submission_version_id == version.id
    assert action.reviewer_id == user.id
    assert action.action == "approve"


def test_list_review_actions_for_submission(db_session):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)

    first = repository.create_review_action(
        organization_id=organization.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=user.id,
        action="request_changes",
        comment="Please correct the claim.",
    )

    second = repository.create_review_action(
        organization_id=organization.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=user.id,
        action="approve",
    )

    history = repository.list_for_submission(
        organization_id=organization.id,
        submission_id=submission.id,
    )

    assert history is not None
    assert len(history) == 2
    assert {item.id for item in history} == {first.id, second.id}


def test_get_review_action_is_organization_scoped(db_session):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)
    action = repository.create_review_action(
        organization_id=organization.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=user.id,
        action="approve",
    )

    other_organization = Organization(name="Unrelated Organization")
    db_session.add(other_organization)
    db_session.flush()

    assert repository.get_review_action(
        organization_id=other_organization.id,
        review_action_id=action.id,
    ) is None


def test_list_review_actions_returns_none_for_other_organization(
    db_session,
):
    organization, user = create_org_user(db_session)
    submission, _ = create_submission_and_version(
        db_session, organization, user
    )

    other_organization = Organization(name="Unrelated Organization")
    db_session.add(other_organization)
    db_session.flush()

    repository = ReviewActionRepository(db_session)

    assert repository.list_for_submission(
        organization_id=other_organization.id,
        submission_id=submission.id,
    ) is None


def test_review_action_rejects_version_from_another_submission(
    db_session,
):
    organization, user = create_org_user(db_session)
    first_submission, _ = create_submission_and_version(
        db_session, organization, user
    )
    second_submission, second_version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)

    with pytest.raises(LookupError, match="does not belong"):
        repository.create_review_action(
            organization_id=organization.id,
            submission_id=first_submission.id,
            submission_version_id=second_version.id,
            reviewer_id=user.id,
            action="approve",
        )


@pytest.mark.parametrize("action", ["request_changes", "reject"])
@pytest.mark.parametrize("comment", [None, "", "   "])
def test_comment_required_for_changes_or_rejection(
    db_session, action, comment
):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)

    with pytest.raises(ValueError, match="comment is required"):
        repository.create_review_action(
            organization_id=organization.id,
            submission_id=submission.id,
            submission_version_id=version.id,
            reviewer_id=user.id,
            action=action,
            comment=comment,
        )


def test_invalid_review_action_is_rejected(db_session):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)

    with pytest.raises(ValueError, match="Unsupported review action"):
        repository.create_review_action(
            organization_id=organization.id,
            submission_id=submission.id,
            submission_version_id=version.id,
            reviewer_id=user.id,
            action="publish",
        )


def test_get_review_action_returns_existing_record(db_session):
    organization, user = create_org_user(db_session)
    submission, version = create_submission_and_version(
        db_session, organization, user
    )

    repository = ReviewActionRepository(db_session)
    action = repository.create_review_action(
        organization_id=organization.id,
        submission_id=submission.id,
        submission_version_id=version.id,
        reviewer_id=user.id,
        action="reject",
        comment="The submission needs correction.",
    )

    db_session.expire_all()

    retrieved = repository.get_review_action(
        organization_id=organization.id,
        review_action_id=action.id,
    )

    assert retrieved is not None
    assert retrieved.id == action.id
    assert retrieved.action == "reject"
    assert retrieved.comment == "The submission needs correction."