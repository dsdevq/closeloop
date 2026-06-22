import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.recurrence import expand_rrule
from app.database import get_db
from app.models import Activity

router = APIRouter(prefix="/activities")

_VALID_TYPES = {"call", "email", "meeting", "note"}


class ActivityCreate(BaseModel):
    deal_id: Optional[int] = None
    contact_id: Optional[int] = None
    type: str
    title: str
    body: Optional[str] = None
    due_at: Optional[str] = None
    recurrence_rule: Optional[dict] = None


class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    due_at: Optional[str] = None
    type: Optional[str] = None
    recurrence_rule: Optional[dict] = None


class ExpandRequest(BaseModel):
    count: int = 1


def _to_out(a: Activity) -> dict:
    rule = None
    if a.recurrence_rule:
        try:
            rule = json.loads(a.recurrence_rule)
        except (ValueError, TypeError):
            rule = None
    return {
        "id": a.id,
        "deal_id": a.deal_id,
        "contact_id": a.contact_id,
        "type": a.type,
        "title": a.title,
        "body": a.body,
        "due_at": a.due_at,
        "completed_at": a.completed_at,
        "recurrence_rule": rule,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


@router.post("", status_code=201)
def create_activity(
    body: ActivityCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    if body.type not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type must be one of {sorted(_VALID_TYPES)}",
        )
    if body.recurrence_rule is not None:
        try:
            expand_rrule(body.recurrence_rule, clk.now(), 0)
        except (ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"invalid recurrence_rule: {exc}") from exc
    now = clk.now().isoformat()
    activity = Activity(
        deal_id=body.deal_id,
        contact_id=body.contact_id,
        type=body.type,
        title=body.title,
        body=body.body,
        due_at=body.due_at,
        recurrence_rule=json.dumps(body.recurrence_rule) if body.recurrence_rule is not None else None,
        created_at=now,
        updated_at=now,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _to_out(activity)


@router.get("")
def list_activities(
    deal_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Activity)
    if deal_id is not None:
        query = query.filter(Activity.deal_id == deal_id)
    if contact_id is not None:
        query = query.filter(Activity.contact_id == contact_id)
    return [_to_out(a) for a in query.all()]


@router.get("/{activity_id}")
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _to_out(a)


@router.patch("/{activity_id}")
def update_activity(
    activity_id: int,
    body: ActivityUpdate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    updates = body.model_dump(exclude_unset=True)
    if "type" in updates and updates["type"] not in _VALID_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type must be one of {sorted(_VALID_TYPES)}",
        )
    if "recurrence_rule" in updates:
        rule = updates.pop("recurrence_rule")
        if rule is not None:
            try:
                expand_rrule(rule, clk.now(), 0)
            except (ValueError, KeyError) as exc:
                raise HTTPException(status_code=422, detail=f"invalid recurrence_rule: {exc}") from exc
            a.recurrence_rule = json.dumps(rule)
        else:
            a.recurrence_rule = None
    for field, value in updates.items():
        setattr(a, field, value)
    a.updated_at = clk.now().isoformat()
    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.post("/{activity_id}/complete")
def complete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    now = clk.now().isoformat()
    a.completed_at = now
    a.updated_at = now
    db.commit()
    db.refresh(a)
    return _to_out(a)


@router.delete("/{activity_id}", status_code=204)
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(a)
    db.commit()
    return Response(status_code=204)


@router.post("/{activity_id}/expand", status_code=201)
def expand_activity(
    activity_id: int,
    body: ExpandRequest,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    """
    Generate ``count`` future occurrences of a recurring activity.

    The source activity must have both ``due_at`` and ``recurrence_rule`` set.
    Returns a list of newly created activity rows (not the original).
    """
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Activity not found")
    if not a.recurrence_rule:
        raise HTTPException(
            status_code=422, detail="activity has no recurrence_rule"
        )
    if not a.due_at:
        raise HTTPException(
            status_code=422, detail="activity has no due_at; cannot expand recurrence"
        )
    if body.count <= 0:
        raise HTTPException(status_code=422, detail="count must be a positive integer")

    try:
        rule = json.loads(a.recurrence_rule)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail=f"malformed recurrence_rule: {exc}") from exc

    try:
        start = _parse_due_at(a.due_at)
        dates = expand_rrule(rule, start, body.count)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    now = clk.now().isoformat()
    created: list[Activity] = []
    for dt in dates:
        child = Activity(
            deal_id=a.deal_id,
            contact_id=a.contact_id,
            type=a.type,
            title=a.title,
            body=a.body,
            due_at=dt.isoformat(),
            recurrence_rule=a.recurrence_rule,
            created_at=now,
            updated_at=now,
        )
        db.add(child)
        created.append(child)

    db.commit()
    for child in created:
        db.refresh(child)
    return [_to_out(c) for c in created]


def _parse_due_at(ts: str):
    """Parse ISO-8601 due_at into a datetime for recurrence expansion."""
    from datetime import datetime
    dt = datetime.fromisoformat(ts)
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
