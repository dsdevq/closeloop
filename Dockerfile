# closeloop production image
# ------------------------------------------------------------------
# Multi-stage: node builds the vite frontend into app/static/, then
# python image serves the FastAPI app + the built static bundle from
# the same origin (same shape as the existing devclaw preview flow,
# now owned by this repo instead of by devclaw's per-goal runner).
# ------------------------------------------------------------------

# --- Stage 1: build the frontend ---------------------------------
FROM node:20-alpine AS frontend-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
# The frontend's build script also copies index.html → login.html
# using ../app/static — bring the app dir along so that cp lands.
COPY app ./app
RUN cd frontend && npm run build

# --- Stage 2: python runtime -------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

# System deps kept minimal; add only what runtime needs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend source + the built frontend assets from stage 1.
COPY app ./app
COPY --from=frontend-build /src/app/static ./app/static

ENV PYTHONUNBUFFERED=1
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || exit 1

# Uvicorn honours ${PORT} (set at container-run time) so the deploy job
# can pin the host+container port from the repo's APP_PORT variable.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
