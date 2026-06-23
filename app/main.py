import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

import app.models  # noqa: F401 — registers models on Base before create_all
from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models import Activity, Contact, Deal, User
from app.routers.activities import router as activities_router
from app.routers.auth import router as auth_router
from app.routers.contacts import router as contacts_router
from app.routers.deals import router as deals_router
from app.routers.forecast import router as forecast_router
from app.routers.health import router as health_router
from app.routers.outbox import router as outbox_router
from app.routers.reminders import router as reminders_router
from app.routers.saved_views import router as saved_views_router
from app.routers.stats import router as stats_router
from app.routers.tags import router as tags_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _run_migrations():
    """Add owner_id columns to existing tables if they don't already exist."""
    with engine.connect() as conn:
        for table in ("contacts", "deals", "activities"):
            try:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
                )
                conn.commit()
            except Exception:
                # Column already present — OperationalError("duplicate column name")
                conn.rollback()


def _seed_and_backfill():
    db = SessionLocal()
    try:
        if not db.query(User).first():
            now = datetime.now(timezone.utc).isoformat()
            admin = User(
                email="admin@closeloop.com",
                hashed_password=hash_password("admin123"),
                role="admin",
                full_name="Admin",
                created_at=now,
                is_active=1,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print("=" * 40)
            print("SEED ADMIN CREATED")
            print("  email:    admin@closeloop.com")
            print("  password: admin123")
            print("=" * 40)
            _backfill_owner(db, admin.id)
        else:
            admin = db.query(User).filter(User.role == "admin").first()
            if admin:
                _backfill_owner(db, admin.id)
    finally:
        db.close()


def _backfill_owner(db, admin_id: int):
    db.query(Contact).filter(Contact.owner_id.is_(None)).update({"owner_id": admin_id})
    db.query(Deal).filter(Deal.owner_id.is_(None)).update({"owner_id": admin_id})
    db.query(Activity).filter(Activity.owner_id.is_(None)).update({"owner_id": admin_id})
    db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _seed_and_backfill()
    yield


app = FastAPI(title="CloseLoop", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def _json_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": latency_ms,
            }
        )
    )
    return response


# API routers must be registered before the static files catch-all
app.include_router(health_router, prefix="")
app.include_router(auth_router)
app.include_router(contacts_router)
app.include_router(deals_router)
app.include_router(activities_router)
app.include_router(reminders_router)
app.include_router(forecast_router)
app.include_router(saved_views_router)
app.include_router(outbox_router)
app.include_router(stats_router)
app.include_router(tags_router)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
