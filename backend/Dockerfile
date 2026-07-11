# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps for asyncpg / bcrypt / curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir 'gunicorn==23.0.0'

# Copy app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Non-root user
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

# Healthcheck (anonymous, no secrets)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

EXPOSE 8000

# Production: 4 workers × uvicorn. Override with WEB_CONCURRENCY env var.
ENV WEB_CONCURRENCY=4 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8000

CMD ["sh", "-c", "exec gunicorn app.main:app \
    --bind ${WEB_HOST}:${WEB_PORT} \
    --workers ${WEB_CONCURRENCY} \
    --worker-class uvicorn.workers.UvicornWorker \
    --access-logfile - \
    --error-logfile - \
    --forwarded-allow-ips='*' \
    --proxy-headers"]