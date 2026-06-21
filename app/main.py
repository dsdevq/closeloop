import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401 — registers models on Base before create_all
from app.database import Base, engine
from app.routers.contacts import router as contacts_router
from app.routers.deals import router as deals_router
from app.routers.health import router as health_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="CloseLoop", version="0.1.0", lifespan=lifespan)


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
app.include_router(contacts_router)
app.include_router(deals_router)

app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
