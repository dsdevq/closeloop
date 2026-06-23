# CloseLoop

Self-contained CRM — FastAPI backend, React/Vite/Tailwind frontend, SQLite storage.

The built frontend is served by FastAPI from `app/static`. Frontend source lives in `frontend/`.

## Quick start (local)

```bash
# Install dependencies (Python 3.11+)
pip install -r requirements.txt

# Install frontend dependencies
npm --prefix frontend install --include=dev

# Build React frontend into app/static
npm run build

# Run from repo root — static UI served at /
uvicorn app.main:app --reload

# Health check
curl http://localhost:8000/health
```

## Preview / hosted environment

If running behind a reverse proxy or in a container, bind to all interfaces:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Tests

```bash
python -m pytest -q
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

The database file (`closeloop.db`) is created automatically in the repo root on first boot.
