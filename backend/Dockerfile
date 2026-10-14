# Backend image for Labor Evidence Organizer.
#
# Authored to spec (docs/04_TECH_ARCHITECTURE.md); the environment this
# project was developed in has no Docker, so this file was validated by
# static review only — see docs/17 §13 (9-D-4). The container runs
# migrations on start, so it assumes a single backend replica.
FROM python:3.11-slim

WORKDIR /app

# libmagic: python-magic content sniffing (optional at runtime, but the
# upload path benefits from it); curl: container HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code only — never bake .env, tests or uploaded evidence
# (.dockerignore enforces this; var/ holds local storage).
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/storage \
    && chown -R appuser:appuser /app /data
USER appuser

ENV STORAGE_LOCAL_ROOT=/data/storage
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# Migrate then serve. Env (DATABASE_URL, SECRET_KEY…) comes from compose/.env.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
