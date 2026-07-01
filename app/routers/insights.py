from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.insights import conversion_funnel, rep_leaderboard, source_cohorts, trends
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Contact, Deal, StageTransition, User

router = APIRouter(prefix="/insights")

_VALID_WINDOWS = frozenset({30, 90, 365})


def _deal_dicts(db: Session) -> list[dict]:
    return [
        {
            "stage": d.stage,
            "value": d.value,
            "owner_id": d.owner_id,
            "contact_id": d.contact_id,
            "created_at": d.created_at,
            "closed_at": d.closed_at,
        }
        for d in db.query(Deal).all()
    ]


def _contact_dicts(db: Session) -> list[dict]:
    return [{"id": c.id, "source": c.source} for c in db.query(Contact).all()]


def _transition_dicts(db: Session) -> list[dict]:
    return [
        {"deal_id": t.deal_id, "to_stage": t.to_stage, "occurred_at": t.occurred_at}
        for t in db.query(StageTransition).all()
    ]


@router.get("/trends")
def get_trends(
    window_days: int = Query(default=30),
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    if window_days not in _VALID_WINDOWS:
        raise HTTPException(
            status_code=422,
            detail=f"window_days must be one of {sorted(_VALID_WINDOWS)}",
        )
    return trends(_deal_dicts(db), window_days=window_days, clock=clk.now)


@router.get("/funnel")
def get_funnel(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return conversion_funnel(_deal_dicts(db), stage_history=_transition_dicts(db))


@router.get("/leaderboard")
def get_leaderboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Reps are scoped to their own deals; managers and admins see all.
    # Scoping is enforced here, not on the frontend.
    scope = current_user.id if current_user.role == "rep" else None
    return rep_leaderboard(_deal_dicts(db), scope=scope)


@router.get("/cohorts")
def get_cohorts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return source_cohorts(_deal_dicts(db), _contact_dicts(db))
