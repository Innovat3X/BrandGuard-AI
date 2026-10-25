from __future__ import annotations

import os
from pathlib import Path

from celery import Celery
from dotenv import dotenv_values


# Resolve the project root from backend/app/workers/celery_app.py.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"

# Environment variables take precedence over values from the project .env.
FILE_ENV = dotenv_values(ENV_FILE) if ENV_FILE.is_file() else {}


def _get_setting(name: str, default: str | None = None) -> str | None:
    """Read a setting from the process environment, then the project .env."""
    value = os.environ.get(name)
    if value is not None and value.strip():
        return value.strip()

    file_value = FILE_ENV.get(name)
    if isinstance(file_value, str) and file_value.strip():
        return file_value.strip()

    return default


BROKER_URL = _get_setting(
    "CELERY_BROKER_URL",
    "amqp://guest:guest@localhost:5672//",
)
RESULT_BACKEND = _get_setting("CELERY_RESULT_BACKEND")

celery_app = Celery(
    "brandguard",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.workers.analysis_tasks"],
)

celery_app.conf.update(
    # Analysis task routing.
    task_default_queue="analysis",
    task_routes={
        "app.workers.analysis_tasks.process_analysis_job": {
            "queue": "analysis",
        },
    },

    # JSON-only task and result serialization.
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",

    # Time and worker execution settings.
    enable_utc=True,
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Broker connection and publication retries.
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 1,
    },

    # A dedicated Celery Beat process must be running for stale-job recovery.
    beat_schedule={
        "recover-stale-analysis-jobs-every-minute": {
            "task": "app.workers.analysis_tasks.recover_stale_analysis_jobs",
            "schedule": 60.0,
        },
    },

    # RabbitMQ 4.3 compatibility: transient control/event queues must
    # be exclusive rather than non-durable and non-exclusive.
    control_queue_exclusive=True,
    event_queue_exclusive=True,
)