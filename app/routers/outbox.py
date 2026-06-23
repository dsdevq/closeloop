from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Outbox, Reminder, User

router = APIRouter(prefix="/outbox")

_VALID_STATUSES = {"queued", "sent", "failed"}


class OutboxCreate(BaseModel):
    to_address: str
    subject: str
    body: str
    deal_id: Optional[int] = None
    contact_id: Optional[int] = None


def _to_out(m: Outbox) -> dict:
    return {
        "id": m.id,
        "to_address": m.to_address,
        "subject": m.subject,
        "body": m.body,
        "status": m.status,
        "deal_id": m.deal_id,
        "contact_id": m.contact_id,
        "created_at": m.created_at,
        "sent_at": m.sent_at,
    }


@router.post("", status_code=201)
def queue_message(
    body: OutboxCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    now = clk.now().isoformat()
    msg = Outbox(
        to_address=body.to_address,
        subject=body.subject,
        body=body.body,
        status="queued",
        deal_id=body.deal_id,
        contact_id=body.contact_id,
        created_at=now,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg)


@router.get("")
def list_messages(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Outbox)
    if status is not None:
        if status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"status must be one of {sorted(_VALID_STATUSES)}",
            )
        query = query.filter(Outbox.status == status)
    return [_to_out(m) for m in query.all()]


@router.get("/{message_id}")
def get_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg = db.query(Outbox).filter(Outbox.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return _to_out(msg)


@router.delete("/{message_id}", status_code=204)
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg = db.query(Outbox).filter(Outbox.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
    return Response(status_code=204)


@router.post("/digest", status_code=201)
def create_digest(
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """
    Compose a daily digest of all overdue and due-today reminders into one outbox row.

    Fetches undismissed reminders whose remind_at ≤ now, composes a plain-text
    summary, and inserts a single outbox row with status='queued'.  If there are no
    overdue reminders the endpoint still succeeds but notes that in the body.
    No real email is ever sent (outbox is a stub boundary per D10).
    """
    now = clk.now()
    now_str = now.isoformat()
    date_str = now.date().isoformat()

    reminders = (
        db.query(Reminder)
        .filter(Reminder.dismissed_at == None, Reminder.remind_at <= now_str)  # noqa: E711
        .all()
    )

    lines = [f"CloseLoop Daily Digest — {date_str}", ""]
    if not reminders:
        lines.append("No overdue or due-today reminders.")
    else:
        lines.append(f"{len(reminders)} reminder(s) need your attention:")
        lines.append("")
        for r in reminders:
            a = r.activity
            if a:
                deal_info = f" (Deal: {a.deal.title})" if a.deal else ""
                contact_info = f" / {a.contact.name}" if a.contact else ""
                lines.append(f"  • [{a.type.upper()}] {a.title}{deal_info}{contact_info}")
                lines.append(f"    Due: {r.remind_at}")

    body = "\n".join(lines)
    msg = Outbox(
        to_address="digest@closeloop.local",
        subject=f"CloseLoop Digest — {date_str}",
        body=body,
        status="queued",
        created_at=now_str,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg)
