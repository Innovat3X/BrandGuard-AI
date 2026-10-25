FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app

# The Vercel Daemon configuration overrides this command for the worker and Beat.
CMD ["python", "-m", "celery", "-A", "app.workers.celery_app.celery_app", "worker", "--loglevel=INFO", "-Q", "analysis"]
