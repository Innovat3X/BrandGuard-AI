"""Application orchestration for background analysis jobs.

This module coordinates persistence and the analysis pipeline without
depending on a specific AI provider or analysis implementation.

The queue adapter and pipeline adapter will be connected separately.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.services.analysis_persistence_mapper import (
    map_findings_for_persistence,
)


@dataclass(frozen=True)
class LoadedSubmissionVersion:
    """Trusted context loaded for one immutable submission version."""

    organization_id: UUID
    submission_version_id: UUID
    submission_id: UUID
    version_number: int
    content_text: str


@dataclass(frozen=True)
class AnalysisJobContext:
    """Inputs supplied to an analysis pipeline adapter."""

    organization_id: UUID
    job_id: UUID
    submission_id: UUID
    submission_version_id: UUID
    version_number: int
    content_text: str
    requested_checks: dict[str, Any] | list[Any] | None


@dataclass(frozen=True)
class WorkerResult:
    """Outcome of a worker invocation."""

    job_id: UUID
    status: str
    attempts: int = 0
    finding_count: int = 0
    retry_scheduled: bool = False


class SubmissionVersionLoader(Protocol):
    """Load a version using trusted organisation scope."""

    def load_submission_version(
        self,
        *,
        organization_id: UUID,
        submission_version_id: UUID,
    ) -> LoadedSubmissionVersion:
        """Return the exact stored version or raise an exception."""
        ...


class AnalysisPipelineResult(Protocol):
    """Minimum response interface expected from an analysis adapter."""

    job_id: UUID
    submission_id: UUID
    submission_version_id: UUID
    status: str
    findings: Sequence[Any]


class AnalysisPipeline(Protocol):
    """Adapter around the agreed content-analysis implementation."""

    def analyze(
        self,
        context: AnalysisJobContext,
    ) -> AnalysisPipelineResult:
        """Analyse the supplied immutable version."""
        ...


class AnalysisJobQueue(Protocol):
    """Interface to the background queue."""

    def enqueue_analysis(self, job_id: UUID) -> None:
        """Publish a message containing the persisted job ID."""
        ...


class AnalysisQueueDispatchError(RuntimeError):
    """A persisted job could not be published to the queue."""

    def __init__(self, job_id: UUID) -> None:
        super().__init__(
            "The analysis job remains queued, but queue dispatch failed. "
            "Retry dispatch using the same job ID."
        )
        self.job_id = job_id


class AnalysisWorkerService:
    """Claim, process, and atomically finalise analysis jobs.

    The database repository owns job-state and finding integrity rules.
    This service owns orchestration and transaction boundaries.

    Failed attempts are requeued up to max_attempts. The existing
    repository's claimed-attempt check protects against stale workers.
    """

    def __init__(
        self,
        session: Session,
        version_loader: SubmissionVersionLoader,
        pipeline: AnalysisPipeline,
        queue: AnalysisJobQueue,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")

        self._session = session
        self._jobs = AnalysisJobRepository(session)
        self._version_loader = version_loader
        self._pipeline = pipeline
        self._queue = queue
        self._max_attempts = max_attempts

    def process_job(self, job_id: UUID) -> WorkerResult:
        """Process a queued job once, or safely ignore duplicate delivery."""

        # Claiming is atomic. Only one worker may claim this queued job.
        try:
            job = self._jobs.claim_queued_job(job_id)

            if job is None:
                self._session.rollback()
                return WorkerResult(
                    job_id=job_id,
                    status="not_claimed",
                )

            organization_id = job.organization_id
            submission_version_id = job.submission_version_id
            claimed_attempt = job.attempts
            requested_checks = job.requested_checks

            # Commit the claim before invoking external analysis.
            self._session.commit()

        except Exception:
            self._session.rollback()
            raise

        try:
            loaded_version = (
                self._version_loader.load_submission_version(
                    organization_id=organization_id,
                    submission_version_id=submission_version_id,
                )
            )

            # Reject accidental cross-organisation or wrong-version
            # results from the version loader.
            if loaded_version.organization_id != organization_id:
                raise ValueError(
                    "The loaded version has an unexpected organisation."
                )

            if (
                loaded_version.submission_version_id
                != submission_version_id
            ):
                raise ValueError(
                    "The loader returned a different submission version."
                )

            if loaded_version.version_number < 1:
                raise ValueError(
                    "The loaded version number must be positive."
                )

            if not isinstance(loaded_version.content_text, str):
                raise ValueError(
                    "The loaded content must be a string."
                )

            context = AnalysisJobContext(
                organization_id=organization_id,
                job_id=job_id,
                submission_id=loaded_version.submission_id,
                submission_version_id=submission_version_id,
                version_number=loaded_version.version_number,
                content_text=loaded_version.content_text,
                requested_checks=requested_checks,
            )

            response = self._pipeline.analyze(context)

            # Never persist a report against a different job or version.
            if response.job_id != job_id:
                raise ValueError(
                    "The analysis response references another job."
                )

            if response.submission_id != context.submission_id:
                raise ValueError(
                    "The analysis response references another submission."
                )

            if (
                response.submission_version_id
                != submission_version_id
            ):
                raise ValueError(
                    "The analysis response references another version."
                )

            final_status = getattr(
                response.status,
                "value",
                response.status,
            )

            if final_status not in {"completed", "partial"}:
                raise ValueError(
                    "The analysis pipeline must return completed or partial."
                )

            persisted_findings = map_findings_for_persistence(
                list(response.findings)
            )

            # The repository atomically writes findings and finalises the
            # job. It also updates the submission status only if this
            # analysed version is still current.
            finalised = self._jobs.persist_findings_and_finish_job(
                organization_id=organization_id,
                job_id=job_id,
                submission_version_id=submission_version_id,
                claimed_attempt=claimed_attempt,
                findings=persisted_findings,
                final_status=final_status,
                submission_status="under_review",
            )

            if not finalised:
                self._session.rollback()
                return WorkerResult(
                    job_id=job_id,
                    status="stale",
                    attempts=claimed_attempt,
                )

            self._session.commit()

            return WorkerResult(
                job_id=job_id,
                status=final_status,
                attempts=claimed_attempt,
                finding_count=len(persisted_findings),
            )

        except Exception:
            # Roll back partial writes before attempting a safe retry
            # or finalising the job as failed.
            self._session.rollback()

            return self._handle_failed_attempt(
                organization_id=organization_id,
                job_id=job_id,
                submission_version_id=submission_version_id,
                claimed_attempt=claimed_attempt,
            )

    def _handle_failed_attempt(
        self,
        *,
        organization_id: UUID,
        job_id: UUID,
        submission_version_id: UUID,
        claimed_attempt: int,
    ) -> WorkerResult:
        """Requeue a failed attempt or finish the job as failed."""

        if claimed_attempt < self._max_attempts:
            try:
                requeued_job = self._jobs.update_job_status(
                    organization_id=organization_id,
                    job_id=job_id,
                    expected_status="processing",
                    new_status="queued",
                    error_code="ANALYSIS_ATTEMPT_FAILED",
                    error_message=(
                        "An analysis attempt failed. "
                        "The job is scheduled for retry."
                    ),
                    claimed_attempt=claimed_attempt,
                )

                if requeued_job is None:
                    self._session.rollback()
                    return WorkerResult(
                        job_id=job_id,
                        status="stale",
                        attempts=claimed_attempt,
                    )

                self._session.commit()

            except Exception:
                self._session.rollback()
                raise

            # The job is committed as queued before dispatch. If dispatch
            # fails, the durable job record remains available for recovery.
            try:
                self._queue.enqueue_analysis(job_id)
            except Exception as exc:
                raise AnalysisQueueDispatchError(job_id) from exc

            return WorkerResult(
                job_id=job_id,
                status="queued",
                attempts=claimed_attempt,
                retry_scheduled=True,
            )

        try:
            finalised = self._jobs.persist_findings_and_finish_job(
                organization_id=organization_id,
                job_id=job_id,
                submission_version_id=submission_version_id,
                claimed_attempt=claimed_attempt,
                findings=[],
                final_status="failed",
                error_code="ANALYSIS_FAILED",
                error_message=(
                    "Analysis could not be completed after the "
                    "allowed attempts."
                ),
                submission_status="failed_needs_attention",
            )

            if not finalised:
                self._session.rollback()
                return WorkerResult(
                    job_id=job_id,
                    status="stale",
                    attempts=claimed_attempt,
                )

            self._session.commit()

        except Exception:
            self._session.rollback()
            raise

        return WorkerResult(
            job_id=job_id,
            status="failed",
            attempts=claimed_attempt,
        )