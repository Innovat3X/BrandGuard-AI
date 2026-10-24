from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.db.finding import Finding
from app.infrastructure.db.submission_version import SubmissionVersion


class FindingRepository:
    """Read persisted findings for an organization's submissions.

    The application service owns transaction boundaries and commits.
    All queries require trusted organization scope.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_submission_version(
        self,
        organization_id: UUID,
        submission_id: UUID,
        version_number: int,
    ) -> list[Finding] | None:
        """Return findings for one exact immutable submission version.

        Returns:
            A list of findings, possibly empty, if the version exists.
            None if the requested version is not found within the
            specified organization.

        Findings from different submission versions are never mixed.
        """
        version_id = self._session.scalar(
            select(SubmissionVersion.id).where(
                SubmissionVersion.organization_id == organization_id,
                SubmissionVersion.submission_id == submission_id,
                SubmissionVersion.version_number == version_number,
            )
        )

        if version_id is None:
            return None

        statement = (
            select(Finding)
            .where(
                Finding.organization_id == organization_id,
                Finding.submission_version_id == version_id,
            )
            .order_by(Finding.created_at, Finding.id)
        )

        return list(self._session.scalars(statement).all())

    def get_finding(
        self,
        organization_id: UUID,
        finding_id: UUID,
    ) -> Finding | None:
        """Retrieve a single finding within its organization."""
        statement = select(Finding).where(
            Finding.organization_id == organization_id,
            Finding.id == finding_id,
        )

        return self._session.scalar(statement)