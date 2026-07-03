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
  - `MentionEvent` kind  → Zoho (parsing deferred to a later slice)
"""
from __future__ import annotations

import json
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

    Parsing @user tokens from note bodies is deferred to a later slice;
    this type is defined here so the schema is ready and consistent.
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
