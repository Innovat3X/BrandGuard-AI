"""Tests for the database-backed analysis worker factory."""

from unittest.mock import patch

import pytest

from app.services.analysis_worker_factory import (
    build_analysis_worker_service,
)


def test_factory_wires_worker_dependencies():
    session = object()
    queue = object()
    claim_extractor = object()

    with (
        patch(
            "app.services.analysis_worker_factory."
            "DatabaseSubmissionVersionLoader"
        ) as loader_class,
        patch(
            "app.services.analysis_worker_factory."
            "build_database_analysis_pipeline"
        ) as pipeline_builder,
        patch(
            "app.services.analysis_worker_factory."
            "AnalysisWorkerService"
        ) as worker_class,
    ):
        loader = loader_class.return_value
        pipeline = pipeline_builder.return_value
        expected_worker = worker_class.return_value

        result = build_analysis_worker_service(
            session,
            queue,
            claim_extractor=claim_extractor,
            max_attempts=5,
        )

    loader_class.assert_called_once_with(session)

    pipeline_builder.assert_called_once_with(
        session,
        claim_extractor=claim_extractor,
    )

    worker_class.assert_called_once_with(
        session,
        loader,
        pipeline,
        queue,
        max_attempts=5,
        heartbeat_session_factory=None,
        heartbeat_interval_seconds=60.0,
    )

    assert result is expected_worker


def test_factory_uses_default_attempt_limit():
    session = object()
    queue = object()

    with (
        patch(
            "app.services.analysis_worker_factory."
            "DatabaseSubmissionVersionLoader"
        ) as loader_class,
        patch(
            "app.services.analysis_worker_factory."
            "build_database_analysis_pipeline"
        ) as pipeline_builder,
        patch(
            "app.services.analysis_worker_factory."
            "AnalysisWorkerService"
        ) as worker_class,
    ):
        build_analysis_worker_service(session, queue)

    worker_class.assert_called_once_with(
        session,
        loader_class.return_value,
        pipeline_builder.return_value,
        queue,
        max_attempts=3,
        heartbeat_session_factory=None,
        heartbeat_interval_seconds=60.0,
    )


@pytest.mark.parametrize("max_attempts", [0, -1])
def test_factory_rejects_invalid_attempt_limit(max_attempts):
    with pytest.raises(
        ValueError,
        match="max_attempts must be at least 1",
    ):
        build_analysis_worker_service(
            object(),
            object(),
            max_attempts=max_attempts,
        )

def test_factory_uses_openai_extractor_when_api_key_is_configured(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    session = object()
    queue = object()
    openai_extractor = object()

    with (
        patch(
            "app.analysis.openai_claim_provider.build_openai_claim_extractor",
            return_value=openai_extractor,
        ) as extractor_builder,
        patch(
            "app.services.analysis_worker_factory."
            "DatabaseSubmissionVersionLoader"
        ),
        patch(
            "app.services.analysis_worker_factory."
            "build_database_analysis_pipeline"
        ) as pipeline_builder,
        patch(
            "app.services.analysis_worker_factory.AnalysisWorkerService"
        ),
    ):
        build_analysis_worker_service(session, queue)

    extractor_builder.assert_called_once_with()
    pipeline_builder.assert_called_once_with(
        session,
        claim_extractor=openai_extractor,
    )


def test_explicit_extractor_takes_precedence_over_openai_configuration(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    session = object()
    queue = object()
    explicit_extractor = object()

    with (
        patch(
            "app.analysis.openai_claim_provider.build_openai_claim_extractor",
        ) as extractor_builder,
        patch(
            "app.services.analysis_worker_factory."
            "DatabaseSubmissionVersionLoader"
        ),
        patch(
            "app.services.analysis_worker_factory."
            "build_database_analysis_pipeline"
        ) as pipeline_builder,
        patch(
            "app.services.analysis_worker_factory.AnalysisWorkerService"
        ),
    ):
        build_analysis_worker_service(
            session,
            queue,
            claim_extractor=explicit_extractor,
        )

    extractor_builder.assert_not_called()
    pipeline_builder.assert_called_once_with(
        session,
        claim_extractor=explicit_extractor,
    )
