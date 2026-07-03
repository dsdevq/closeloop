"""Notifications pull API (Pipedrive / HubSpot / Attio pull-model pattern).

Notifications are created by trigger wiring (later slices).
This router exposes only the retrieval and read-state management surface.
No WebSocket, no SSE — client polls GET /notifications (ADR-0010 compatible).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.core.notifications import event_from_payload, render_notification
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notification, User

router = APIRouter(prefix="/notifications")


def _to_out(n: Notification) -> dict:
    try:
        event = event_from_payload(n.payload_json)
        message = render_notification(event)
    except (ValueError, TypeError):
        message = ""
    return {
        "id": n.id,
        "kind": n.kind,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "actor_id": n.actor_id,
        "message": message,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the count of unread notifications for the authenticated user.

    Intended for frequent polling by the bell-icon badge.
    """
    count = (
        db.query(Notification)
        .filter(
            Notification.recipient_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .count()
    )
    return {"unread_count": count}


@router.get("")
def list_notifications(
    unread_only: Optional[bool] = False,
    limit: Optional[int] = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the authenticated user's notifications, newest first.

    unread_only=true restricts to notifications where read_at IS NULL.
    limit caps the result set (default 50, minimum 1).
    """
    if limit is not None and limit < 1:
        raise HTTPException(status_code=422, detail="limit must be a positive integer")

    query = db.query(Notification).filter(
        Notification.recipient_id == current_user.id
    )
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    query = query.order_by(Notification.created_at.desc())
    if limit is not None:
        query = query.limit(limit)

    return [_to_out(n) for n in query.all()]


@router.post("/read-all", status_code=204)
def mark_all_read(
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """Mark every unread notification for the authenticated user as read."""
    now = clk.now().isoformat()
    db.query(Notification).filter(
        Notification.recipient_id == current_user.id,
        Notification.read_at.is_(None),
    ).update({"read_at": now})
    db.commit()
    return Response(status_code=204)


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read.

    Returns the updated notification.
    404 if the notification does not exist or belongs to another user.
    Idempotent: marking an already-read notification is a no-op.
    """
    n = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.recipient_id == current_user.id,
        )
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")

    if n.read_at is None:
        n.read_at = clk.now().isoformat()
        db.commit()
        db.refresh(n)
    return _to_out(n)
