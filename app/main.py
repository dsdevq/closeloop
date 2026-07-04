import asyncio
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
from app.core.clock import get_clock
from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models import Activity, Contact, Deal, PipelineStage, User
from app.services.automations import run_scheduled_automations
from app.routers.accounts import router as accounts_router
from app.routers.activities import router as activities_router
from app.routers.auth import router as auth_router
from app.routers.contacts import router as contacts_router
from app.routers.deals import router as deals_router
from app.routers.forecast import router as forecast_router
from app.routers.health import router as health_router
from app.routers.insights import router as insights_router
from app.routers.history import router as history_router
from app.routers.notifications import router as notifications_router
from app.routers.outbox import router as outbox_router
from app.routers.pipeline import router as pipeline_router
from app.routers.reminders import router as reminders_router
from app.routers.saved_views import router as saved_views_router
from app.routers.stats import router as stats_router
from app.routers.tags import router as tags_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Map legacy string stage names → default PipelineStage names
_STAGE_NAME_MAP: dict[str, str] = {
    "lead": "Prospecting",
    "qualified": "Qualification",
    "proposal": "Proposal",
    "negotiation": "Negotiation",
    "won": "Closed-Won",
    "lost": "Closed-Lost",
    "open": "Prospecting",
    "active": "Prospecting",
}


def _run_migrations():
    """Add new columns to existing tables idempotently."""
    with engine.connect() as conn:
        # v1 — owner_id on contacts / deals / activities
        for table in ("contacts", "deals", "activities"):
            try:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
                )
                conn.commit()
            except Exception:
                conn.rollback()

        # v2 — account_id on contacts, stage_id on deals
        v2_cols = [
            ("contacts", "account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL"),
            ("deals", "stage_id INTEGER REFERENCES pipeline_stages(id) ON DELETE SET NULL"),
        ]
        for table, col_def in v2_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
                conn.commit()
            except Exception:
                conn.rollback()

        # v2.1 — notes on accounts
        try:
            conn.execute(text("ALTER TABLE accounts ADD COLUMN notes TEXT"))
            conn.commit()
        except Exception:
            conn.rollback()

        # v3 — scheduled trigger support on automation_rules
        v3_cols = [
            ("automation_rules", "trigger_type TEXT NOT NULL DEFAULT 'after_save'"),
            ("automation_rules", "schedule_config_json TEXT"),
            ("automation_rules", "last_triggered_at TEXT"),
        ]
        for table, col_def in v3_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))
                conn.commit()
            except Exception:
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


def _seed_pipeline_stages():
    """Seed the 6 default pipeline stages if none exist, then backfill deal.stage_id."""
    db = SessionLocal()
    try:
        if db.query(PipelineStage).first():
            # Already seeded — just make sure stage_id backfill is done
            _backfill_stage_id(db)
            return

        now = datetime.now(timezone.utc).isoformat()
        defaults = [
            PipelineStage(name="Prospecting",  position=0, probability=0,   is_default=1, created_at=now),
            PipelineStage(name="Qualification", position=1, probability=20,  is_default=1, created_at=now),
            PipelineStage(name="Proposal",      position=2, probability=50,  is_default=1, created_at=now),
            PipelineStage(name="Negotiation",   position=3, probability=75,  is_default=1, created_at=now),
            PipelineStage(name="Closed-Won",    position=4, probability=100, is_default=1, created_at=now),
            PipelineStage(name="Closed-Lost",   position=5, probability=0,   is_default=1, created_at=now),
        ]
        db.add_all(defaults)
        db.commit()
        _backfill_stage_id(db)
    finally:
        db.close()


def _backfill_stage_id(db):
    """Set deal.stage_id for any deals that still have NULL stage_id."""
    stages = {s.name: s.id for s in db.query(PipelineStage).all()}
    if not stages:
        return
    deals = db.query(Deal).filter(Deal.stage_id.is_(None)).all()
    for deal in deals:
        target_name = _STAGE_NAME_MAP.get(deal.stage, "Prospecting")
        stage_id = stages.get(target_name)
        if stage_id:
            deal.stage_id = stage_id
    db.commit()


async def _scheduled_automations_loop() -> None:
    """Background poller for scheduled AutomationRules.

    Sleeps 60 seconds between polls so the poller fires roughly every minute.
    Each poll opens its own DB session and commits independently of any request
    handler — the poller owns its transactions (unlike after_save rule evaluation
    which runs within the router's transaction).

    Exceptions are caught and logged so a transient error cannot kill the loop.
    """
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            count = run_scheduled_automations(db, clk=get_clock())
            if count:
                logger.info("scheduled automations: %d rule(s) fired", count)
        except Exception:
            logger.exception("scheduled automations poller encountered an error")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _run_migrations()
    _seed_and_backfill()
    _seed_pipeline_stages()
    poller_task = asyncio.create_task(_scheduled_automations_loop())
    yield
    poller_task.cancel()
    try:
        await poller_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="CloseLoop", version="2.0.0", lifespan=lifespan)


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
app.include_router(accounts_router)
app.include_router(pipeline_router)
app.include_router(activities_router)
app.include_router(reminders_router)
app.include_router(forecast_router)
app.include_router(insights_router)
app.include_router(history_router)
app.include_router(notifications_router)
app.include_router(saved_views_router)
app.include_router(outbox_router)
app.include_router(stats_router)
app.include_router(tags_router)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
