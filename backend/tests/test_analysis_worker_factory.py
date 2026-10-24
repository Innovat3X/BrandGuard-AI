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