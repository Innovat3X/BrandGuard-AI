"""Celery tasks for BrandGuard AI analysis jobs."""

from uuid import UUID

from app.infrastructure.db.session import get_session_factory
from app.services.analysis_worker_factory import (
    build_analysis_worker_service,
)
from app.workers.celery_app import celery_app


ANALYSIS_TASK_NAME = "app.workers.analysis_tasks.process_analysis_job"
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

    Claim extraction is intentionally not configured until a real
    extractor is available. The analysis pipeline must represent
    unavailable checks as unavailable, not as passing.
    """

    parsed_job_id = UUID(job_id)
    session_factory = get_session_factory()

    with session_factory() as session:
        queue = CeleryAnalysisJobQueue()

        worker = build_analysis_worker_service(
            session,
            queue,
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