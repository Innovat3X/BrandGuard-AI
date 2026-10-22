# BrandGuard AI

AI-Powered Brand Governance Platform.

## Architecture

- Frontend: Next.js App Router, React, TypeScript, Tailwind CSS
- Backend: Python 3.12, FastAPI, Pydantic
- Database: PostgreSQL, SQLAlchemy, Alembic
- Background processing: Celery and RabbitMQ
- Analysis: deterministic rules and a provider-independent AI adapter

## Shared contracts

- docs/contracts/api-v1.md
- docs/contracts/data-model.md
- docs/contracts/analysis-result.md

These contracts define the common interfaces used by all team members.
Changes must be coordinated and reviewed.

## Backend quick start

Create a Python 3.12 virtual environment in the project root.
Install dependencies from backend/requirements.txt.
Run the application with Uvicorn from the backend directory.

The initial health endpoint is /health.
The FastAPI interactive documentation is available at /docs.
