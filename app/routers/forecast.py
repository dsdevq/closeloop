from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.forecast import stage_forecast, weighted_forecast
from app.database import get_db
from app.models import Deal

router = APIRouter(prefix="/forecast")


@router.get("")
def get_forecast(db: Session = Depends(get_db)):
    deals = db.query(Deal).all()
    deal_dicts = [
        {"stage": d.stage, "value": d.value, "probability": d.probability}
        for d in deals
    ]
    return {
        "total": weighted_forecast(deal_dicts),
        "by_stage": stage_forecast(deal_dicts),
    }
