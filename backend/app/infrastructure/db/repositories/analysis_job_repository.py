from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.infrastructure.db.analysis_job import AnalysisJob
from app.infrastructure.db.brand_fact_version import BrandFactVersion
from app.infrastructure.db.brand_rule_version import BrandRuleVersion
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

SOURCE_VERSION_VALID_STATUSES = {"approved", "archived"}

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

    Application services own transaction boundaries and commits.
    This repository never commits a transaction independently.
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
        """Create a queued job or return its existing idempotent request.

        Reusing an idempotency key for a different submission version
        or requested-check configuration is rejected.
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

    def claim_queued_job(
        self,
        job_id: UUID,
    ) -> AnalysisJob | None:
        """Atomically claim a queued job.

        The returned attempts value is the claimed-attempt token.
        Claiming initialises the heartbeat and clears any dispatch lease.
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
                heartbeat_at=func.now(),
                dispatch_lease_token=None,
                dispatch_lease_expires_at=None,
                completed_at=None,
                error_code=None,
                error_message=None,
                updated_at=func.now(),
            )
            .returning(
                AnalysisJob.id,
                AnalysisJob.organization_id,
            )
        )

        claimed_row = self._session.execute(statement).one_or_none()

        if claimed_row is None:
            return None

        claimed_id, claimed_organization_id = claimed_row

        return self._session.scalar(
            select(AnalysisJob)
            .where(
                AnalysisJob.organization_id == claimed_organization_id,
                AnalysisJob.id == claimed_id,
            )
            .execution_options(populate_existing=True)
        )

    def heartbeat_processing_job(
        self,
        job_id: UUID,
        claimed_attempt: int,
    ) -> bool:
        """Refresh a heartbeat only for the currently owned attempt."""
        statement = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == "processing",
                AnalysisJob.attempts == claimed_attempt,
            )
            .values(
                heartbeat_at=func.now(),
                updated_at=func.now(),
            )
            .returning(AnalysisJob.id)
        )

        return self._session.scalar(statement) is not None

    def list_stale_processing_jobs(
        self,
        stale_before: datetime,
        limit: int,
    ) -> list[AnalysisJob]:
        """Return a bounded batch of jobs whose heartbeat is stale.

        Jobs with a missing heartbeat are included for recovery rather
        than remaining stuck indefinitely.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1.")

        statement = (
            select(AnalysisJob)
            .where(
                AnalysisJob.status == "processing",
                or_(
                    AnalysisJob.heartbeat_at.is_(None),
                    AnalysisJob.heartbeat_at < stale_before,
                ),
            )
            .order_by(
                AnalysisJob.heartbeat_at.asc().nullsfirst(),
                AnalysisJob.created_at.asc(),
                AnalysisJob.id.asc(),
            )
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def recover_stale_processing_job(
        self,
        job_id: UUID,
        expected_attempt: int,
        stale_before: datetime,
        max_attempts: int,
    ) -> bool:
        """Conditionally requeue or fail a stale processing job.

        Status, attempt number, and heartbeat cutoff are checked by one
        conditional UPDATE. If the attempt limit is exhausted, this method
        marks the job failed and updates the submission status only when
        the analysed version is still the submission's current version.

        The job transition and submission update belong to the same
        database transaction. The caller must commit or roll back.
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")

        if expected_attempt < 1:
            raise ValueError("expected_attempt must be at least 1.")

        exhausted = expected_attempt >= max_attempts

        if exhausted:
            new_status = "failed"
            error_code = "WORKER_HEARTBEAT_TIMEOUT"
            error_message = (
                "The worker heartbeat expired and the allowed attempts "
                "were exhausted."
            )
            completed_at = func.now()
        else:
            new_status = "queued"
            error_code = "WORKER_HEARTBEAT_TIMEOUT"
            error_message = (
                "The worker heartbeat expired. The job has been queued "
                "for another attempt."
            )
            completed_at = None

        statement = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == "processing",
                AnalysisJob.attempts == expected_attempt,
                or_(
                    AnalysisJob.heartbeat_at.is_(None),
                    AnalysisJob.heartbeat_at < stale_before,
                ),
            )
            .values(
                status=new_status,
                completed_at=completed_at,
                error_code=error_code,
                error_message=error_message,
                heartbeat_at=None,
                dispatch_lease_token=None,
                dispatch_lease_expires_at=None,
                updated_at=func.now(),
            )
            .returning(
                AnalysisJob.organization_id,
                AnalysisJob.submission_version_id,
            )
        )

        recovered_row = self._session.execute(statement).one_or_none()

        if recovered_row is None:
            return False

        if exhausted:
            organization_id, submission_version_id = recovered_row

            version = self._session.scalar(
                select(SubmissionVersion).where(
                    SubmissionVersion.organization_id == organization_id,
                    SubmissionVersion.id == submission_version_id,
                )
            )

            if version is None:
                raise LookupError(
                    "Submission version not found while finalising "
                    "an exhausted analysis job."
                )

            # The conditional UPDATE avoids changing submission status
            # if a newer version became current during recovery.
            self._session.execute(
                update(Submission)
                .where(
                    Submission.organization_id == organization_id,
                    Submission.id == version.submission_id,
                    Submission.current_version_number == version.version_number,
                )
                .values(status="failed_needs_attention")
            )

        return True

    def list_queued_jobs_for_recovery(
        self,
        limit: int,
    ) -> list[AnalysisJob]:
        """Return queued jobs with no active dispatch lease."""
        if limit < 1:
            raise ValueError("limit must be at least 1.")

        lease_available = or_(
            AnalysisJob.dispatch_lease_token.is_(None),
            AnalysisJob.dispatch_lease_expires_at.is_(None),
            AnalysisJob.dispatch_lease_expires_at <= func.now(),
        )

        statement = (
            select(AnalysisJob)
            .where(
                AnalysisJob.status == "queued",
                lease_available,
            )
            .order_by(
                AnalysisJob.created_at.asc(),
                AnalysisJob.id.asc(),
            )
            .limit(limit)
        )

        return list(self._session.scalars(statement).all())

    def acquire_dispatch_lease(
        self,
        job_id: UUID,
        lease_token: UUID | str,
        lease_expires_at: datetime,
        stale_before: datetime | None = None,
    ) -> bool:
        """Acquire a dispatch lease for a queued job, if available.

        UUID tokens are stored as strings. An optional stale_before cutoff
        can restrict acquisition to older jobs. The conditional UPDATE
        rechecks status and lease availability atomically.
        """
        token = str(lease_token).strip()

        if not token:
            raise ValueError("lease_token must not be empty.")

        if (
            lease_expires_at.tzinfo is None
            or lease_expires_at.utcoffset() is None
        ):
            raise ValueError("lease_expires_at must be timezone-aware.")

        conditions = [
            AnalysisJob.id == job_id,
            AnalysisJob.status == "queued",
            or_(
                AnalysisJob.dispatch_lease_token.is_(None),
                AnalysisJob.dispatch_lease_expires_at.is_(None),
                AnalysisJob.dispatch_lease_expires_at <= func.now(),
            ),
        ]

        if stale_before is not None:
            if stale_before.tzinfo is None or stale_before.utcoffset() is None:
                raise ValueError("stale_before must be timezone-aware.")
            conditions.append(AnalysisJob.updated_at <= stale_before)

        statement = (
            update(AnalysisJob)
            .where(*conditions)
            .values(
                dispatch_lease_token=token,
                dispatch_lease_expires_at=lease_expires_at,
                updated_at=func.now(),
            )
            .returning(AnalysisJob.id)
        )

        return self._session.scalar(statement) is not None

    def release_dispatch_lease(
        self,
        job_id: UUID,
        lease_token: UUID | str,
    ) -> bool:
        """Release a dispatch lease only when the caller still owns it."""
        statement = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status == "queued",
                AnalysisJob.dispatch_lease_token == str(lease_token),
            )
            .values(
                dispatch_lease_token=None,
                dispatch_lease_expires_at=None,
                updated_at=func.now(),
            )
            .returning(AnalysisJob.id)
        )

        return self._session.scalar(statement) is not None

    def update_job_status(
        self,
        organization_id: UUID,
        job_id: UUID,
        expected_status: str,
        new_status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        claimed_attempt: int | None = None,
    ) -> AnalysisJob | None:
        """Apply a non-terminal status transition safely.

        Processing -> queued requires the current attempt token.
        Terminal states must be written through
        persist_findings_and_finish_job().
        """
        if expected_status not in JOB_STATUSES:
            raise ValueError(
                f"Unsupported expected job status: {expected_status}"
            )

        if new_status not in JOB_STATUSES:
            raise ValueError(
                f"Unsupported new job status: {new_status}"
            )

        if new_status in TERMINAL_JOB_STATUSES:
            raise ValueError(
                "Terminal job transitions must use "
                "persist_findings_and_finish_job() so the claimed "
                "attempt can be validated."
            )

        if new_status == "processing":
            raise ValueError(
                "Queued jobs must be claimed with claim_queued_job()."
            )

        if expected_status in TERMINAL_JOB_STATUSES:
            raise ValueError(
                "Terminal analysis jobs cannot transition to another status."
            )

        if expected_status == "processing":
            if claimed_attempt is None:
                raise ValueError(
                    "claimed_attempt is required when updating a processing job."
                )

            if new_status != "queued":
                raise ValueError(
                    "A processing job can only be requeued through "
                    "an attempt-aware status update."
                )
        elif claimed_attempt is not None:
            raise ValueError(
                "claimed_attempt may only be supplied when "
                "expected_status is 'processing'."
            )

        values: dict[str, Any] = {
            "status": new_status,
            "error_code": error_code,
            "error_message": error_message,
            "completed_at": None,
            "updated_at": func.now(),
        }

        if expected_status == "processing" and new_status == "queued":
            values.update(
                heartbeat_at=None,
                dispatch_lease_token=None,
                dispatch_lease_expires_at=None,
            )

        conditions = [
            AnalysisJob.organization_id == organization_id,
            AnalysisJob.id == job_id,
            AnalysisJob.status == expected_status,
        ]

        if expected_status == "processing":
            conditions.append(AnalysisJob.attempts == claimed_attempt)

        statement = (
            update(AnalysisJob)
            .where(*conditions)
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

    def _validate_source_versions(
        self,
        organization_id: UUID,
        findings: Sequence[Mapping[str, Any]],
    ) -> None:
        """Validate source provenance for new findings."""
        for index, finding in enumerate(findings):
            rule_version_id = finding.get("source_rule_version_id")

            if rule_version_id is not None:
                rule_version = self._session.scalar(
                    select(BrandRuleVersion).where(
                        BrandRuleVersion.organization_id == organization_id,
                        BrandRuleVersion.id == rule_version_id,
                    )
                )

                if (
                    rule_version is None
                    or rule_version.status not in SOURCE_VERSION_VALID_STATUSES
                    or rule_version.approved_at is None
                    or rule_version.approved_by is None
                ):
                    raise ValueError(
                        f"Finding at index {index} must reference a "
                        "previously approved rule version in the same organization."
                    )

            fact_version_id = finding.get("source_fact_version_id")

            if fact_version_id is not None:
                fact_version = self._session.scalar(
                    select(BrandFactVersion).where(
                        BrandFactVersion.organization_id == organization_id,
                        BrandFactVersion.id == fact_version_id,
                    )
                )

                if (
                    fact_version is None
                    or fact_version.status not in SOURCE_VERSION_VALID_STATUSES
                    or fact_version.approved_at is None
                    or fact_version.approved_by is None
                ):
                    raise ValueError(
                        f"Finding at index {index} must reference a "
                        "previously approved fact version in the same organization."
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
        """Persist findings and finalise the claimed job in one transaction.

        Returns False if the job is no longer processing or the attempt
        token is stale. No findings or final status changes are written
        in that case.

        Submission status is updated only if the analysed version is
        still the submission's current version. The application service
        must commit or roll back the transaction.
        """
        if final_status not in TERMINAL_JOB_STATUSES:
            raise ValueError(
                "Final status must be completed, partial, or failed."
            )

        if (
            submission_status is not None
            and submission_status not in SUBMISSION_STATUSES
        ):
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

            fingerprint = finding["finding_fingerprint"]

            if not isinstance(fingerprint, str) or not fingerprint.strip():
                raise ValueError(
                    f"Finding at index {index} has an empty or invalid fingerprint."
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

        if job.status != "processing" or job.attempts != claimed_attempt:
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

        self._validate_source_versions(
            organization_id=organization_id,
            findings=prepared_findings,
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

            statement = (
                insert(Finding)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        Finding.analysis_job_id,
                        Finding.finding_fingerprint,
                    ]
                )
            )

            self._session.execute(statement)

        job.status = final_status
        job.completed_at = func.now()
        job.error_code = error_code
        job.error_message = error_message
        job.heartbeat_at = None
        job.dispatch_lease_token = None
        job.dispatch_lease_expires_at = None

        if (
            submission is not None
            and submission.current_version_number == version.version_number
        ):
            submission.status = submission_status

        self._session.flush()
        return True