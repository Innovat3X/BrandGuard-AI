"""Lease-protected dispatch for queued analysis jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.db.analysis_job import AnalysisJob
from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)


logger = logging.getLogger(__name__)

DISPATCH_LEASE_SECONDS = 300.0


class DispatchOutcome(str, Enum):
    """Outcome of attempting lease-protected job dispatch."""

    DISPATCHED = "dispatched"
    LEASE_UNAVAILABLE = "lease_unavailable"
    NOT_ELIGIBLE = "not_eligible"
    RETRY_REQUIRED = "retry_required"


class AnalysisDispatchQueue(Protocol):
    """Queue adapter used to publish analysis-job identifiers."""

    def enqueue_analysis(self, job_id: UUID) -> None:
        """Publish a persisted analysis-job identifier."""
        ...


def _classify_failed_acquisition(
    *,
    session: Session,
    job_id: UUID,
) -> DispatchOutcome:
    """Determine why a dispatch lease could not be acquired.

    This read follows the failed conditional UPDATE. PostgreSQL evaluates
    the lease expiration against its database clock to avoid comparing
    database timestamps to a potentially skewed application clock.
    """

    statement = (
        select(
            AnalysisJob.status,
            AnalysisJob.dispatch_lease_token,
            (
                AnalysisJob.dispatch_lease_expires_at > func.now()
            ).label("lease_is_live"),
        )
        .where(AnalysisJob.id == job_id)
    )

    row = session.execute(statement).one_or_none()

    if row is None:
        return DispatchOutcome.NOT_ELIGIBLE

    status, lease_token, lease_is_live = row

    if status != "queued":
        return DispatchOutcome.NOT_ELIGIBLE

    if lease_token is not None and bool(lease_is_live):
        return DispatchOutcome.LEASE_UNAVAILABLE

    # The row is still queued, but no live lease was visible after the
    # failed UPDATE. This can happen if a lease expires during the check.
    # Leave the durable job queued for the recovery service to retry.
    return DispatchOutcome.RETRY_REQUIRED


def enqueue_with_dispatch_lease(
    *,
    session: Session,
    jobs: AnalysisJobRepository,
    queue: AnalysisDispatchQueue,
    job_id: UUID,
) -> DispatchOutcome:
    """Acquire a dispatch lease and publish a queued job.

    DISPATCHED:
        This invocation acquired the lease and published the message.

    LEASE_UNAVAILABLE:
        The job remains queued and another dispatcher has a live lease.

    NOT_ELIGIBLE:
        The job is missing or is no longer queued.

    RETRY_REQUIRED:
        The job is still queued, but the failed acquisition could not be
        classified as a live competing lease. Recovery should try again.

    Publication failures raise the original exception after an attempt to
    release only the lease acquired by this invocation.
    """

    lease_token = uuid4()
    lease_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=DISPATCH_LEASE_SECONDS
    )

    try:
        acquired = jobs.acquire_dispatch_lease(
            job_id=job_id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
        )

        if not acquired:
            outcome = _classify_failed_acquisition(
                session=session,
                job_id=job_id,
            )
            session.rollback()
            return outcome

        # The lease must be committed before publishing to the broker.
        session.commit()

    except Exception:
        session.rollback()
        raise

    try:
        queue.enqueue_analysis(job_id)

        # Keep the lease until the worker claims the job or it expires.
        return DispatchOutcome.DISPATCHED

    except Exception:
        # The queued job remains durable. Start a new transaction to release
        # our lease, if the lease still belongs to this invocation.
        session.rollback()

        try:
            released = jobs.release_dispatch_lease(
                job_id=job_id,
                lease_token=lease_token,
            )

            if released:
                session.commit()
            else:
                session.rollback()

        except Exception:
            session.rollback()
            logger.exception(
                "Could not release failed dispatch lease for job %s",
                job_id,
            )

        # Preserve the queue-publication exception for the caller.
        raise