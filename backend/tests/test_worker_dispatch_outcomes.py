from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import app.services.analysis_worker_service as worker_module
from app.services.analysis_worker_service import (
    AnalysisWorkerService,
    LoadedSubmissionVersion,
)


def build_failing_worker(monkeypatch, dispatch_state):
    session = MagicMock()
    jobs = MagicMock()
    queue = MagicMock()
    loader = MagicMock()
    pipeline = MagicMock()

    organization_id = uuid4()
    job_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()

    jobs.claim_queued_job.return_value = SimpleNamespace(
        id=job_id,
        organization_id=organization_id,
        submission_version_id=version_id,
        requested_checks={"terminology": True},
        attempts=1,
    )
    jobs.update_job_status.return_value = SimpleNamespace(
        id=job_id,
        status="queued",
    )
    jobs.acquire_dispatch_lease.return_value = False

    loader.load_submission_version.return_value = LoadedSubmissionVersion(
        organization_id=organization_id,
        submission_version_id=version_id,
        submission_id=submission_id,
        version_number=1,
        content_text="Sample analysis input.",
    )

    pipeline.analyze.side_effect = RuntimeError("Simulated analysis failure")

    # The helper queries the persisted job and lease state after acquisition
    # fails. A three-item tuple represents status, lease token, live-lease flag.
    session.execute.return_value.one_or_none.return_value = dispatch_state

    monkeypatch.setattr(
        worker_module,
        "AnalysisJobRepository",
        lambda _session: jobs,
    )

    worker = AnalysisWorkerService(
        session=session,
        version_loader=loader,
        pipeline=pipeline,
        queue=queue,
        max_attempts=3,
    )

    return {
        "worker": worker,
        "session": session,
        "jobs": jobs,
        "queue": queue,
        "job_id": job_id,
    }


def test_worker_distinguishes_a_competing_live_lease(monkeypatch):
    ctx = build_failing_worker(
        monkeypatch,
        ("queued", "another-dispatcher-token", True),
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "queued"
    assert result.dispatch_outcome == "lease_unavailable"
    assert result.retry_scheduled is True

    ctx["jobs"].acquire_dispatch_lease.assert_called_once()
    ctx["queue"].enqueue_analysis.assert_not_called()
    ctx["jobs"].release_dispatch_lease.assert_not_called()


def test_worker_marks_job_stale_when_it_is_no_longer_eligible(monkeypatch):
    ctx = build_failing_worker(
        monkeypatch,
        ("processing", None, False),
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "stale"
    assert result.dispatch_outcome == "not_eligible"
    assert result.retry_scheduled is False

    ctx["jobs"].acquire_dispatch_lease.assert_called_once()
    ctx["queue"].enqueue_analysis.assert_not_called()
    ctx["jobs"].release_dispatch_lease.assert_not_called()


def test_worker_reports_retry_required_after_lease_expiry_race(monkeypatch):
    ctx = build_failing_worker(
        monkeypatch,
        ("queued", None, False),
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "queued"
    assert result.dispatch_outcome == "retry_required"
    assert result.retry_scheduled is False

    ctx["jobs"].acquire_dispatch_lease.assert_called_once()
    ctx["queue"].enqueue_analysis.assert_not_called()
    ctx["jobs"].release_dispatch_lease.assert_not_called()