"""Tests for Celery analysis task dispatch and execution."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from app.workers.analysis_tasks import (
    ANALYSIS_QUEUE_NAME,
    ANALYSIS_TASK_NAME,
    CeleryAnalysisJobQueue,
    process_analysis_job,
)


def test_queue_dispatches_job_id_to_analysis_queue(monkeypatch):
    job_id = uuid4()
    send_task = Mock()

    monkeypatch.setattr(
        "app.workers.analysis_tasks.celery_app.send_task",
        send_task,
    )

    queue = CeleryAnalysisJobQueue()
    queue.enqueue_analysis(job_id)

    send_task.assert_called_once_with(
        ANALYSIS_TASK_NAME,
        args=[str(job_id)],
        queue=ANALYSIS_QUEUE_NAME,
    )


def test_task_invokes_worker_and_returns_job_status(monkeypatch):
    job_id = uuid4()
    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    session_factory = Mock(return_value=session_context)
    get_factory = Mock(return_value=session_factory)

    monkeypatch.setattr(
        "app.workers.analysis_tasks.get_session_factory",
        get_factory,
    )

    worker = Mock()
    worker.process_job.return_value = SimpleNamespace(
        job_id=job_id,
        status="completed",
    )

    build_worker = Mock(return_value=worker)

    monkeypatch.setattr(
        "app.workers.analysis_tasks.build_analysis_worker_service",
        build_worker,
    )

    result = process_analysis_job.run(str(job_id))

    get_factory.assert_called_once_with()
    session_factory.assert_called_once_with()

    build_worker.assert_called_once()
    args, kwargs = build_worker.call_args

    assert args[0] is session
    assert isinstance(args[1], CeleryAnalysisJobQueue)
    assert kwargs == {}

    worker.process_job.assert_called_once_with(job_id)

    assert result == {
        "job_id": str(job_id),
        "status": "completed",
    }

    session_context.__exit__.assert_called_once_with(
        None,
        None,
        None,
    )


def test_task_returns_partial_status(monkeypatch):
    job_id = uuid4()
    session = MagicMock()
    session_context = MagicMock()
    session_context.__enter__.return_value = session

    monkeypatch.setattr(
        "app.workers.analysis_tasks.get_session_factory",
        lambda: Mock(return_value=session_context),
    )

    worker = Mock()
    worker.process_job.return_value = SimpleNamespace(
        job_id=job_id,
        status="partial",
    )

    monkeypatch.setattr(
        "app.workers.analysis_tasks.build_analysis_worker_service",
        Mock(return_value=worker),
    )

    result = process_analysis_job.run(str(job_id))

    assert result == {
        "job_id": str(job_id),
        "status": "partial",
    }


def test_invalid_job_id_is_rejected_before_database_access(monkeypatch):
    get_factory = Mock()

    monkeypatch.setattr(
        "app.workers.analysis_tasks.get_session_factory",
        get_factory,
    )

    with pytest.raises(ValueError):
        process_analysis_job.run("not-a-valid-uuid")

    get_factory.assert_not_called()