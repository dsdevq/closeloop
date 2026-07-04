# closeloop production image
# ------------------------------------------------------------------
# Multi-stage: Node builds the Vite frontend into app/static/, then
# a Python image serves the FastAPI app + the built static bundle
# from the same origin (zero external services — see ADR-0010).
#
# Build-cache layering (order is deliberate):
#   1. requirements-prod.txt install  — slow; only re-runs when deps change
#   2. app source copy                — fast; re-runs on every code edit
#
# To pin base images to immutable digests for production CI, run:
#   docker pull node:20.18.0-alpine3.21
#   docker inspect node:20.18.0-alpine3.21 --format '{{index .RepoDigests 0}}'
#   docker pull python:3.12.9-slim-bookworm
#   docker inspect python:3.12.9-slim-bookworm --format '{{index .RepoDigests 0}}'
# Then append @sha256:<digest> to each FROM line.
# ------------------------------------------------------------------

# ── Stage 1: Vite / Node build ────────────────────────────────────
# Exact release tag — version bumps are intentional, not automatic.
FROM node:20.18.0-alpine3.21 AS frontend-build
WORKDIR /src

# Copy manifests first; npm ci is cached separately from source.
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --prefer-offline

COPY frontend ./frontend
# vite.config.ts writes output to ../app/static and the build script
# runs `cp ../app/static/index.html ../app/static/login.html`, so the
# app directory must exist in this stage.
COPY app ./app
RUN cd frontend && npm run build


# ── Stage 2: Python runtime ───────────────────────────────────────
FROM python:3.12.9-slim-bookworm AS runtime
WORKDIR /app

# Non-root user — principle of least privilege.
RUN groupadd --gid 1001 appuser \
 && useradd  --uid 1001 --gid appuser --shell /bin/sh --no-create-home appuser

# curl is used only by the HEALTHCHECK instruction below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# ── Dependency layer ──────────────────────────────────────────────
# requirements-prod.txt contains only runtime packages; pytest and
# httpx (dev-only) are excluded.  Placed before the source COPY so
# that source-only edits do not bust this (slow) cache layer.
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

# /data holds the SQLite database; declare it as a volume mount-point so
# operators can bind-mount a named volume (e.g. closeloop-data:/data).
# appuser owns the dir so the DB file can be created without root.
RUN mkdir -p /data && chown appuser:appuser /app /data
VOLUME ["/data"]

# ── Application layer ─────────────────────────────────────────────
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser --from=frontend-build /src/app/static ./app/static

USER appuser

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
# DATABASE_URL is read by app/database.py; default keeps local-dev working,
# Dockerfile override points to the mounted volume for persistence.
ENV DATABASE_URL=sqlite:////data/closeloop.db
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

# gunicorn manages worker processes; UvicornWorker provides async I/O.
# Override PORT and WEB_CONCURRENCY at container run-time as needed.
CMD ["sh", "-c", "exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-4} --timeout 120 --access-logfile - --error-logfile -"]
