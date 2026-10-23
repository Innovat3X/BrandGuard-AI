from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.infrastructure.db.analysis_job import AnalysisJob
from app.infrastructure.db.finding import Finding
from app.infrastructure.db.submission import Submission
from app.infrastructure.db.submission_version import SubmissionVersion


JOB_STATUSES = {
    "queued",
    "processing",
    "completed",
    "partial",
    "failed",
}

TERMINAL_JOB_STATUSES = {"completed", "partial", "failed"}

SUBMISSION_STATUSES = {
    "draft",
    "submitted",
    "processing",
    "under_review",
    "changes_requested",
    "approved",
    "rejected",
    "failed_needs_attention",
}

FINDING_FIELDS = {
    "category",
    "severity",
    "result",
    "explanation",
    "evidence",
    "source_rule_version_id",
    "source_fact_version_id",
    "location",
    "suggested_correction",
    "detection_method",
    "requires_human_review",
    "finding_fingerprint",
}

REQUIRED_FINDING_FIELDS = {
    "category",
    "severity",
    "result",
    "explanation",
    "detection_method",
    "requires_human_review",
    "finding_fingerprint",
}


class AnalysisJobRepository:
    """Persistence operations for analysis jobs and their findings.

    The application service owns the transaction boundary and commits.
    Methods in this repository flush or execute database statements but
    never commit independently.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_or_get_analysis_job(
        self,
        organization_id: UUID,
        submission_version_id: UUID,
        idempotency_key: str,
        requested_checks: dict[str, Any] | list[Any] | None = None,
    ) -> AnalysisJob:
        """Create a queued job, or return the existing matching request.

        Reusing an idempotency key for a different submission version or
        different requested checks is rejected.
        """
        if not idempotency_key.strip():
            raise ValueError("Idempotency key must not be empty.")

        version = self._session.scalar(
            select(SubmissionVersion).where(
                SubmissionVersion.organization_id == organization_id,
                SubmissionVersion.id == submission_version_id,
            )
        )

        if version is None:
            raise LookupError(
                "Submission version not found within the specified organization."
            )

        statement = (
            insert(AnalysisJob)
            .values(
                id=uuid4(),
                organization_id=organization_id,
                submission_version_id=submission_version_id,
                idempotency_key=idempotency_key,
                requested_checks=requested_checks,
                status="queued",
                attempts=0,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    AnalysisJob.organization_id,
                    AnalysisJob.idempotency_key,
                ]
            )
            .returning(AnalysisJob.id)
        )

        self._session.scalar(statement)

        job = self._session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.organization_id == organization_id,
                AnalysisJob.idempotency_key == idempotency_key,
            )
        )

        if job is None:
            raise RuntimeError(
                "Analysis job was neither created nor found after insertion."
            )

        if (
            job.submission_version_id != submission_version_id
            or job.requested_checks != requested_checks
        ):
            raise ValueError(
                "This idempotency key is already associated with a "
                "different submission version or requested-check configuration."
            )

        return job

    def get_analysis_job(
        self,
        organization_id: UUID,
        job_id: UUID,
    ) -> AnalysisJob | None:
        """Retrieve a job scoped to its trusted organization."""
        return self._session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.organization_id == organization_id,
                AnalysisJob.id == job_id,
            )
        )

    def claim_queued_job(self, job_id: UUID) -> AnalysisJob | None:
        """Atomically claim a queued job and increment its attempt count.

        Returns None when the job does not exist or another worker has
        already claimed it. The worker must use the returned attempts
        value as its claimed-attempt token during finalization.
        """
        statement = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == "queued",
            )
            .values(
                status="processing",
                attempts=AnalysisJob.attempts + 1,
                started_at=func.coalesce(
                    AnalysisJob.started_at,
                    func.now(),
                ),
                completed_at=None,
                error_code=None,
                error_message=None,
                updated_at=func.now(),
            )
            .returning(AnalysisJob.id)
        )

        claimed_id = self._session.scalar(statement)

        if claimed_id is None:
            return None

        return self._session.scalar(
            select(AnalysisJob)
            .where(AnalysisJob.id == claimed_id)
            .execution_options(populate_existing=True)
        )

    def update_job_status(
        self,
        organization_id: UUID,
        job_id: UUID,
        expected_status: str,
        new_status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> AnalysisJob | None:
        """Conditionally update a job status using organization scope.

        Returns None when the job is absent or its status no longer
        matches expected_status. Final outcomes with findings should use
        persist_findings_and_finish_job() instead.
        """
        if expected_status not in JOB_STATUSES:
            raise ValueError(f"Unsupported expected job status: {expected_status}")

        if new_status not in JOB_STATUSES:
            raise ValueError(f"Unsupported new job status: {new_status}")

        values: dict[str, Any] = {
            "status": new_status,
            "error_code": error_code,
            "error_message": error_message,
            "completed_at": (
                func.now() if new_status in TERMINAL_JOB_STATUSES else None
            ),
            "updated_at": func.now(),
        }

        statement = (
            update(AnalysisJob)
            .where(
                AnalysisJob.organization_id == organization_id,
                AnalysisJob.id == job_id,
                AnalysisJob.status == expected_status,
            )
            .values(**values)
            .returning(AnalysisJob.id)
        )

        updated_id = self._session.scalar(statement)

        if updated_id is None:
            return None

        return self._session.scalar(
            select(AnalysisJob)
            .where(
                AnalysisJob.organization_id == organization_id,
                AnalysisJob.id == updated_id,
            )
            .execution_options(populate_existing=True)
        )

    def persist_findings_and_finish_job(
        self,
        organization_id: UUID,
        job_id: UUID,
        submission_version_id: UUID,
        claimed_attempt: int,
        findings: Sequence[Mapping[str, Any]],
        final_status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        submission_status: str | None = None,
    ) -> bool:
        """Persist findings and finalize the claimed job atomically.

        Returns False if the job is no longer processing or the worker's
        claimed attempt is stale. In that case, no findings are written.

        Duplicate finding fingerprints within the same job are ignored.
        The optional submission status is updated only if the analyzed
        version is still the submission's current version.
        """
        if final_status not in TERMINAL_JOB_STATUSES:
            raise ValueError(
                "Final status must be completed, partial, or failed."
            )

        if submission_status is not None and submission_status not in SUBMISSION_STATUSES:
            raise ValueError(
                f"Unsupported submission status: {submission_status}"
            )

        prepared_findings: list[dict[str, Any]] = []

        for index, finding in enumerate(findings):
            unknown_fields = set(finding) - FINDING_FIELDS
            if unknown_fields:
                raise ValueError(
                    f"Finding at index {index} contains unsupported fields: "
                    f"{sorted(unknown_fields)}"
                )

            missing_fields = REQUIRED_FINDING_FIELDS - set(finding)
            if missing_fields:
                raise ValueError(
                    f"Finding at index {index} is missing required fields: "
                    f"{sorted(missing_fields)}"
                )

            if not finding["finding_fingerprint"]:
                raise ValueError(
                    f"Finding at index {index} has an empty fingerprint."
                )

            prepared_findings.append(dict(finding))

        job = self._session.scalar(
            select(AnalysisJob)
            .where(
                AnalysisJob.organization_id == organization_id,
                AnalysisJob.id == job_id,
            )
            .with_for_update()
        )

        if job is None:
            raise LookupError(
                "Analysis job not found within the specified organization."
            )

        if job.submission_version_id != submission_version_id:
            raise ValueError(
                "Submission version does not match the analysis job."
            )

        if (
            job.status != "processing"
            or job.attempts != claimed_attempt
        ):
            return False

        version = self._session.scalar(
            select(SubmissionVersion).where(
                SubmissionVersion.organization_id == organization_id,
                SubmissionVersion.id == submission_version_id,
            )
        )

        if version is None:
            raise LookupError(
                "Submission version not found within the specified organization."
            )

        submission = None

        if submission_status is not None:
            submission = self._session.scalar(
                select(Submission)
                .where(
                    Submission.organization_id == organization_id,
                    Submission.id == version.submission_id,
                )
                .with_for_update()
            )

            if submission is None:
                raise LookupError(
                    "Parent submission not found within the specified organization."
                )

        for finding in prepared_findings:
            values = {
                **finding,
                "organization_id": organization_id,
                "analysis_job_id": job_id,
                "submission_version_id": submission_version_id,
            }

            statement = insert(Finding).values(**values).on_conflict_do_nothing(
                index_elements=[
                    Finding.analysis_job_id,
                    Finding.finding_fingerprint,
                ]
            )

            self._session.execute(statement)

        job.status = final_status
        job.completed_at = func.now()
        job.error_code = error_code
        job.error_message = error_message

        if (
            submission is not None
            and submission.current_version_number == version.version_number
        ):
            submission.status = submission_status

        self._session.flush()
        return True