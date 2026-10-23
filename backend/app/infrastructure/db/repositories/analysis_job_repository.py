from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
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
        """Atomically claim a queued job using its persisted identity.

        Queue messages carry the job ID. The organisation scope is
        derived from the persisted job row returned by the atomic
        update, rather than supplied by the queue message.

        Returns None when the job does not exist or has already been
        claimed by another worker. The returned attempts value is the
        claimed-attempt token for stale-worker protection.

        started_at records the first-ever processing start and is
        preserved across retries. updated_at is refreshed on each
        successful claim. Recovery code should use updated_at as the
        current staleness baseline, not started_at.
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

        Queued -> processing must use claim_queued_job(), which increments
        the attempt count atomically.

        Processing -> queued requires the current claimed_attempt token
        and uses it as part of the conditional UPDATE.

        Completed, partial, and failed are terminal states. They must be
        written through persist_findings_and_finish_job(), which locks
        the job and validates the claimed attempt before finalisation.

        Returns None when the scoped job or expected state/attempt does
        not match. The application service owns commits and rollbacks.
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
        """Validate source provenance for new findings.

        Approved versions are valid sources. Archived versions are also
        valid historical sources only when approval metadata proves that
        they were approved before archival. Draft or otherwise unapproved
        versions and cross-organisation references are rejected.

        New analysis must select from currently applicable approved
        versions and retain the exact version IDs it used.
        """
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
        token is stale. In that case, no findings or final status changes
        are written.

        Duplicate fingerprints within the same job are ignored.
        Referenced rule/fact versions must have valid approval provenance
        and belong to the same organization as the job.

        Submission status is updated only if the analysed version is
        still the submission's current version.

        The application service must commit or roll back the transaction.
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

        # Validate source references only after checking the attempt token.
        # A stale worker returns False and cannot write findings.
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

        if (
            submission is not None
            and submission.current_version_number == version.version_number
        ):
            submission.status = submission_status

        self._session.flush()
        return True