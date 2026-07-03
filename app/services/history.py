"""Audit history creation service — thin DB-write layer (not pure core).

`record_history` is the single entry point for trigger wiring in routers.
It derives `actor_id` from the event so callers only pass the entity context
and the typed event — consistent with the notifications service pattern.

Trigger mechanism borrowed from Salesforce Field History Tracking
(activity-timeline.md §2.1): called inline in the router handler after the
domain mutation, before db.commit(). The caller owns the transaction — this
function calls db.add() but does NOT commit.

ADR-0001: this module has I/O (DB write) so it lives in app/services/, not app/core/.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.history import HistoryEvent, event_to_meta
from app.models import HistoryEntry


def record_history(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    event: HistoryEvent,
    clk: Clock,
) -> HistoryEntry:
    """Insert a HistoryEntry row for *entity_id*.

    actor_id is derived from `event.actor_id` (present on all HistoryEvent
    subclasses in this slice).  The caller owns the DB transaction — this
    function calls db.add() but does NOT commit.
    """
    entry = HistoryEntry(
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=event.actor_id,
        kind=event.kind,
        meta_json=event_to_meta(event),
        occurred_at=clk.now().isoformat(),
    )
    db.add(entry)
    return entry
