"""Periodic recovery orchestration for stale analysis jobs.

Persistence and concurrency guarantees live in ``AnalysisJobRepository``.
This service coordinates bounded candidate scans, conditional state changes,
and queue publication. It never holds a database transaction open while it
publishes to the broker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.services.analysis_worker_service import AnalysisJobQueue


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryRunResult:
    """Counters for one bounded recovery scan."""

    stale_processing_recovered: int = 0
    stale_processing_failed: int = 0
    queued_jobs_dispatched: int = 0
    dispatch_failures: int = 0
    skipped_due_to_race: int = 0
    errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class AnalysisRecoveryService:
    """Recover stale processing jobs and queued jobs lacking a live lease.

    Expected repository contracts (implemented by the persistence owner):

    * ``list_stale_processing_jobs(stale_before, limit)`` returns bounded
      ``AnalysisJob`` candidates whose heartbeat is older than the cutoff.
    * ``recover_stale_processing_job(...)`` conditionally changes a job only
      if it is still processing, has the expected attempt, and its heartbeat
      remains older than the cutoff. It returns ``bool`` and is responsible
      for atomically updating the submission when a job becomes terminal.
    * ``list_queued_jobs_for_recovery(limit)`` returns bounded queued jobs
      whose dispatch lease is absent or expired.
    * ``acquire_dispatch_lease(...)`` and ``release_dispatch_lease(...)`` are
      conditional and return ``bool``. Only the lease owner can release it.

    A queued-job listing deliberately does not impose the processing heartbeat
    cutoff: an absent lease is recoverable on the next scan, while an active
    lease protects an in-flight publish. Successful publishes retain the
    lease until a worker claims the job or the lease expires.
    """

    def __init__(
        self,
        session: Session,
        queue: AnalysisJobQueue,
        *,
        max_attempts: int = 3,
        stale_after_seconds: float = 300.0,
        dispatch_lease_seconds: float = 300.0,
        batch_size: int = 100,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive.")
        if dispatch_lease_seconds <= 0:
            raise ValueError("dispatch_lease_seconds must be positive.")
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1.")

        self._session = session
        self._jobs = AnalysisJobRepository(session)
        self._queue = queue
        self._max_attempts = max_attempts
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._dispatch_lease = timedelta(seconds=dispatch_lease_seconds)
        self._batch_size = batch_size
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run_once(self) -> RecoveryRunResult:
        """Run one bounded recovery scan.

        Jobs transitioned from processing to queued are dispatched in this
        pass and excluded from the queued-candidate pass, preventing duplicate
        dispatch attempts during a single scan.
        """

        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("The recovery clock must return a timezone-aware datetime.")
        stale_before = now - self._stale_after

        stale_processing_recovered = 0
        stale_processing_failed = 0
        queued_jobs_dispatched = 0
        dispatch_failures = 0
        skipped_due_to_race = 0
        errors = 0
        visited_ids: set[UUID] = set()

        try:
            processing_candidates = self._jobs.list_stale_processing_jobs(
                stale_before=stale_before,
                limit=self._batch_size,
            )
        except Exception:
            self._session.rollback()
            logger.exception("Could not list stale processing analysis jobs")
            return RecoveryRunResult(errors=1)

        for candidate in processing_candidates:
            job_id = candidate.id
            expected_attempt = candidate.attempts
            visited_ids.add(job_id)

            try:
                changed = self._jobs.recover_stale_processing_job(
                    job_id=job_id,
                    expected_attempt=expected_attempt,
                    stale_before=stale_before,
                    max_attempts=self._max_attempts,
                )
                if not changed:
                    self._session.rollback()
                    skipped_due_to_race += 1
                    continue

                # The state transition and any submission-status update are
                # committed atomically before dispatching to the broker.
                self._session.commit()
            except Exception:
                self._session.rollback()
                logger.exception("Failed to recover stale job %s", job_id)
                errors += 1
                continue

            if expected_attempt >= self._max_attempts:
                stale_processing_failed += 1
                continue

            stale_processing_recovered += 1
            outcome = self._dispatch_queued_job(job_id, stale_before=None)
            if outcome == "dispatched":
                queued_jobs_dispatched += 1
            elif outcome == "failed":
                dispatch_failures += 1
            elif outcome == "error":
                errors += 1
            else:
                skipped_due_to_race += 1

        try:
            queued_candidates = self._jobs.list_queued_jobs_for_recovery(
                limit=self._batch_size,
            )
        except Exception:
            self._session.rollback()
            logger.exception("Could not list queued analysis jobs for recovery")
            errors += 1
            queued_candidates = []

        for candidate in queued_candidates:
            job_id = candidate.id
            if job_id in visited_ids:
                continue
            visited_ids.add(job_id)

            outcome = self._dispatch_queued_job(job_id, stale_before=None)
            if outcome == "dispatched":
                queued_jobs_dispatched += 1
            elif outcome == "failed":
                dispatch_failures += 1
            elif outcome == "error":
                errors += 1
            else:
                skipped_due_to_race += 1

        return RecoveryRunResult(
            stale_processing_recovered=stale_processing_recovered,
            stale_processing_failed=stale_processing_failed,
            queued_jobs_dispatched=queued_jobs_dispatched,
            dispatch_failures=dispatch_failures,
            skipped_due_to_race=skipped_due_to_race,
            errors=errors,
        )

    def _dispatch_queued_job(
        self,
        job_id: UUID,
        *,
        stale_before: datetime | None,
    ) -> str:
        """Lease, publish, and release only the caller's failed lease."""

        lease_token = uuid4()
        try:
            acquired = self._jobs.acquire_dispatch_lease(
                job_id=job_id,
                lease_token=lease_token,
                lease_expires_at=self._clock() + self._dispatch_lease,
                stale_before=stale_before,
            )
            if not acquired:
                self._session.rollback()
                return "skipped"
            self._session.commit()
        except Exception:
            self._session.rollback()
            logger.exception("Could not acquire dispatch lease for job %s", job_id)
            return "error"

        try:
            self._queue.enqueue_analysis(job_id)
            # Keep the lease until the worker claims the job, or it expires.
            return "dispatched"
        except Exception:
            logger.exception("Failed to dispatch queued analysis job %s", job_id)
            self._session.rollback()
            try:
                released = self._jobs.release_dispatch_lease(
                    job_id=job_id,
                    lease_token=lease_token,
                )
                if released:
                    self._session.commit()
                else:
                    self._session.rollback()
            except Exception:
                self._session.rollback()
                logger.exception(
                    "Could not release failed dispatch lease for job %s",
                    job_id,
                )
                return "error"
            return "failed"
