"""Typed notification event model — pure, no I/O (ADR-0001).

Design:
  Discriminated union on the `kind` field (Salesforce Platform Events +
  Attio's structured payload pattern).  Each event carries the context
  needed to render a human-readable message without a DB round-trip at
  render time, avoiding the stale-message problem of storing pre-rendered
  strings (rejected HubSpot / Pipedrive pattern).

Borrowed from reference CRMs:
  - Closed `kind` enum  → Pipedrive
  - Structured per-kind payload  → Attio
  - `actor_id` on events  → Attio, Salesforce
  - `MentionEvent` kind + `parse_mentions()`  → Zoho @mention / Salesforce Chatter
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Literal, Union


# ---------------------------------------------------------------------------
# Typed event definitions
# Each dataclass carries exactly the fields needed to render its message.
# `kind` is init=False so it is excluded from __init__ but included in asdict.
# ---------------------------------------------------------------------------


@dataclass
class DealAssignedEvent:
    """A deal was (re)assigned to a new owner."""
    deal_id: int
    deal_title: str
    actor_id: int
    previous_owner_id: int | None = None   # None = first-time assignment
    kind: Literal["deal_assigned"] = field(default="deal_assigned", init=False)


@dataclass
class StageChangedEvent:
    """A deal moved to a new pipeline stage."""
    deal_id: int
    deal_title: str
    actor_id: int
    from_stage: str | None   # None when a deal is created directly into a stage
    to_stage: str
    kind: Literal["stage_changed"] = field(default="stage_changed", init=False)


@dataclass
class TaskOverdueEvent:
    """An activity with a due_at is now past its due date."""
    activity_id: int
    activity_title: str
    due_at: str                            # ISO-8601 string
    kind: Literal["task_overdue"] = field(default="task_overdue", init=False)


@dataclass
class MentionEvent:
    """A user was @mentioned in a note body.

    Tokens are parsed by `app.core.notifications.parse_mentions()` and
    resolved to active User rows by `app.services.notifications.resolve_mentioned_users()`.
    Trigger wiring in `app/routers/activities.py` emits one MentionEvent per
    unique mentioned user (excluding the actor) whenever a note is created or
    its body is updated.
    """
    actor_id: int
    entity_type: str                       # "activity" | "deal" | "contact"
    entity_id: int
    snippet: str                           # short preview of the note (≤120 chars)
    kind: Literal["mention"] = field(default="mention", init=False)


# Public union type used in function signatures
NotificationEvent = Union[
    DealAssignedEvent,
    StageChangedEvent,
    TaskOverdueEvent,
    MentionEvent,
]

# Single source of truth for the closed kind set
_KIND_MAP: dict[str, type] = {
    "deal_assigned": DealAssignedEvent,
    "stage_changed": StageChangedEvent,
    "task_overdue": TaskOverdueEvent,
    "mention": MentionEvent,
}

ALL_KINDS: frozenset[str] = frozenset(_KIND_MAP)


# ---------------------------------------------------------------------------
# Serialisation / deserialisation
# payload_json is stored in Notification.payload_json; rendered at read time.
# ---------------------------------------------------------------------------


def event_to_payload(event: NotificationEvent) -> str:
    """Serialise a typed event to a JSON string for storage in payload_json.

    asdict() includes init=False fields (like `kind`), so the round-trip
    through event_from_payload() is lossless.
    """
    return json.dumps(asdict(event))


def event_from_payload(payload: str) -> NotificationEvent:
    """Deserialise payload_json back to a typed NotificationEvent.

    Raises ValueError for unknown kinds or malformed payloads.
    """
    try:
        d: dict = json.loads(payload)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"invalid notification payload JSON: {exc}") from exc

    kind = d.pop("kind", None)
    cls = _KIND_MAP.get(kind)  # type: ignore[arg-type]
    if cls is None:
        raise ValueError(f"unknown notification kind: {kind!r}")

    try:
        return cls(**d)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            f"malformed notification payload for kind={kind!r}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Rendering
# Pure function: event → one-line human-readable message string.
# The frontend uses `kind` for icon selection; `message` for display text.
# ---------------------------------------------------------------------------


def render_notification(event: NotificationEvent) -> str:
    """Return a one-line human-readable description of the event."""
    if isinstance(event, DealAssignedEvent):
        return f'Deal "{event.deal_title}" was assigned to you'

    if isinstance(event, StageChangedEvent):
        from_part = f"from {event.from_stage} " if event.from_stage else ""
        return f'Deal "{event.deal_title}" moved {from_part}to {event.to_stage}'

    if isinstance(event, TaskOverdueEvent):
        return f'Task "{event.activity_title}" is overdue (due {event.due_at})'

    if isinstance(event, MentionEvent):
        return f"You were mentioned in a {event.entity_type}"

    raise TypeError(f"unknown event type: {type(event)!r}")  # pragma: no cover


# ---------------------------------------------------------------------------
# @mention parsing
# Pure function: extracts @mention tokens from free-text note bodies.
# Borrowed from Zoho CRM @mention (Zoho treats mention as a first-class
# notification kind with its own payload — notifications-engine.md §2.5).
# Salesforce Chatter uses the same @ prefix convention.
# ---------------------------------------------------------------------------

# Negative lookbehind (?<!\w) prevents matching the @ inside email addresses
# (e.g. "alice@example.com" would otherwise produce a false "example.com" match).
_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9][A-Za-z0-9._+-]*)")


def parse_mentions(body: str) -> list[str]:
    """Extract @mention tokens from a free-text note body.

    Returns lowercase unique tokens (the string after @) in first-appearance
    order. Duplicates are discarded. The token must begin with a letter or
    digit, so a bare `@` or whitespace-only suffix is ignored.

    Resolution of tokens to User rows is handled by
    `app.services.notifications.resolve_mentioned_users` (has DB I/O).
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in _MENTION_RE.finditer(body or ""):
        token = m.group(1).lower()
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result
