from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import app.services.analysis_recovery_service as recovery_module
from app.services.analysis_recovery_service import AnalysisRecoveryService


FIXED_NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def build_recovery(monkeypatch, *, attempts=1, max_attempts=3):
    session = MagicMock()
    jobs = MagicMock()
    queue = MagicMock()
    processing_job = SimpleNamespace(id=uuid4(), attempts=attempts)

    jobs.list_stale_processing_jobs.return_value = [processing_job]
    jobs.list_queued_jobs_for_recovery.return_value = []
    jobs.recover_stale_processing_job.return_value = True
    jobs.acquire_dispatch_lease.return_value = True
    jobs.release_dispatch_lease.return_value = True

    monkeypatch.setattr(
        recovery_module,
        "AnalysisJobRepository",
        lambda _session: jobs,
    )

    service = AnalysisRecoveryService(
        session=session,
        queue=queue,
        max_attempts=max_attempts,
        stale_after_seconds=300,
        dispatch_lease_seconds=300,
        batch_size=25,
        clock=lambda: FIXED_NOW,
    )
    return {
        "service": service,
        "session": session,
        "jobs": jobs,
        "queue": queue,
        "processing_job": processing_job,
    }


def test_stale_processing_job_is_conditionally_recovered_and_dispatched(monkeypatch):
    ctx = build_recovery(monkeypatch, attempts=1)

    result = ctx["service"].run_once()

    assert result.stale_processing_recovered == 1
    assert result.stale_processing_failed == 0
    assert result.queued_jobs_dispatched == 1
    assert result.dispatch_failures == 0

    ctx["jobs"].list_stale_processing_jobs.assert_called_once_with(
        stale_before=FIXED_NOW - timedelta(seconds=300),
        limit=25,
    )
    ctx["jobs"].recover_stale_processing_job.assert_called_once_with(
        job_id=ctx["processing_job"].id,
        expected_attempt=1,
        stale_before=FIXED_NOW - timedelta(seconds=300),
        max_attempts=3,
    )
    ctx["jobs"].acquire_dispatch_lease.assert_called_once()
    ctx["queue"].enqueue_analysis.assert_called_once_with(
        ctx["processing_job"].id
    )


def test_exhausted_stale_processing_job_is_failed_without_redispatch(monkeypatch):
    ctx = build_recovery(monkeypatch, attempts=3, max_attempts=3)

    result = ctx["service"].run_once()

    assert result.stale_processing_recovered == 0
    assert result.stale_processing_failed == 1
    assert result.queued_jobs_dispatched == 0
    ctx["jobs"].acquire_dispatch_lease.assert_not_called()
    ctx["queue"].enqueue_analysis.assert_not_called()


def test_recovery_race_skips_job_if_repository_recheck_fails(monkeypatch):
    ctx = build_recovery(monkeypatch, attempts=1)
    ctx["jobs"].recover_stale_processing_job.return_value = False

    result = ctx["service"].run_once()

    assert result.stale_processing_recovered == 0
    assert result.skipped_due_to_race == 1
    ctx["session"].rollback.assert_called_once()
    ctx["jobs"].acquire_dispatch_lease.assert_not_called()
    ctx["queue"].enqueue_analysis.assert_not_called()


def test_queued_job_without_lease_is_dispatched(monkeypatch):
    ctx = build_recovery(monkeypatch)
    ctx["jobs"].list_stale_processing_jobs.return_value = []
    queued_job = SimpleNamespace(id=uuid4(), attempts=0)
    ctx["jobs"].list_queued_jobs_for_recovery.return_value = [queued_job]

    result = ctx["service"].run_once()

    assert result.queued_jobs_dispatched == 1
    ctx["jobs"].acquire_dispatch_lease.assert_called_once_with(
        job_id=queued_job.id,
        lease_token=ctx["jobs"].acquire_dispatch_lease.call_args.kwargs["lease_token"],
        lease_expires_at=FIXED_NOW + timedelta(seconds=300),
        stale_before=None,
    )
    ctx["queue"].enqueue_analysis.assert_called_once_with(queued_job.id)


def test_failed_publish_releases_only_the_acquired_lease(monkeypatch):
    ctx = build_recovery(monkeypatch)
    ctx["jobs"].list_stale_processing_jobs.return_value = []
    queued_job = SimpleNamespace(id=uuid4(), attempts=0)
    ctx["jobs"].list_queued_jobs_for_recovery.return_value = [queued_job]
    ctx["queue"].enqueue_analysis.side_effect = RuntimeError("broker unavailable")

    result = ctx["service"].run_once()

    assert result.dispatch_failures == 1
    lease_token = ctx["jobs"].acquire_dispatch_lease.call_args.kwargs["lease_token"]
    ctx["jobs"].release_dispatch_lease.assert_called_once_with(
        job_id=queued_job.id,
        lease_token=lease_token,
    )
    ctx["session"].commit.assert_called()
    ctx["session"].rollback.assert_called()


def test_unavailable_dispatch_lease_prevents_duplicate_publish(monkeypatch):
    ctx = build_recovery(monkeypatch)
    ctx["jobs"].list_stale_processing_jobs.return_value = []
    queued_job = SimpleNamespace(id=uuid4(), attempts=0)
    ctx["jobs"].list_queued_jobs_for_recovery.return_value = [queued_job]
    ctx["jobs"].acquire_dispatch_lease.return_value = False

    result = ctx["service"].run_once()

    assert result.queued_jobs_dispatched == 0
    assert result.skipped_due_to_race == 1
    ctx["queue"].enqueue_analysis.assert_not_called()


def test_invalid_recovery_configuration_is_rejected():
    with pytest.raises(ValueError):
        AnalysisRecoveryService(MagicMock(), MagicMock(), batch_size=0)
