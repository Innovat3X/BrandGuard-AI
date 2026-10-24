from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.review_action import ReviewAction
from app.infrastructure.db.submission import Submission
from app.infrastructure.db.submission_version import SubmissionVersion


REVIEW_ACTIONS = {"approve", "request_changes", "reject"}


class ReviewActionRepository:
    """Persistence operations for append-only human review actions.

    The application service validates reviewer permissions and workflow
    transitions. The service also owns the transaction and commit.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_review_action(
        self,
        organization_id: UUID,
        submission_id: UUID,
        submission_version_id: UUID,
        reviewer_id: UUID,
        action: str,
        comment: str | None = None,
    ) -> ReviewAction:
        """Append a review action for one exact submission version.

        The repository validates the organization and submission/version
        relationship. Reviewer authorization and whether the action is
        permitted for the current workflow state are service concerns.
        """
        if action not in REVIEW_ACTIONS:
            raise ValueError(f"Unsupported review action: {action}")

        if action in {"request_changes", "reject"} and (
            comment is None or not comment.strip()
        ):
            raise ValueError(
                f"A non-empty comment is required for '{action}'."
            )

        submission = self._session.scalar(
            select(Submission)
            .where(
                Submission.organization_id == organization_id,
                Submission.id == submission_id,
            )
            .with_for_update()
        )

        if submission is None:
            raise LookupError(
                "Submission not found within the specified organization."
            )

        version = self._session.scalar(
            select(SubmissionVersion).where(
                SubmissionVersion.organization_id == organization_id,
                SubmissionVersion.submission_id == submission_id,
                SubmissionVersion.id == submission_version_id,
            )
        )

        if version is None:
            raise LookupError(
                "Submission version does not belong to this submission "
                "within the specified organization."
            )

        review_action = ReviewAction(
            organization_id=organization_id,
            submission_id=submission_id,
            submission_version_id=submission_version_id,
            reviewer_id=reviewer_id,
            action=action,
            comment=comment,
        )

        self._session.add(review_action)
        self._session.flush()

        return review_action

    def get_review_action(
        self,
        organization_id: UUID,
        review_action_id: UUID,
    ) -> ReviewAction | None:
        """Retrieve one review action within its organization."""
        statement = select(ReviewAction).where(
            ReviewAction.organization_id == organization_id,
            ReviewAction.id == review_action_id,
        )

        return self._session.scalar(statement)

    def list_for_submission(
        self,
        organization_id: UUID,
        submission_id: UUID,
    ) -> list[ReviewAction] | None:
        """List a submission's review history in chronological order.

        Returns None if the submission is not found within the requested
        organization, or a list (possibly empty) if it exists.
        """
        submission_exists = self._session.scalar(
            select(Submission.id).where(
                Submission.organization_id == organization_id,
                Submission.id == submission_id,
            )
        )

        if submission_exists is None:
            return None

        statement = (
            select(ReviewAction)
            .where(
                ReviewAction.organization_id == organization_id,
                ReviewAction.submission_id == submission_id,
            )
            .order_by(ReviewAction.created_at, ReviewAction.id)
        )

        return list(self._session.scalars(statement).all())