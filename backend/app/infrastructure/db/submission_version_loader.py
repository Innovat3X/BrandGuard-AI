"""Database-backed loader for immutable submission versions."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.submission_version import SubmissionVersion


@dataclass(frozen=True)
class DatabaseLoadedSubmissionVersion:
    """Content and identifiers loaded from one stored version."""

    organization_id: UUID
    submission_version_id: UUID
    submission_id: UUID
    version_number: int
    content_text: str


class DatabaseSubmissionVersionLoader:
    """Load an exact submission version for analysis.

    The organisation ID must come from the persisted analysis job,
    not from an untrusted client request.

    The initial M4 implementation supports text submissions.
    File extraction will be integrated separately.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def load_submission_version(
        self,
        *,
        organization_id: UUID,
        submission_version_id: UUID,
    ) -> DatabaseLoadedSubmissionVersion:
        """Retrieve the requested version within its organisation."""

        statement = select(SubmissionVersion).where(
            SubmissionVersion.organization_id == organization_id,
            SubmissionVersion.id == submission_version_id,
        )

        version = self._session.scalar(statement)

        if version is None:
            raise LookupError(
                "Submission version not found within this organization."
            )

        if version.source_type != "text":
            raise NotImplementedError(
                "The initial analysis worker supports text submissions "
                "only. File extraction must be implemented before "
                "file-based submissions can be analysed."
            )

        content_text = (
            version.extracted_text
            if version.extracted_text is not None
            else version.original_text
        )

        if content_text is None:
            raise ValueError(
                "The stored text submission has no available content."
            )

        return DatabaseLoadedSubmissionVersion(
            organization_id=version.organization_id,
            submission_version_id=version.id,
            submission_id=version.submission_id,
            version_number=version.version_number,
            content_text=content_text,
        )