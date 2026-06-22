from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.forecast import weighted_forecast
from app.database import get_db
from app.models import Activity, Contact, Deal, Outbox

router = APIRouter(prefix="/stats")

_TERMINAL = {"won", "lost"}


@router.get("")
def get_stats(
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    now = clk.now()

    total_contacts = db.query(Contact).count()
    total_deals = db.query(Deal).count()
    total_activities = db.query(Activity).count()

    deals = db.query(Deal).all()

    deals_by_stage: dict[str, int] = {}
    for d in deals:
        deals_by_stage[d.stage] = deals_by_stage.get(d.stage, 0) + 1

    pipeline_value = sum(d.value for d in deals if d.stage not in _TERMINAL)

    deal_dicts = [{"stage": d.stage, "value": d.value, "probability": d.probability} for d in deals]
    wf = weighted_forecast(deal_dicts)

    cutoff = (now - timedelta(days=30)).isoformat()
    activities_last_30_days = (
        db.query(Activity).filter(Activity.created_at >= cutoff).count()
    )

    outbox_queued = db.query(Outbox).filter(Outbox.status == "queued").count()

    return {
        "total_contacts": total_contacts,
        "total_deals": total_deals,
        "total_activities": total_activities,
        "deals_by_stage": deals_by_stage,
        "pipeline_value": pipeline_value,
        "weighted_forecast": wf,
        "activities_last_30_days": activities_last_30_days,
        "outbox_queued": outbox_queued,
    }
