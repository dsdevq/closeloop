"""Notification creation service — thin DB-write layer (not pure core).

`create_notification` is the single entry point for trigger wiring in routers.
It derives `actor_id` from the event so callers only pass the recipient and
context fields — consistent with Attio's first-class `actor_id` on events and
Salesforce's typed notification creation API (internal, not a REST endpoint).

ADR-0001: this module has I/O (DB write) so it lives in app/services/, not app/core/.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.notifications import NotificationEvent, event_to_payload
from app.models import Notification


def create_notification(
    db: Session,
    *,
    recipient_id: int,
    event: NotificationEvent,
    entity_type: str | None = None,
    entity_id: int | None = None,
    clk: Clock,
) -> Notification:
    """Insert a Notification row for *recipient_id*.

    actor_id is derived from `event.actor_id` when present (deal/stage/mention
    events); None for system-generated events (task_overdue).  The caller owns
    the DB transaction — this function calls db.add() but does NOT commit.
    """
    actor_id: int | None = getattr(event, "actor_id", None)
    n = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        kind=event.kind,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=event_to_payload(event),
        created_at=clk.now().isoformat(),
    )
    db.add(n)
    return n
