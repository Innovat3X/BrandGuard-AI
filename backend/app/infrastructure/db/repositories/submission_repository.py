from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.db.submission import Submission
from app.infrastructure.db.submission_version import SubmissionVersion


class SubmissionRepository:
    """Database operations for submissions and immutable versions.

    The application service owns transaction boundaries and commits.
    This repository adds or updates records and flushes them when needed,
    but never commits transactions independently.

    All methods accessing a submission require its trusted organization ID.
    Permission checks and workflow-state transition rules belong to the
    application service.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_submission(
        self,
        organization_id: UUID,
        title: str,
        created_by: UUID,
    ) -> Submission:
        """Create a submission parent for its initial version.

        The parent and its first version must be persisted within the same
        service-controlled transaction. New submissions start as submitted,
        as specified in the API contract.
        """
        submission = Submission(
            organization_id=organization_id,
            title=title,
            status="submitted",
            current_version_number=1,
            created_by=created_by,
        )

        self._session.add(submission)
        self._session.flush()

        return submission

    def get_submission(
        self,
        organization_id: UUID,
        submission_id: UUID,
    ) -> Submission | None:
        """Retrieve a submission within the specified organization."""
        statement = select(Submission).where(
            Submission.organization_id == organization_id,
            Submission.id == submission_id,
        )

        return self._session.scalar(statement)

    def get_submission_version(
        self,
        organization_id: UUID,
        submission_id: UUID,
        version_number: int,
    ) -> SubmissionVersion | None:
        """Retrieve one exact version within the specified organization."""
        statement = select(SubmissionVersion).where(
            SubmissionVersion.organization_id == organization_id,
            SubmissionVersion.submission_id == submission_id,
            SubmissionVersion.version_number == version_number,
        )

        return self._session.scalar(statement)

    def create_submission_version(
        self,
        organization_id: UUID,
        submission_id: UUID,
        version_number: int,
        source_type: str,
        sha256: str,
        created_by: UUID,
        original_text: str | None = None,
        storage_key: str | None = None,
        original_filename: str | None = None,
        media_type: str | None = None,
        extracted_text: str | None = None,
    ) -> SubmissionVersion:
        """Create the next immutable version without overwriting history.

        The parent row is locked while checking the next version number.
        Concurrent attempts to create versions for the same submission
        are therefore serialized within their database transactions.

        After creation, the service must call update_current_version()
        in the same transaction.
        """
        statement = (
            select(Submission)
            .where(
                Submission.organization_id == organization_id,
                Submission.id == submission_id,
            )
            .with_for_update()
        )

        submission = self._session.scalar(statement)

        if submission is None:
            raise LookupError(
                "Submission not found within the specified organization."
            )

        latest_version_number = self._session.scalar(
            select(func.max(SubmissionVersion.version_number)).where(
                SubmissionVersion.organization_id == organization_id,
                SubmissionVersion.submission_id == submission_id,
            )
        )

        if latest_version_number is None:
            if submission.current_version_number != 1:
                raise RuntimeError(
                    "Submission version pointer is inconsistent "
                    "with its version history."
                )

            expected_version_number = 1
        else:
            if latest_version_number != submission.current_version_number:
                raise RuntimeError(
                    "Submission version pointer is inconsistent "
                    "with its version history."
                )

            expected_version_number = latest_version_number + 1

        if version_number != expected_version_number:
            raise ValueError(
                f"Expected submission version "
                f"{expected_version_number}, received {version_number}."
            )

        version = SubmissionVersion(
            organization_id=organization_id,
            submission_id=submission_id,
            version_number=version_number,
            source_type=source_type,
            original_text=original_text,
            storage_key=storage_key,
            original_filename=original_filename,
            media_type=media_type,
            sha256=sha256,
            extracted_text=extracted_text,
            created_by=created_by,
        )

        self._session.add(version)
        self._session.flush()

        return version

    def update_current_version(
        self,
        organization_id: UUID,
        submission_id: UUID,
        version_number: int,
    ) -> Submission:
        """Advance the submission's current-version pointer.

        The target version must already exist and belong to this exact
        organization and submission. The pointer can stay unchanged or
        advance by one version; it cannot move backwards or skip versions.
        """
        statement = (
            select(Submission)
            .where(
                Submission.organization_id == organization_id,
                Submission.id == submission_id,
            )
            .with_for_update()
        )

        submission = self._session.scalar(statement)

        if submission is None:
            raise LookupError(
                "Submission not found within the specified organization."
            )

        version = self.get_submission_version(
            organization_id=organization_id,
            submission_id=submission_id,
            version_number=version_number,
        )

        if version is None:
            raise LookupError(
                "Target submission version was not found."
            )

        if version_number == submission.current_version_number:
            return submission

        if version_number != submission.current_version_number + 1:
            raise ValueError(
                "The current-version pointer can only advance "
                "to the next version."
            )

        submission.current_version_number = version_number
        self._session.flush()

        return submission

    def update_submission_status(
        self,
        organization_id: UUID,
        submission_id: UUID,
        status: str,
    ) -> Submission | None:
        """Update a submission status within its organization.

        The application service must validate whether the requested
        status transition is permitted before calling this method.
        """
        statement = (
            select(Submission)
            .where(
                Submission.organization_id == organization_id,
                Submission.id == submission_id,
            )
            .with_for_update()
        )

        submission = self._session.scalar(statement)

        if submission is None:
            return None

        submission.status = status
        self._session.flush()

        return submission