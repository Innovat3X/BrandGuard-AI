from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.analysis_dispatch import (
    DispatchOutcome,
    enqueue_with_dispatch_lease,
)


def build_dispatch():
    session = MagicMock()
    jobs = MagicMock()
    queue = MagicMock()

    jobs.acquire_dispatch_lease.return_value = True
    jobs.release_dispatch_lease.return_value = True

    job_id = uuid4()

    return session, jobs, queue, job_id


def set_dispatch_state(session, state):
    """Configure the row returned by the dispatch-state query."""
    session.execute.return_value.one_or_none.return_value = state


def test_dispatch_commits_lease_before_publishing():
    session, jobs, queue, job_id = build_dispatch()
    events = []

    session.commit.side_effect = lambda: events.append("commit")
    queue.enqueue_analysis.side_effect = lambda _job_id: events.append(
        "enqueue"
    )

    outcome = enqueue_with_dispatch_lease(
        session=session,
        jobs=jobs,
        queue=queue,
        job_id=job_id,
    )

    assert outcome is DispatchOutcome.DISPATCHED
    assert events == ["commit", "enqueue"]

    jobs.acquire_dispatch_lease.assert_called_once()
    lease_args = jobs.acquire_dispatch_lease.call_args.kwargs

    assert lease_args["job_id"] == job_id
    assert lease_args["lease_token"] is not None
    assert lease_args["lease_expires_at"].tzinfo is not None

    queue.enqueue_analysis.assert_called_once_with(job_id)
    jobs.release_dispatch_lease.assert_not_called()


def test_dispatch_returns_lease_unavailable_for_a_live_competing_lease():
    session, jobs, queue, job_id = build_dispatch()
    jobs.acquire_dispatch_lease.return_value = False
    set_dispatch_state(
        session,
        ("queued", "another-dispatcher-token", True),
    )

    outcome = enqueue_with_dispatch_lease(
        session=session,
        jobs=jobs,
        queue=queue,
        job_id=job_id,
    )

    assert outcome is DispatchOutcome.LEASE_UNAVAILABLE
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    queue.enqueue_analysis.assert_not_called()
    jobs.release_dispatch_lease.assert_not_called()


def test_dispatch_returns_not_eligible_when_job_is_no_longer_queued():
    session, jobs, queue, job_id = build_dispatch()
    jobs.acquire_dispatch_lease.return_value = False
    set_dispatch_state(session, ("processing", None, False))

    outcome = enqueue_with_dispatch_lease(
        session=session,
        jobs=jobs,
        queue=queue,
        job_id=job_id,
    )

    assert outcome is DispatchOutcome.NOT_ELIGIBLE
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    queue.enqueue_analysis.assert_not_called()
    jobs.release_dispatch_lease.assert_not_called()


def test_dispatch_returns_not_eligible_when_job_does_not_exist():
    session, jobs, queue, job_id = build_dispatch()
    jobs.acquire_dispatch_lease.return_value = False
    set_dispatch_state(session, None)

    outcome = enqueue_with_dispatch_lease(
        session=session,
        jobs=jobs,
        queue=queue,
        job_id=job_id,
    )

    assert outcome is DispatchOutcome.NOT_ELIGIBLE
    queue.enqueue_analysis.assert_not_called()
    jobs.release_dispatch_lease.assert_not_called()


def test_dispatch_returns_retry_required_for_lease_expiry_race():
    session, jobs, queue, job_id = build_dispatch()
    jobs.acquire_dispatch_lease.return_value = False
    set_dispatch_state(session, ("queued", None, False))

    outcome = enqueue_with_dispatch_lease(
        session=session,
        jobs=jobs,
        queue=queue,
        job_id=job_id,
    )

    assert outcome is DispatchOutcome.RETRY_REQUIRED
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    queue.enqueue_analysis.assert_not_called()
    jobs.release_dispatch_lease.assert_not_called()


def test_failed_publish_releases_the_lease_it_acquired():
    session, jobs, queue, job_id = build_dispatch()
    queue.enqueue_analysis.side_effect = RuntimeError(
        "Simulated queue outage"
    )

    with pytest.raises(RuntimeError, match="queue outage"):
        enqueue_with_dispatch_lease(
            session=session,
            jobs=jobs,
            queue=queue,
            job_id=job_id,
        )

    acquired = jobs.acquire_dispatch_lease.call_args.kwargs
    released = jobs.release_dispatch_lease.call_args.kwargs

    assert released["job_id"] == job_id
    assert released["lease_token"] == acquired["lease_token"]

    # The lease is committed once on acquisition and once on release.
    assert session.commit.call_count == 2
    session.rollback.assert_called_once()


def test_failed_publish_does_not_release_a_superseded_lease():
    session, jobs, queue, job_id = build_dispatch()
    jobs.release_dispatch_lease.return_value = False
    queue.enqueue_analysis.side_effect = RuntimeError(
        "Simulated queue outage"
    )

    with pytest.raises(RuntimeError, match="queue outage"):
        enqueue_with_dispatch_lease(
            session=session,
            jobs=jobs,
            queue=queue,
            job_id=job_id,
        )

    acquired = jobs.acquire_dispatch_lease.call_args.kwargs
    released = jobs.release_dispatch_lease.call_args.kwargs

    assert released["job_id"] == job_id
    assert released["lease_token"] == acquired["lease_token"]

    # The acquisition commits; unsuccessful release is rolled back.
    assert session.commit.call_count == 1
    assert session.rollback.call_count == 2


def test_dispatch_propagates_lease_acquisition_errors():
    session, jobs, queue, job_id = build_dispatch()
    jobs.acquire_dispatch_lease.side_effect = RuntimeError(
        "Database unavailable"
    )

    with pytest.raises(RuntimeError, match="Database unavailable"):
        enqueue_with_dispatch_lease(
            session=session,
            jobs=jobs,
            queue=queue,
            job_id=job_id,
        )

    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    queue.enqueue_analysis.assert_not_called()
    jobs.release_dispatch_lease.assert_not_called()