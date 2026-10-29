
"""Celery tasks for BrandGuard AI analysis jobs."""

from uuid import UUID

from app.infrastructure.db.session import get_session_factory
from app.services.analysis_recovery_service import AnalysisRecoveryService
from app.services.analysis_worker_factory import (
    build_analysis_worker_service,
)
from app.workers.celery_app import celery_app


ANALYSIS_TASK_NAME = "app.workers.analysis_tasks.process_analysis_job"
RECOVERY_TASK_NAME = "app.workers.analysis_tasks.recover_stale_analysis_jobs"
ANALYSIS_QUEUE_NAME = "analysis"


class CeleryAnalysisJobQueue:
    """Dispatch analysis jobs through the configured Celery broker."""

    def enqueue_analysis(self, job_id: UUID) -> None:
        """Publish a job ID to the dedicated analysis queue.

        PostgreSQL remains the source of truth for job state.
        Queue messages contain only the job identifier.
        """
        celery_app.send_task(
            ANALYSIS_TASK_NAME,
            args=[str(job_id)],
            queue=ANALYSIS_QUEUE_NAME,
        )


@celery_app.task(
    name=ANALYSIS_TASK_NAME,
    acks_late=True,
)
def process_analysis_job(job_id: str) -> dict[str, str]:
    """Run one analysis job using the persisted job record.

    The worker service handles atomic claiming, duplicate delivery,
    retries, and finalisation. An unclaimed duplicate is returned
    without performing analysis again.

    The worker factory configures the OpenAI claim extractor when
    OPENAI_API_KEY is available. Without the key, claim extraction
    remains unavailable. Unavailable checks must never be reported
    as passing.

    Claim extraction does not establish factual truth. End-to-end
    factual verification remains incomplete until approved database
    facts can be mapped to structured comparison values.
    """
    parsed_job_id = UUID(job_id)
    session_factory = get_session_factory()

    with session_factory() as session:
        queue = CeleryAnalysisJobQueue()

        worker = build_analysis_worker_service(
            session,
            queue,
            heartbeat_session_factory=session_factory,
        )

        result = worker.process_job(parsed_job_id)

        result_status = getattr(
            result.status,
            "value",
            result.status,
        )

        return {
            "job_id": str(result.job_id),
            "status": str(result_status),
        }


@celery_app.task(name=RECOVERY_TASK_NAME)
def recover_stale_analysis_jobs() -> dict[str, int]:
    """Recover stale processing jobs and queued jobs without a live lease.

    This task is triggered periodically by Celery Beat. Recovery state changes
    and dispatch leases are guarded by conditional repository operations.
    """
    session_factory = get_session_factory()

    with session_factory() as session:
        recovery = AnalysisRecoveryService(
            session=session,
            queue=CeleryAnalysisJobQueue(),
        )
        result = recovery.run_once()
        return result.as_dict()
