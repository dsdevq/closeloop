from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.models import Activity, Reminder

router = APIRouter(prefix="/reminders")


class ReminderCreate(BaseModel):
    activity_id: int
    remind_at: str


def _to_out(r: Reminder) -> dict:
    return {
        "id": r.id,
        "activity_id": r.activity_id,
        "remind_at": r.remind_at,
        "dismissed_at": r.dismissed_at,
        "created_at": r.created_at,
    }


def _to_today_out(r: Reminder) -> dict:
    a = r.activity
    return {
        "id": r.id,
        "activity_id": r.activity_id,
        "activity_title": a.title if a else None,
        "activity_type": a.type if a else None,
        "deal_id": a.deal_id if a else None,
        "deal_title": a.deal.title if a and a.deal else None,
        "contact_id": a.contact_id if a else None,
        "contact_name": a.contact.name if a and a.contact else None,
        "remind_at": r.remind_at,
        "dismissed_at": r.dismissed_at,
        "created_at": r.created_at,
    }


@router.post("", status_code=201)
def create_reminder(
    body: ReminderCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    activity = db.query(Activity).filter(Activity.id == body.activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    now = clk.now().isoformat()
    reminder = Reminder(
        activity_id=body.activity_id,
        remind_at=body.remind_at,
        created_at=now,
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return _to_out(reminder)


@router.get("/today")
def get_today_reminders(
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    now_str = clk.now().isoformat()
    reminders = (
        db.query(Reminder)
        .filter(Reminder.dismissed_at == None, Reminder.remind_at <= now_str)  # noqa: E711
        .all()
    )
    return [_to_today_out(r) for r in reminders]


@router.patch("/{reminder_id}/dismiss")
def dismiss_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
):
    r = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    r.dismissed_at = clk.now().isoformat()
    db.commit()
    db.refresh(r)
    return _to_out(r)


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    r = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    db.delete(r)
    db.commit()
    return Response(status_code=204)
