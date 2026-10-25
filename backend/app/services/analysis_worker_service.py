"""Application orchestration for background analysis jobs.

This module coordinates persistence and the analysis pipeline without
depending on a specific AI provider or analysis implementation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
import logging
from threading import Event, Thread
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.services.analysis_dispatch import (
    enqueue_with_dispatch_lease,
)
from app.services.analysis_persistence_mapper import (
    map_findings_for_persistence,
)


logger = logging.getLogger(__name__)
HeartbeatSessionFactory = Callable[[], AbstractContextManager[Session]]


class _WorkerHeartbeat:
    """Refresh a claimed job with an independent database session.

    The repository fences each refresh by processing status and the claimed
    attempt number. A false result means this worker no longer owns the
    current attempt.
    """

    def __init__(
        self,
        *,
        session_factory: HeartbeatSessionFactory,
        job_id: UUID,
        claimed_attempt: int,
        interval_seconds: float,
    ) -> None:
        self._session_factory = session_factory
        self._job_id = job_id
        self._claimed_attempt = claimed_attempt
        self._interval_seconds = interval_seconds
        self._stop_event = Event()
        self._ownership_lost = Event()
        self._thread = Thread(
            target=self._run,
            name=f"analysis-heartbeat-{job_id}",
            daemon=True,
        )

    @property
    def ownership_lost(self) -> bool:
        return self._ownership_lost.is_set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        # Do not let a slow database call block task completion indefinitely.
        self._thread.join(timeout=10.0)

        if self._thread.is_alive():
            logger.warning(
                "Heartbeat thread is still stopping for analysis job %s",
                self._job_id,
            )

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            try:
                with self._session_factory() as heartbeat_session:
                    jobs = AnalysisJobRepository(heartbeat_session)
                    refreshed = jobs.heartbeat_processing_job(
                        job_id=self._job_id,
                        claimed_attempt=self._claimed_attempt,
                    )

                    if refreshed:
                        heartbeat_session.commit()
                        continue

                    heartbeat_session.rollback()
                    self._ownership_lost.set()
                    self._stop_event.set()
                    return

            except Exception:
                # Retry a transient database error on the next interval.
                logger.exception(
                    "Heartbeat failed for analysis job %s attempt %s",
                    self._job_id,
                    self._claimed_attempt,
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
            "The recovery task can retry dispatch."
        )
        self.job_id = job_id


class AnalysisWorkerService:
    """Claim, process, and atomically finalise analysis jobs.

    The database repository owns job-state and finding-integrity rules.
    This service owns orchestration and transaction boundaries.

    Failed attempts are requeued up to max_attempts. Dispatch of each retry
    uses a persisted lease to coordinate with recovery dispatch.
    """

    def __init__(
        self,
        session: Session,
        version_loader: SubmissionVersionLoader,
        pipeline: AnalysisPipeline,
        queue: AnalysisJobQueue,
        max_attempts: int = 3,
        heartbeat_session_factory: HeartbeatSessionFactory | None = None,
        heartbeat_interval_seconds: float = 60.0,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")

        if heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds must be positive.")

        self._session = session
        self._jobs = AnalysisJobRepository(session)
        self._version_loader = version_loader
        self._pipeline = pipeline
        self._queue = queue
        self._max_attempts = max_attempts
        self._heartbeat_session_factory = heartbeat_session_factory
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

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

        heartbeat = None

        if self._heartbeat_session_factory is not None:
            heartbeat = _WorkerHeartbeat(
                session_factory=self._heartbeat_session_factory,
                job_id=job_id,
                claimed_attempt=claimed_attempt,
                interval_seconds=self._heartbeat_interval_seconds,
            )
            heartbeat.start()

        try:
            try:
                loaded_version = (
                    self._version_loader.load_submission_version(
                        organization_id=organization_id,
                        submission_version_id=submission_version_id,
                    )
                )

                # Reject cross-organisation or wrong-version data.
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

                # Never persist a report against another job or version.
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

                # Do not persist results if the heartbeat has lost ownership.
                if heartbeat is not None and heartbeat.ownership_lost:
                    self._session.rollback()
                    return WorkerResult(
                        job_id=job_id,
                        status="stale",
                        attempts=claimed_attempt,
                    )

                persisted_findings = map_findings_for_persistence(
                    list(response.findings)
                )

                # The repository atomically stores findings and finalises the
                # job, updating submission state only if this version is current.
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

        finally:
            if heartbeat is not None:
                heartbeat.stop()

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

                # Commit the queued state before trying to publish a message.
                self._session.commit()

            except Exception:
                self._session.rollback()
                raise

            try:
                enqueue_with_dispatch_lease(
                    session=self._session,
                    jobs=self._jobs,
                    queue=self._queue,
                    job_id=job_id,
                )

            except Exception as exc:
                raise AnalysisQueueDispatchError(job_id) from exc

            # A false return means another dispatcher owns the lease (or the
            # job changed state). The durable queued record remains recoverable.
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