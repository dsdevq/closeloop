"""Notification creation service — thin DB-write layer (not pure core).

`create_notification` is the single entry point for trigger wiring in routers.
It derives `actor_id` from the event so callers only pass the recipient and
context fields — consistent with Attio's first-class `actor_id` on events and
Salesforce's typed notification creation API (internal, not a REST endpoint).

`resolve_mentioned_users` maps @mention tokens (from `parse_mentions()` in
app/core/notifications) to active User rows by email local-part — the I/O
counterpart to the pure `parse_mentions` function.

ADR-0001: this module has I/O (DB read/write) so it lives in app/services/, not app/core/.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.notifications import NotificationEvent, event_to_payload
from app.models import Notification, User


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


def resolve_mentioned_users(db: Session, tokens: list[str]) -> list[User]:
    """Resolve @mention tokens to active User rows by email local-part.

    Matches each token against the local part of User.email (the portion
    before the first '@'), case-insensitively, using ILIKE '<token>@%'.
    Returns unique active users in token order; tokens with no matching
    active user are silently skipped.

    Callers obtain tokens from `app.core.notifications.parse_mentions()`.
    """
    if not tokens:
        return []
    seen_ids: set[int] = set()
    users: list[User] = []
    for token in tokens:
        user = (
            db.query(User)
            .filter(User.email.ilike(f"{token}@%"), User.is_active == 1)
            .first()
        )
        if user and user.id not in seen_ids:
            seen_ids.add(user.id)
            users.append(user)
    return users
