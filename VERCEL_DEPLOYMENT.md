# BrandGuard AI: single-project Vercel deployment kit

This kit configures the repository as one Vercel project using Vercel Services for the Next.js + FastAPI applications and Vercel Daemons for the existing Celery worker and Celery Beat scheduler.

## Apply the files

Copy these files into the matching locations in the `Innovat3X/BrandGuard-AI` repository:

- `vercel.json` -> repository root
- `backend/Dockerfile` -> `backend/Dockerfile`
- `backend/.python-version` -> `backend/.python-version`
- `frontend/lib/api-client.ts` -> replace the existing frontend API client

Keep the Vercel project root at the repository root (`.`), not at `frontend/` or `backend/`, because the root configuration declares all services and daemons.

## Required production environment variables

Configure these in the Vercel project's Production environment before deploying:

- `DATABASE_URL`: PostgreSQL URL using the exact prefix `postgresql+psycopg://` (the current database layer validates this prefix).
- `JWT_SECRET_KEY`: unique, cryptographically random secret of at least 32 characters.
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: typically `30` unless you have another intended value.
- `CELERY_BROKER_URL`: secure URL for a reachable managed RabbitMQ broker, preferably `amqps://...` when supported by your broker provider.
- `CELERY_RESULT_BACKEND`: leave unset unless the implementation specifically requires it; job state is persisted in PostgreSQL.

Do not expose any secret with a `NEXT_PUBLIC_` variable. The frontend API client now defaults to same-origin requests in production, so Vercel's `/api/*` rewrite routes requests to FastAPI without a separate API URL.

## Database and broker

Vercel runs the frontend, API, Celery worker, and Celery Beat. PostgreSQL and RabbitMQ should be managed services reachable over TLS/network from Vercel; do not run them as containers in Vercel Daemons because daemon filesystem storage is ephemeral. Use connection details from your managed database and broker providers.

## Before the first live test

1. Create a PostgreSQL database and a managed RabbitMQ broker; add the environment variables above.
2. Apply the Alembic migrations to the production database. Run from a checkout with the production `DATABASE_URL` configured:

   `python -m alembic -c backend/alembic.ini upgrade head`

3. Import this repository into Vercel with the repository root as the project root. The root `vercel.json` declares the frontend, API, worker, and scheduler.
4. Confirm your Vercel account has Services and Daemons enabled. Daemons are currently beta and run only in production, not preview deployments.
5. Deploy, then check `/health`, `/docs`, register/login, submit analysis text, and confirm the Celery worker processes jobs and findings persist in PostgreSQL.

## Important notes

- The kit configures functions and daemons in `bom1` (Mumbai). Keep PostgreSQL and RabbitMQ in Mumbai or a nearby region where possible; otherwise change regions to match your database/broker location and check latency.
- The two daemons each start one instance. Keep a single Celery Beat instance for the current scheduler configuration.
- The backend's current CORS setting allows localhost only, but browser calls use the same origin through the Vercel rewrite in this configuration. If you later use a separate frontend origin, update CORS deliberately.
- This file set has not been deployed against your Vercel account. Validate the Vercel build and a full production end-to-end flow before relying on it.
