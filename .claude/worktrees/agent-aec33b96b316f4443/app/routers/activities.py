from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
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


class ActivityUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    due_at: Optional[str] = None
    type: Optional[str] = None


def _to_out(a: Activity) -> dict:
    return {
        "id": a.id,
        "deal_id": a.deal_id,
        "contact_id": a.contact_id,
        "type": a.type,
        "title": a.title,
        "body": a.body,
        "due_at": a.due_at,
        "completed_at": a.completed_at,
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
    now = clk.now().isoformat()
    activity = Activity(
        deal_id=body.deal_id,
        contact_id=body.contact_id,
        type=body.type,
        title=body.title,
        body=body.body,
        due_at=body.due_at,
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
