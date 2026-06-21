from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.core.clock import Clock, get_clock

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db), clk: Clock = Depends(get_clock)):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    return {
        "status": "ok",
        "db": db_status,
        "version": "0.1.0",
        "timestamp": clk.now().isoformat(),
    }
