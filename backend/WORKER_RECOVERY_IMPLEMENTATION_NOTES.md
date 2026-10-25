# BrandGuard AI — Anusha's Worker-Recovery Draft

This worker-recovery implementation is on the isolated branch
`feat/anusha-worker-recovery`, based on the backend source snapshot
from commit `b54cd9a`.

It implements worker-recovery orchestration and tests. Girish's
migration and persistence-side repository changes are being handled
separately and have not yet been integrated or verified with this
implementation. The repository interface below must be reconciled
with Girish's implementation before integration.

## Implemented in this branch

- A worker heartbeat that uses an independent SQLAlchemy session, defaults to 60 seconds, and calls a conditional repository operation fenced by job status and claimed attempt.
- An `AnalysisRecoveryService` with bounded candidate batches, a configurable five-minute processing-staleness threshold, a five-minute dispatch lease, and per-job conditional transitions.
- A recovery task scheduled every 60 seconds through Celery Beat.
- Unit tests for worker heartbeats, lost ownership, stale recovery, exhausted attempts, concurrent recovery conflicts, queued dispatch recovery, lease conflicts, and failed broker publication.

## Repository interface expected by this draft

Girish's persistence implementation should supply equivalent methods, or the draft should be adjusted to his exact names/signatures:

```python
heartbeat_processing_job(job_id: UUID, claimed_attempt: int) -> bool
list_stale_processing_jobs(stale_before: datetime, limit: int) -> Sequence[AnalysisJob]
recover_stale_processing_job(
    job_id: UUID,
    expected_attempt: int,
    stale_before: datetime,
    max_attempts: int,
) -> bool
list_queued_jobs_for_recovery(limit: int) -> Sequence[AnalysisJob]
acquire_dispatch_lease(
    job_id: UUID,
    lease_token: UUID,
    lease_expires_at: datetime,
    stale_before: datetime | None = None,
) -> bool
release_dispatch_lease(job_id: UUID, lease_token: UUID) -> bool
```

Required semantics:

- Heartbeats update only when the job is still `processing` and the attempt matches.
- Processing recovery rechecks status, expected attempt, and heartbeat cutoff atomically.
- Queued candidates are limited to queued jobs whose lease is absent or expired; acquiring a lease rechecks this condition atomically.
- Only the lease owner may release a failed dispatch lease.
- The persistence method that marks an exhausted job `failed` also updates the related submission status transactionally.
- The worker claim increments the attempt, initialises `heartbeat_at`, and clears the dispatch lease.

## Tests run locally

- Focused worker-recovery tests: 27 passed in 2.49 seconds.
- Full backend test suite: 340 passed, 1 warning in 9.85 seconds.
- `git diff --check`: clean.

The warning is a Starlette deprecation warning related to
using `httpx` with `starlette.testclient`.

The full backend suite passed against the current local code.
However, PostgreSQL integration of the new recovery operations
still requires verification after Girish's migration and repository
implementation are available.

These results do not establish that the new recovery operations
have been tested against the completed persistence implementation.
## Starting the scheduled recovery task

Celery Beat must run as a separate process for the periodic schedule to execute. From the `backend` directory, once the code and repository methods are integrated, the command is:

```powershell
..\.venv\Scripts\python.exe -m celery -A app.workers.celery_app.celery_app beat --loglevel=INFO
```

Use the project's existing worker command in a separate terminal. Do not start Beat twice for the same schedule unless the deployment is designed for a single scheduler/leader.
