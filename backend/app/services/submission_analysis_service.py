"""Application orchestration for text submissions and job dispatch.

Authenticated API routes must supply organisation and actor identifiers
from trusted server-side context, never from an untrusted request body.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.repositories.analysis_job_repository import (
    AnalysisJobRepository,
)
from app.infrastructure.db.repositories.submission_repository import (
    SubmissionRepository,
)
from app.services.analysis_dispatch import (
    enqueue_with_dispatch_lease,
)


class AnalysisJobQueue(Protocol):
    """Interface for the analysis queue adapter."""

    def enqueue_analysis(self, job_id: UUID) -> None:
        """Publish a message containing the persisted analysis-job ID."""
        ...


@dataclass(frozen=True)
class CreatedTextSubmission:
    submission_id: UUID
    submission_version_id: UUID
    version_number: int
    status: str
    sha256: str


@dataclass(frozen=True)
class RequestedAnalysisJob:
    job_id: UUID
    submission_id: UUID
    submission_version_id: UUID
    version_number: int
    status: str


class AnalysisQueueDispatchError(RuntimeError):
    """Raised when a persisted job cannot be dispatched to the queue."""

    def __init__(self, job_id: UUID, message: str) -> None:
        super().__init__(message)
        self.job_id = job_id


class SubmissionAnalysisService:
    """Coordinate submissions, persistence, and analysis-job dispatch.

    Repositories do not commit transactions themselves. This service
    owns transaction boundaries.

    The submission and job are committed before queue dispatch. Dispatch
    obtains a persisted lease before publishing to the broker.
    """

    def __init__(
        self,
        session: Session,
        queue: AnalysisJobQueue,
    ) -> None:
        self._session = session
        self._submissions = SubmissionRepository(session)
        self._analysis_jobs = AnalysisJobRepository(session)
        self._queue = queue

    def create_text_submission(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        title: str,
        text: str,
    ) -> CreatedTextSubmission:
        """Persist a submission and its immutable first version."""

        cleaned_title = title.strip()

        if not cleaned_title:
            raise ValueError("Submission title must not be empty.")

        if not text.strip():
            raise ValueError("Submission text must not be empty.")

        content_hash = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

        try:
            submission = self._submissions.create_submission(
                organization_id=organization_id,
                title=cleaned_title,
                created_by=actor_id,
            )

            version = self._submissions.create_submission_version(
                organization_id=organization_id,
                submission_id=submission.id,
                version_number=1,
                source_type="text",
                original_text=text,
                extracted_text=text,
                sha256=content_hash,
                created_by=actor_id,
            )

            self._session.commit()

        except Exception:
            self._session.rollback()
            raise

        return CreatedTextSubmission(
            submission_id=submission.id,
            submission_version_id=version.id,
            version_number=version.version_number,
            status=submission.status,
            sha256=content_hash,
        )

    def request_analysis(
        self,
        *,
        organization_id: UUID,
        submission_id: UUID,
        idempotency_key: str,
        requested_checks: (
            dict[str, Any] | list[Any] | None
        ) = None,
        version_number: int | None = None,
    ) -> RequestedAnalysisJob:
        """Create or retrieve an idempotent job and dispatch it safely."""

        if not idempotency_key.strip():
            raise ValueError("Idempotency key must not be empty.")

        try:
            submission = self._submissions.get_submission(
                organization_id=organization_id,
                submission_id=submission_id,
            )

            if submission is None:
                raise LookupError(
                    "Submission not found in this organization."
                )

            selected_version_number = (
                submission.current_version_number
                if version_number is None
                else version_number
            )

            if selected_version_number < 1:
                raise ValueError(
                    "version_number must be a positive integer."
                )

            version = self._submissions.get_submission_version(
                organization_id=organization_id,
                submission_id=submission_id,
                version_number=selected_version_number,
            )

            if version is None:
                raise LookupError(
                    "Submission version not found in this organization."
                )

            job = self._analysis_jobs.create_or_get_analysis_job(
                organization_id=organization_id,
                submission_version_id=version.id,
                idempotency_key=idempotency_key,
                requested_checks=requested_checks,
            )

            # The job is durable before attempting external dispatch.
            self._session.commit()

        except Exception:
            self._session.rollback()
            raise

        if job.status == "queued":
            try:
                enqueue_with_dispatch_lease(
                    session=self._session,
                    jobs=self._analysis_jobs,
                    queue=self._queue,
                    job_id=job.id,
                )

            except Exception as exc:
                raise AnalysisQueueDispatchError(
                    job_id=job.id,
                    message=(
                        "The analysis job was saved, but queue dispatch "
                        "failed. Retry using the same idempotency key. "
                        "The recovery task can retry dispatch while the "
                        "job remains queued."
                    ),
                ) from exc

        return RequestedAnalysisJob(
            job_id=job.id,
            submission_id=submission.id,
            submission_version_id=version.id,
            version_number=version.version_number,
            status=job.status,
        )