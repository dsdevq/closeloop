from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.models import Outbox

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
def list_messages(status: Optional[str] = None, db: Session = Depends(get_db)):
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
def get_message(message_id: int, db: Session = Depends(get_db)):
    msg = db.query(Outbox).filter(Outbox.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return _to_out(msg)


@router.delete("/{message_id}", status_code=204)
def delete_message(message_id: int, db: Session = Depends(get_db)):
    msg = db.query(Outbox).filter(Outbox.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    db.delete(msg)
    db.commit()
    return Response(status_code=204)
