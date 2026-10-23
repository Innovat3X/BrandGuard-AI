from sqlalchemy.orm import Session

from app.infrastructure.db import (
    Organization,
    Submission,
    User,
)


def test_related_records_roll_back_together(
    db_session: Session,
) -> None:
    """Verify rollback removes related writes from the transaction."""
    organization = Organization(
        name="Synthetic rollback organisation"
    )

    user = User(
        full_name="Synthetic Rollback User",
        email="rollback@example.test",
        password_hash="synthetic-test-hash",
        is_active=True,
    )

    db_session.add_all([organization, user])
    db_session.flush()

    organization_id = organization.id
    user_id = user.id

    submission = Submission(
        organization_id=organization_id,
        title="Synthetic rollback submission",
        status="draft",
        current_version_number=1,
        created_by=user_id,
    )

    db_session.add(submission)
    db_session.flush()

    submission_id = submission.id

    # Roll back the writes made in this session.
    db_session.rollback()

    # Verify that none of those records remains in the database.
    assert db_session.get(Submission, submission_id) is None
    assert db_session.get(Organization, organization_id) is None
    assert db_session.get(User, user_id) is None