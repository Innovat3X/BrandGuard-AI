from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

import app.services.submission_analysis_service as service_module
from app.services.submission_analysis_service import (
    AnalysisQueueDispatchError,
    SubmissionAnalysisService,
)


def build_service(monkeypatch):
    session = MagicMock()
    submissions = MagicMock()
    jobs = MagicMock()
    queue = MagicMock()

    jobs.acquire_dispatch_lease.return_value = True
    jobs.release_dispatch_lease.return_value = True

    monkeypatch.setattr(
        service_module,
        "SubmissionRepository",
        lambda _session: submissions,
    )
    monkeypatch.setattr(
        service_module,
        "AnalysisJobRepository",
        lambda _session: jobs,
    )

    service = SubmissionAnalysisService(
        session=session,
        queue=queue,
    )

    return service, session, submissions, jobs, queue


def configure_queued_job(submissions, jobs, job_id=None):
    submission_id = uuid4()
    version_id = uuid4()
    job_id = job_id or uuid4()

    submissions.get_submission.return_value = SimpleNamespace(
        id=submission_id,
        current_version_number=1,
    )
    submissions.get_submission_version.return_value = SimpleNamespace(
        id=version_id,
        version_number=1,
    )
    jobs.create_or_get_analysis_job.return_value = SimpleNamespace(
        id=job_id,
        status="queued",
    )

    return submission_id, version_id, job_id


def test_create_text_submission_persists_initial_version(monkeypatch):
    service, session, submissions, _, _ = build_service(monkeypatch)

    organization_id = uuid4()
    actor_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()
    content = "Our brand uses approved terminology."

    submissions.create_submission.return_value = SimpleNamespace(
        id=submission_id,
        status="submitted",
    )
    submissions.create_submission_version.return_value = SimpleNamespace(
        id=version_id,
        version_number=1,
    )

    result = service.create_text_submission(
        organization_id=organization_id,
        actor_id=actor_id,
        title="  Campaign draft  ",
        text=content,
    )

    assert result.submission_id == submission_id
    assert result.submission_version_id == version_id
    assert result.version_number == 1
    assert result.status == "submitted"
    assert result.sha256 == sha256(content.encode("utf-8")).hexdigest()

    submissions.create_submission.assert_called_once_with(
        organization_id=organization_id,
        title="Campaign draft",
        created_by=actor_id,
    )
    submissions.create_submission_version.assert_called_once_with(
        organization_id=organization_id,
        submission_id=submission_id,
        version_number=1,
        source_type="text",
        original_text=content,
        extracted_text=content,
        sha256=result.sha256,
        created_by=actor_id,
    )

    session.commit.assert_called_once()
    session.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("title", "content"),
    [
        ("", "Valid text"),
        ("   ", "Valid text"),
        ("Campaign", ""),
        ("Campaign", "   "),
    ],
)
def test_create_text_submission_rejects_empty_input(
    monkeypatch,
    title,
    content,
):
    service, session, submissions, _, _ = build_service(monkeypatch)

    with pytest.raises(ValueError):
        service.create_text_submission(
            organization_id=uuid4(),
            actor_id=uuid4(),
            title=title,
            text=content,
        )

    submissions.create_submission.assert_not_called()
    submissions.create_submission_version.assert_not_called()
    session.commit.assert_not_called()


def test_create_text_submission_rolls_back_if_version_creation_fails(
    monkeypatch,
):
    service, session, submissions, _, _ = build_service(monkeypatch)

    submissions.create_submission.return_value = SimpleNamespace(
        id=uuid4(),
        status="submitted",
    )
    submissions.create_submission_version.side_effect = RuntimeError(
        "Simulated version persistence failure"
    )

    with pytest.raises(RuntimeError, match="version persistence failure"):
        service.create_text_submission(
            organization_id=uuid4(),
            actor_id=uuid4(),
            title="Campaign",
            text="Valid content",
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()


def test_request_analysis_uses_current_version_and_dispatches_with_lease(
    monkeypatch,
):
    service, session, submissions, jobs, queue = build_service(monkeypatch)

    organization_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()

    submissions.get_submission.return_value = SimpleNamespace(
        id=submission_id,
        current_version_number=2,
    )
    submissions.get_submission_version.return_value = SimpleNamespace(
        id=version_id,
        version_number=2,
    )
    jobs.create_or_get_analysis_job.return_value = SimpleNamespace(
        id=job_id,
        status="queued",
    )

    events = []
    session.commit.side_effect = lambda: events.append("commit")
    queue.enqueue_analysis.side_effect = lambda _job_id: events.append(
        "enqueue"
    )

    result = service.request_analysis(
        organization_id=organization_id,
        submission_id=submission_id,
        idempotency_key="request-001",
    )

    assert result.job_id == job_id
    assert result.submission_id == submission_id
    assert result.submission_version_id == version_id
    assert result.version_number == 2
    assert result.status == "queued"

    submissions.get_submission_version.assert_called_once_with(
        organization_id=organization_id,
        submission_id=submission_id,
        version_number=2,
    )
    jobs.create_or_get_analysis_job.assert_called_once_with(
        organization_id=organization_id,
        submission_version_id=version_id,
        idempotency_key="request-001",
        requested_checks=None,
    )

    jobs.acquire_dispatch_lease.assert_called_once()
    lease_args = jobs.acquire_dispatch_lease.call_args.kwargs
    assert lease_args["job_id"] == job_id
    assert lease_args["lease_token"] is not None
    assert lease_args["lease_expires_at"].tzinfo is not None

    queue.enqueue_analysis.assert_called_once_with(job_id)
    jobs.release_dispatch_lease.assert_not_called()

    # Persist the job, commit its lease, then publish to the queue.
    assert events == ["commit", "commit", "enqueue"]
    session.rollback.assert_not_called()


def test_request_analysis_can_select_an_explicit_version(monkeypatch):
    service, _, submissions, jobs, queue = build_service(monkeypatch)

    organization_id = uuid4()
    submission_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()

    submissions.get_submission.return_value = SimpleNamespace(
        id=submission_id,
        current_version_number=3,
    )
    submissions.get_submission_version.return_value = SimpleNamespace(
        id=version_id,
        version_number=1,
    )
    jobs.create_or_get_analysis_job.return_value = SimpleNamespace(
        id=job_id,
        status="processing",
    )

    result = service.request_analysis(
        organization_id=organization_id,
        submission_id=submission_id,
        idempotency_key="historical-version",
        version_number=1,
        requested_checks={"terminology": True},
    )

    assert result.version_number == 1
    assert result.status == "processing"

    submissions.get_submission_version.assert_called_once_with(
        organization_id=organization_id,
        submission_id=submission_id,
        version_number=1,
    )
    jobs.create_or_get_analysis_job.assert_called_once_with(
        organization_id=organization_id,
        submission_version_id=version_id,
        idempotency_key="historical-version",
        requested_checks={"terminology": True},
    )

    queue.enqueue_analysis.assert_not_called()
    jobs.acquire_dispatch_lease.assert_not_called()


def test_request_analysis_rejects_missing_submission(monkeypatch):
    service, session, submissions, jobs, queue = build_service(monkeypatch)
    submissions.get_submission.return_value = None

    with pytest.raises(LookupError, match="Submission not found"):
        service.request_analysis(
            organization_id=uuid4(),
            submission_id=uuid4(),
            idempotency_key="request-missing",
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    jobs.create_or_get_analysis_job.assert_not_called()
    jobs.acquire_dispatch_lease.assert_not_called()
    queue.enqueue_analysis.assert_not_called()


def test_request_analysis_skips_when_another_dispatcher_has_the_lease(
    monkeypatch,
):
    service, session, submissions, jobs, queue = build_service(monkeypatch)
    submission_id, _, job_id = configure_queued_job(submissions, jobs)
    jobs.acquire_dispatch_lease.return_value = False

    result = service.request_analysis(
        organization_id=uuid4(),
        submission_id=submission_id,
        idempotency_key="request-already-leased",
    )

    assert result.job_id == job_id
    assert result.status == "queued"
    jobs.acquire_dispatch_lease.assert_called_once()
    queue.enqueue_analysis.assert_not_called()
    jobs.release_dispatch_lease.assert_not_called()
    session.rollback.assert_called_once()


def test_queue_failure_reports_persisted_job_id_and_releases_lease(
    monkeypatch,
):
    service, session, submissions, jobs, queue = build_service(monkeypatch)
    submission_id, _, job_id = configure_queued_job(submissions, jobs)

    queue.enqueue_analysis.side_effect = RuntimeError(
        "Simulated queue outage"
    )

    with pytest.raises(AnalysisQueueDispatchError) as exc_info:
        service.request_analysis(
            organization_id=uuid4(),
            submission_id=submission_id,
            idempotency_key="request-queue-failure",
        )

    assert exc_info.value.job_id == job_id

    acquired = jobs.acquire_dispatch_lease.call_args.kwargs
    released = jobs.release_dispatch_lease.call_args.kwargs
    assert released["job_id"] == job_id
    assert released["lease_token"] == acquired["lease_token"]

    # Job commit, lease commit, and lease-release commit.
    assert session.commit.call_count == 3
    session.rollback.assert_called_once()


def test_failed_dispatch_does_not_release_a_lease_owned_by_another_dispatcher(
    monkeypatch,
):
    service, session, submissions, jobs, queue = build_service(monkeypatch)
    submission_id, _, job_id = configure_queued_job(submissions, jobs)

    queue.enqueue_analysis.side_effect = RuntimeError(
        "Simulated queue outage"
    )
    jobs.release_dispatch_lease.return_value = False

    with pytest.raises(AnalysisQueueDispatchError):
        service.request_analysis(
            organization_id=uuid4(),
            submission_id=submission_id,
            idempotency_key="request-lease-owner-changed",
        )

    acquired = jobs.acquire_dispatch_lease.call_args.kwargs
    released = jobs.release_dispatch_lease.call_args.kwargs

    assert acquired["job_id"] == job_id
    assert released["job_id"] == job_id
    assert released["lease_token"] == acquired["lease_token"]

    # The release did not succeed, so only the job and lease were committed.
    assert session.commit.call_count == 2
    assert session.rollback.call_count == 2


def test_request_analysis_rolls_back_if_job_creation_fails(monkeypatch):
    service, session, submissions, jobs, queue = build_service(monkeypatch)

    submission_id = uuid4()
    version_id = uuid4()

    submissions.get_submission.return_value = SimpleNamespace(
        id=submission_id,
        current_version_number=1,
    )
    submissions.get_submission_version.return_value = SimpleNamespace(
        id=version_id,
        version_number=1,
    )
    jobs.create_or_get_analysis_job.side_effect = ValueError(
        "Idempotency key conflicts with another request"
    )

    with pytest.raises(ValueError, match="Idempotency key conflicts"):
        service.request_analysis(
            organization_id=uuid4(),
            submission_id=submission_id,
            idempotency_key="conflicting-key",
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    jobs.acquire_dispatch_lease.assert_not_called()
    queue.enqueue_analysis.assert_not_called()