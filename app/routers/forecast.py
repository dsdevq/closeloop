from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.forecast import forecast_scenarios, stage_forecast, weighted_forecast
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Deal, User

router = APIRouter(prefix="/forecast")


def _deal_dicts(db: Session) -> list[dict]:
    return [
        {"stage": d.stage, "value": d.value, "probability": d.probability}
        for d in db.query(Deal).all()
    ]


@router.get("")
def get_forecast(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deals = _deal_dicts(db)
    return {
        "total": weighted_forecast(deals),
        "by_stage": stage_forecast(deals),
    }


class ScenariosRequest(BaseModel):
    probability_overrides: Optional[dict[str, float]] = None


@router.post("/scenarios")
def get_forecast_scenarios(
    body: ScenariosRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return best/expected/worst forecast scenarios, plus optional custom probability map."""
    deals = _deal_dicts(db)
    return forecast_scenarios(deals, custom_map=body.probability_overrides)
