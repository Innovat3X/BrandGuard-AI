# \# Analysis Worker and Recovery Integration

#

# This document describes the integrated implementation on

# `feat/m4-persistence-integration`. The worker-recovery and persistence

# changes have been integrated; this is no longer a draft integration.

#

# \## Implemented

#

# \- Database-backed analysis jobs, with PostgreSQL as the source of truth.

# \- Celery/RabbitMQ dispatch using the dedicated `analysis` queue.

# \- Conditional worker claims, attempt tracking, and heartbeats.

# \- Persisted findings associated with the correct submission version.

# \- Dispatch leases to protect job publication and recovery paths.

# \- Stale-job recovery scheduled every 60 seconds through Celery Beat.

# \- Organisation-scoped submission, job-status, and version-specific

# &#x20; findings endpoints.

# \- Unavailable factual checks are not treated as passing checks.

#

# \## Required database migration

#

# Migration `4b71e8d29c60\_add\_analysis\_job\_recovery\_fields.py` adds:

#

# \- `analysis\_jobs.heartbeat\_at`

# \- `analysis\_jobs.dispatch\_lease\_token`

# \- `analysis\_jobs.dispatch\_lease\_expires\_at`

#

# Run the following from the repository root:

#

# ```powershell

# python -m alembic -c backend\\alembic.ini current

# python -m alembic -c backend\\alembic.ini upgrade head

# python -m alembic -c backend\\alembic.ini current

# ```

#

# Ensure `.env` points to the same PostgreSQL database used by the API

# and worker. A backend process may start even when the database schema

# is behind, but analysis queueing can then fail when it queries the

# missing recovery columns.

#

# \## Process requirements

#

# Run the API, analysis worker, and Celery Beat as separate processes.

# RabbitMQ and PostgreSQL must be available.

#

# From the repository root, the worker command is:

#

# ```powershell

# .\\.venv\\Scripts\\python.exe -m celery -A app.workers.celery\_app.celery\_app worker --loglevel=INFO --pool=solo -Q analysis

# ```

#

# Start the scheduler in another terminal:

#

# ```powershell

# .\\.venv\\Scripts\\python.exe -m celery -A app.workers.celery\_app.celery\_app beat --loglevel=INFO

# ```

#

# Only one Beat scheduler should run for this configuration.

#

# \## Validation

#

# The integrated branch previously passed the full backend test suite:

# \*\*364 passed, 1 warning\*\*. `git diff --check` also passed.

#

# A live smoke test exposed a database-schema mismatch. The missing

# recovery migration was applied to the database used by the local API,

# after which the live prototype workflow worked.

#

# Repeat the test suite and a live end-to-end test against the actual

# deployment configuration before release.

#

# \## Prototype limitations

#

# Claim extraction is not configured by default. Some dashboard records,

# brand-library content, review actions, and analytics remain illustrative.

# Analysis findings support human review and do not replace human approval.
