"""Lease-protected dispatch for queued analysis jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)


logger = logging.getLogger(__name__)

DISPATCH_LEASE_SECONDS = 300.0


class AnalysisDispatchQueue(Protocol):
    """Queue adapter used to publish analysis-job identifiers."""

    def enqueue_analysis(self, job_id: UUID) -> None:
        """Publish a persisted analysis-job identifier."""
        ...


def enqueue_with_dispatch_lease(
    *,
    session: Session,
    jobs: AnalysisJobRepository,
    queue: AnalysisDispatchQueue,
    job_id: UUID,
) -> bool:
    """Acquire a lease and publish a queued job.

    Returns:
        True if the job was published.
        False if another dispatcher owns the lease or the job is no
        longer eligible for dispatch.

    If publication raises an exception, this function attempts to release
    only the lease acquired by this invocation. The queued job remains
    persisted so that recovery can retry dispatch.
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
            session.rollback()
            return False

        # The lease must be committed before publishing to the broker.
        session.commit()

    except Exception:
        session.rollback()
        raise

    try:
        queue.enqueue_analysis(job_id)
        # Keep the lease until the worker claims the job, or it expires.
        return True

    except Exception:
        # The queued job remains durable. Start a fresh transaction to
        # release our lease, if the lease still belongs to this invocation.
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

        # Preserve the original queue-publication exception.
        raise