# BrandGuard AI

AI-powered brand governance platform for reviewing content against approved brand terminology and available brand knowledge before publication.

## Project Demonstration

Watch the deployed BrandGuard AI product demonstration:

[![BrandGuard AI — Complete Live Product Demonstration]

[Watch the demonstration on YouTube](https://youtu.be/ULJgc-X92_0)

## Prototype capabilities

The current prototype supports:

- User registration and login.
- Organisation-scoped text submissions.
- Asynchronous analysis jobs using Celery and RabbitMQ.
- Analysis job-status polling.
- Persisted findings linked to a specific submission version.
- Deterministic checks against approved terminology rules.
- Explanations, evidence, and suggested corrections where supported.
- Worker heartbeats, dispatch leases, and stale-job recovery.
- Human review of analysis results.

### Current limitations

- File-based submissions are not enabled. Submit pasted text.
- Claim extraction is not configured by default. Factual checks that cannot be completed reliably must be represented as unavailable, not passed.
- Some dashboard sample records, brand-library entries, review actions, and analytics remain illustrative rather than connected to backend persistence.
- Findings are review signals. Human reviewers remain responsible for publication decisions.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **API:** Python 3.12, FastAPI, Pydantic
- **Database:** PostgreSQL, SQLAlchemy, Alembic
- **Background processing:** Celery and RabbitMQ
- **Analysis:** Deterministic terminology rules and structured analysis components

Shared contracts are maintained in `docs/contracts/`:
- `api-v1.md`
- `data-model.md`
- `analysis-result.md`

## Local setup — Windows PowerShell

### Prerequisites

Install Python 3.12, Node.js/npm, PostgreSQL, and Docker Desktop.

### 1. Configure environment variables

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and configure `DATABASE_URL` for your PostgreSQL database. Replace `JWT_SECRET_KEY` with a unique random secret of at least 32 characters.

Never commit `.env` or production secrets.

### 2. Start RabbitMQ

```powershell
docker compose up -d rabbitmq
```

Ensure PostgreSQL is running and the database named in `DATABASE_URL` exists.

### 3. Install backend dependencies and apply migrations

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m alembic -c backend\alembic.ini upgrade head
```

Apply migrations after pulling code that adds or changes database migrations. Make sure `.env` points to the same database used by the API and worker.

### 4. Start the API

From the repository root:

```powershell
python -m uvicorn app.main:app --app-dir backend --reload
```

- Health endpoint: `http://localhost:8000/health`
- API documentation: `http://localhost:8000/docs`

### 5. Start the analysis worker

Open another terminal. From the repository root, run:

```powershell
.\.venv\Scripts\python.exe -m celery -A app.workers.celery_app.celery_app worker --loglevel=INFO --pool=solo -Q analysis
```

### 6. Start Celery Beat

Open another terminal and run:

```powershell
.\.venv\Scripts\python.exe -m celery -A app.workers.celery_app.celery_app beat --loglevel=INFO
```

Celery Beat is required for scheduled stale-job recovery. Run only one scheduler for this configuration.

### 7. Start the frontend

Open another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`.

The frontend API client defaults to `http://localhost:8000`. Configure `NEXT_PUBLIC_API_BASE_URL` before building or starting the frontend if the API has a different origin.

Register an account at `/register`, then sign in at `/login`. Submit text through **New analysis**.

### Brand Library management

With the updated Brand Library frontend patch present and the frontend development server running, open:

http://localhost:3000/brand-library

The updated page provides the facts and rules management interface. Use it to create facts and terminology rules, save drafts, create new versions, review version history, and approve drafts with an authorised admin or reviewer account.

If the page still displays **“Reference management not connected yet,”** the browser is showing an older frontend build or the updated frontend patch is not present in the local checkout. Confirm that the Brand Library page and its fact/rule service files are present, then restart the frontend development server.

The local frontend patch does not automatically update the hosted website. To make Brand Library management available on the deployed site, commit and push the updated frontend files to the deployment branch and redeploy the frontend. Ensure `NEXT_PUBLIC_API_BASE_URL` points to the backend that exposes the Brand Facts and Brand Rules APIs.

## Verification

From the repository root:

```powershell
python -m pytest backend/tests -q
git diff --check
```

From the `frontend` directory:

```powershell
npm run lint
npm run build
```

A passing unit-test suite does not replace a live end-to-end test with PostgreSQL, RabbitMQ, the API, the worker, Celery Beat, and the browser running together.

## Deployment and security

- Use a strong, unique JWT secret.
- Use managed or properly secured PostgreSQL and RabbitMQ services.
- Configure production CORS to allow only the deployed frontend origin.
- Use TLS and secure database/broker connections.
- Configure production environment variables through the hosting provider, not committed files.
- Run database migrations before serving application traffic.
- Keep human review in the publication workflow.

This is a prototype. Do not rely on it as the sole control for legal, factual, safety, or publication approval.

## Repository

[GitHub repository](https://github.com/Innovat3X/BrandGuard-AI)

[Integration pull request #4](https://github.com/Innovat3X/BrandGuard-AI/pull/4)
