# BrandGuard AI: single-project Vercel deployment kit

This kit configures the repository as one Vercel project using Vercel Services for the Next.js and FastAPI applications, and Vercel Daemons for the existing Celery worker and Celery Beat scheduler.

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

Do not expose any secret with a `NEXT_PUBLIC_` variable. The frontend API client defaults to same-origin requests in production, so Vercel's `/api/*` rewrite routes requests to FastAPI without a separate API URL.

## Optional AI provider configuration

AI-assisted tone and messaging analysis is **disabled by default**. The application continues to use the configured deterministic checks when `AI_PROVIDER=disabled`.

To enable the OpenAI-compatible provider, configure the following variables in the Production environment used by both the **FastAPI API service and the Celery worker**:

| Variable | Purpose |
|---|---|
| `AI_PROVIDER` | Set to `openai_compatible` to enable the provider, or `disabled` to leave it off |
| `AI_API_KEY` | Secret API key for the configured provider |
| `AI_MODEL` | Model identifier supported by that provider |
| `AI_BASE_URL` | Optional provider API base URL; defaults to `https://api.openai.com/v1` |
| `AI_TIMEOUT_SECONDS` | Optional request timeout in seconds; defaults to `30` |
| `AI_MAX_OUTPUT_TOKENS` | Optional maximum output-token budget; defaults to `1800` |

Example configuration:

```dotenv
AI_PROVIDER=openai_compatible
AI_API_KEY=<your-provider-api-key>
AI_MODEL=<your-supported-model>
AI_BASE_URL=https://api.openai.com/v1
AI_TIMEOUT_SECONDS=30
AI_MAX_OUTPUT_TOKENS=1800
```

The angle-bracketed values above are placeholders. Replace them with the actual key and model identifier. Do not commit real credentials.

Configure the key as a secret in the hosting provider. **Never use a `NEXT_PUBLIC_` prefix for the AI key** or send the key to the frontend. AI calls are made by the backend worker, not by browser code.

The configured provider receives the submitted content and the approved guideline text needed for tone and messaging analysis. Before enabling it in production, review the provider's data-handling terms and confirm that sending this content to that provider is permitted by your organisation's privacy and security requirements.

The provider validates its response and represents failures or invalid output as unavailable checks. An unavailable AI check must not be treated as a successful check; it can cause the overall analysis to be reported as partial. AI findings remain advisory, and human reviewers remain responsible for publication decisions.

After changing these variables, redeploy the API service and worker so both processes use the same configuration. Keep AI disabled until the intended provider, credentials, model, privacy requirements, and deployment settings have been verified.

## Database and broker

Vercel runs the frontend, API, Celery worker, and Celery Beat. PostgreSQL and RabbitMQ should be managed services reachable over TLS/network from Vercel; do not run them as containers in Vercel Daemons because daemon filesystem storage is ephemeral. Use connection details from your managed database and broker providers.

## Before the first live test

1. Create a PostgreSQL database and a managed RabbitMQ broker; configure the required environment variables.
2. Apply the Alembic migrations to the target database. Run from a checkout with the appropriate `DATABASE_URL` configured:

   `python -m alembic -c backend/alembic.ini upgrade head`

3. Import this repository into Vercel with the repository root as the project root. The root `vercel.json` declares the frontend, API, worker, and scheduler.
4. Confirm your Vercel account has Services and Daemons enabled. Daemons are currently beta and run only in production, not preview deployments.
5. Deploy and check `/health`, `/docs`, registration, and login.
6. Submit a sample analysis and confirm the worker processes the job and findings persist in PostgreSQL.
7. Verify the findings endpoint returns the correct results for the exact submission version.
8. If enabling AI, configure the provider variables for both the API and worker, redeploy them, and verify an AI-enabled analysis with approved guidelines. Also test provider failure handling to confirm unavailable checks produce a partial result rather than a pass.

The deployment kit has not been verified against your Vercel account merely by documenting these settings. Validate the build and full production workflow before relying on it.

## Important notes

- The kit configures functions and daemons in `bom1` (Mumbai). Keep PostgreSQL and RabbitMQ in Mumbai or a nearby region where possible; otherwise change regions to match your database/broker location and check latency.
- The two daemons each start one instance. Keep a single Celery Beat instance for the current scheduler configuration.
- The backend's current CORS setting allows localhost only, but browser calls use the same origin through the Vercel rewrite in this configuration. If you later use a separate frontend origin, update CORS deliberately.
- Use a dedicated, non-production PostgreSQL test database for integration tests.
- Keep database credentials, broker credentials, JWT secrets, and AI provider keys out of source control.
- Do not automatically approve content based on analysis findings.
