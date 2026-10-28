
"""Composition factory for the database-backed analysis worker."""

import os

from sqlalchemy.orm import Session

from app.infrastructure.db.submission_version_loader import (
    DatabaseSubmissionVersionLoader,
)
from app.services.analysis_pipeline_factory import (
    build_database_analysis_pipeline,
)
from app.services.analysis_worker_service import (
    AnalysisJobQueue,
    AnalysisWorkerService,
    HeartbeatSessionFactory,
)
from app.services.database_analysis_pipeline import ClaimExtractor


def build_analysis_worker_service(
    session: Session,
    queue: AnalysisJobQueue,
    *,
    claim_extractor: ClaimExtractor | None = None,
    max_attempts: int = 3,
    heartbeat_session_factory: HeartbeatSessionFactory | None = None,
    heartbeat_interval_seconds: float = 60.0,
) -> AnalysisWorkerService:
    """Build a worker with database loading and analysis dependencies."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    # Preserve explicit injection for tests and alternate providers.
    # Enable OpenAI extraction only when a key is configured.
    if claim_extractor is None and os.getenv("OPENAI_API_KEY", "").strip():
        from app.analysis.openai_claim_provider import (
            build_openai_claim_extractor,
        )

        claim_extractor = build_openai_claim_extractor()

    submission_loader = DatabaseSubmissionVersionLoader(session)

    pipeline = build_database_analysis_pipeline(
        session,
        claim_extractor=claim_extractor,
    )

    return AnalysisWorkerService(
        session,
        submission_loader,
        pipeline,
        queue,
        max_attempts=max_attempts,
        heartbeat_session_factory=heartbeat_session_factory,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
