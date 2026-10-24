from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import app.services.analysis_worker_service as worker_module
from app.services.analysis_worker_service import (
    AnalysisQueueDispatchError,
    AnalysisWorkerService,
    LoadedSubmissionVersion,
)


def build_worker(monkeypatch, attempts=1, status="completed"):
    session = MagicMock()
    jobs = MagicMock()
    queue = MagicMock()
    loader = MagicMock()
    pipeline = MagicMock()

    organization_id = uuid4()
    job_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()

    job = SimpleNamespace(
        id=job_id,
        organization_id=organization_id,
        submission_version_id=version_id,
        requested_checks={"terminology": True},
        attempts=attempts,
    )

    loaded_version = LoadedSubmissionVersion(
        organization_id=organization_id,
        submission_version_id=version_id,
        submission_id=submission_id,
        version_number=1,
        content_text="Our product is cheap.",
    )

    jobs.claim_queued_job.return_value = job
    loader.load_submission_version.return_value = loaded_version

    pipeline.analyze.return_value = SimpleNamespace(
        job_id=job_id,
        submission_id=submission_id,
        submission_version_id=version_id,
        status=status,
        findings=[],
    )

    jobs.persist_findings_and_finish_job.return_value = True
    jobs.update_job_status.return_value = SimpleNamespace(
        id=job_id,
        status="queued",
    )

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
        "loader": loader,
        "pipeline": pipeline,
        "organization_id": organization_id,
        "job_id": job_id,
        "submission_id": submission_id,
        "version_id": version_id,
    }


@pytest.mark.parametrize("status", ["completed", "partial"])
def test_successful_analysis_persists_and_finalises_job(
    monkeypatch,
    status,
):
    ctx = build_worker(monkeypatch, status=status)

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.job_id == ctx["job_id"]
    assert result.status == status
    assert result.attempts == 1
    assert result.finding_count == 0
    assert result.retry_scheduled is False

    ctx["jobs"].claim_queued_job.assert_called_once_with(
        ctx["job_id"]
    )

    ctx["loader"].load_submission_version.assert_called_once_with(
        organization_id=ctx["organization_id"],
        submission_version_id=ctx["version_id"],
    )

    ctx["pipeline"].analyze.assert_called_once()

    ctx["jobs"].persist_findings_and_finish_job.assert_called_once_with(
        organization_id=ctx["organization_id"],
        job_id=ctx["job_id"],
        submission_version_id=ctx["version_id"],
        claimed_attempt=1,
        findings=[],
        final_status=status,
        submission_status="under_review",
    )

    # One commit for claiming the job, one for final persistence.
    assert ctx["session"].commit.call_count == 2
    ctx["session"].rollback.assert_not_called()


def test_duplicate_delivery_does_not_run_pipeline(monkeypatch):
    ctx = build_worker(monkeypatch)
    ctx["jobs"].claim_queued_job.return_value = None

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "not_claimed"
    ctx["pipeline"].analyze.assert_not_called()
    ctx["loader"].load_submission_version.assert_not_called()
    ctx["jobs"].persist_findings_and_finish_job.assert_not_called()
    ctx["session"].rollback.assert_called_once()


def test_stale_finalisation_does_not_report_success(monkeypatch):
    ctx = build_worker(monkeypatch)
    ctx["jobs"].persist_findings_and_finish_job.return_value = False

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "stale"
    assert result.attempts == 1

    # Only the claim is committed; stale finalisation is rolled back.
    assert ctx["session"].commit.call_count == 1
    ctx["session"].rollback.assert_called_once()


def test_cross_organisation_version_is_not_analysed(monkeypatch):
    ctx = build_worker(monkeypatch)

    ctx["loader"].load_submission_version.return_value = (
        LoadedSubmissionVersion(
            organization_id=uuid4(),
            submission_version_id=ctx["version_id"],
            submission_id=ctx["submission_id"],
            version_number=1,
            content_text="Content from the wrong organisation.",
        )
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "queued"
    assert result.retry_scheduled is True

    ctx["pipeline"].analyze.assert_not_called()
    ctx["jobs"].update_job_status.assert_called_once_with(
        organization_id=ctx["organization_id"],
        job_id=ctx["job_id"],
        expected_status="processing",
        new_status="queued",
        error_code="ANALYSIS_ATTEMPT_FAILED",
        error_message=(
            "An analysis attempt failed. "
            "The job is scheduled for retry."
        ),
        claimed_attempt=1,
    )

    ctx["queue"].enqueue_analysis.assert_called_once_with(
        ctx["job_id"]
    )


def test_pipeline_failure_requeues_job(monkeypatch):
    ctx = build_worker(monkeypatch)

    ctx["pipeline"].analyze.side_effect = RuntimeError(
        "Simulated analysis failure"
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "queued"
    assert result.retry_scheduled is True
    assert result.attempts == 1

    ctx["session"].rollback.assert_called_once()
    ctx["jobs"].update_job_status.assert_called_once()
    ctx["queue"].enqueue_analysis.assert_called_once_with(
        ctx["job_id"]
    )


def test_exhausted_attempts_mark_job_failed(monkeypatch):
    ctx = build_worker(monkeypatch, attempts=3)

    ctx["pipeline"].analyze.side_effect = RuntimeError(
        "Simulated persistent failure"
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "failed"
    assert result.attempts == 3
    assert result.retry_scheduled is False

    ctx["jobs"].update_job_status.assert_not_called()

    ctx["jobs"].persist_findings_and_finish_job.assert_called_once_with(
        organization_id=ctx["organization_id"],
        job_id=ctx["job_id"],
        submission_version_id=ctx["version_id"],
        claimed_attempt=3,
        findings=[],
        final_status="failed",
        error_code="ANALYSIS_FAILED",
        error_message=(
            "Analysis could not be completed after the "
            "allowed attempts."
        ),
        submission_status="failed_needs_attention",
    )

    ctx["session"].commit.assert_called()
    ctx["queue"].enqueue_analysis.assert_not_called()


def test_retry_queue_failure_reports_job_id(monkeypatch):
    ctx = build_worker(monkeypatch)

    ctx["pipeline"].analyze.side_effect = RuntimeError(
        "Simulated analysis failure"
    )
    ctx["queue"].enqueue_analysis.side_effect = RuntimeError(
        "Simulated queue outage"
    )

    with pytest.raises(AnalysisQueueDispatchError) as exc_info:
        ctx["worker"].process_job(ctx["job_id"])

    assert exc_info.value.job_id == ctx["job_id"]

    # The job was committed back to queued before dispatch.
    ctx["jobs"].update_job_status.assert_called_once()
    ctx["session"].commit.assert_called()


def test_mismatched_pipeline_job_is_not_persisted(monkeypatch):
    ctx = build_worker(monkeypatch)

    ctx["pipeline"].analyze.return_value = SimpleNamespace(
        job_id=uuid4(),
        submission_id=ctx["submission_id"],
        submission_version_id=ctx["version_id"],
        status="completed",
        findings=[],
    )

    result = ctx["worker"].process_job(ctx["job_id"])

    assert result.status == "queued"
    assert result.retry_scheduled is True

    ctx["jobs"].persist_findings_and_finish_job.assert_not_called()
    ctx["jobs"].update_job_status.assert_called_once()


def test_retry_limit_must_be_positive(monkeypatch):
    session = MagicMock()
    loader = MagicMock()
    pipeline = MagicMock()
    queue = MagicMock()

    monkeypatch.setattr(
        worker_module,
        "AnalysisJobRepository",
        lambda _session: MagicMock(),
    )

    with pytest.raises(
        ValueError,
        match="max_attempts must be at least 1",
    ):
        AnalysisWorkerService(
            session=session,
            version_loader=loader,
            pipeline=pipeline,
            queue=queue,
            max_attempts=0,
        )