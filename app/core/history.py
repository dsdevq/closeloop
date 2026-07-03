"""Typed audit history event model — pure, no I/O (ADR-0001).

Design:
  Discriminated union on the `kind` field, mirroring the notifications event
  model (app/core/notifications.py) but for entity-scoped audit history rather
  than user-scoped inbox notifications.

  Trigger mechanism borrowed from Salesforce Field History Tracking: history
  rows are written in the same transaction as the mutation, inline in the
  FastAPI route handler, before db.commit(). No async queue, no background
  worker (see .devclaw/research/activity-timeline.md §4).

  Structured payload per kind borrowed from Attio's activity stream and
  HubSpot's Timeline API: each dataclass carries exactly the fields needed to
  describe the event without a DB round-trip, avoiding the stale-message
  problem of pre-rendered strings.

  entity_id is stored as a plain INTEGER (no FK) so history entries survive
  deletion of the entity they describe — audit durability is the point.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal, Union


# ---------------------------------------------------------------------------
# Deal history events
# ---------------------------------------------------------------------------


@dataclass
class DealCreatedEntry:
    """A deal was created."""
    deal_id: int
    deal_title: str
    actor_id: int
    kind: Literal["deal_created"] = field(default="deal_created", init=False)


@dataclass
class DealStageChangedEntry:
    """A deal moved to a new pipeline stage."""
    deal_id: int
    deal_title: str
    actor_id: int
    from_stage: str | None          # None when created directly into a stage
    to_stage: str
    kind: Literal["deal_stage_changed"] = field(default="deal_stage_changed", init=False)


@dataclass
class DealAssignedEntry:
    """A deal's owner changed."""
    deal_id: int
    deal_title: str
    actor_id: int
    from_owner_id: int | None       # None when first assignment
    to_owner_id: int
    kind: Literal["deal_assigned"] = field(default="deal_assigned", init=False)


@dataclass
class DealUpdatedEntry:
    """Non-structural fields on a deal were updated (title, value, etc.).

    Field-level old/new values are deferred to a later slice; this entry
    records that a mutation occurred and who performed it.
    """
    deal_id: int
    deal_title: str
    actor_id: int
    kind: Literal["deal_updated"] = field(default="deal_updated", init=False)


@dataclass
class DealDeletedEntry:
    """A deal was deleted.

    entity_id on the HistoryEntry row is the former deal PK; no live row
    for that entity exists once this event is written.
    """
    deal_id: int
    deal_title: str
    actor_id: int
    kind: Literal["deal_deleted"] = field(default="deal_deleted", init=False)


# ---------------------------------------------------------------------------
# Contact history events
# ---------------------------------------------------------------------------


@dataclass
class ContactCreatedEntry:
    """A contact was created."""
    contact_id: int
    contact_name: str
    actor_id: int
    kind: Literal["contact_created"] = field(default="contact_created", init=False)


@dataclass
class ContactUpdatedEntry:
    """Fields on a contact were updated."""
    contact_id: int
    contact_name: str
    actor_id: int
    kind: Literal["contact_updated"] = field(default="contact_updated", init=False)


@dataclass
class ContactDeletedEntry:
    """A contact was deleted."""
    contact_id: int
    contact_name: str
    actor_id: int
    kind: Literal["contact_deleted"] = field(default="contact_deleted", init=False)


# ---------------------------------------------------------------------------
# Activity history events
# ---------------------------------------------------------------------------


@dataclass
class ActivityCreatedEntry:
    """An activity (call/email/meeting/note) was logged."""
    activity_id: int
    activity_title: str
    activity_type: str              # "call" / "email" / "meeting" / "note"
    actor_id: int
    deal_id: int | None
    contact_id: int | None
    kind: Literal["activity_created"] = field(default="activity_created", init=False)


@dataclass
class ActivityUpdatedEntry:
    """An activity was updated."""
    activity_id: int
    activity_title: str
    activity_type: str
    actor_id: int
    kind: Literal["activity_updated"] = field(default="activity_updated", init=False)


@dataclass
class ActivityCompletedEntry:
    """An activity was marked complete."""
    activity_id: int
    activity_title: str
    activity_type: str
    actor_id: int
    kind: Literal["activity_completed"] = field(default="activity_completed", init=False)


@dataclass
class ActivityDeletedEntry:
    """An activity was deleted."""
    activity_id: int
    activity_title: str
    activity_type: str
    actor_id: int
    kind: Literal["activity_deleted"] = field(default="activity_deleted", init=False)


# ---------------------------------------------------------------------------
# Public union type and kind registry
# ---------------------------------------------------------------------------

HistoryEvent = Union[
    DealCreatedEntry,
    DealStageChangedEntry,
    DealAssignedEntry,
    DealUpdatedEntry,
    DealDeletedEntry,
    ContactCreatedEntry,
    ContactUpdatedEntry,
    ContactDeletedEntry,
    ActivityCreatedEntry,
    ActivityUpdatedEntry,
    ActivityCompletedEntry,
    ActivityDeletedEntry,
]

# Single source of truth for the closed kind set (Pipedrive pattern).
_KIND_MAP: dict[str, type] = {
    "deal_created": DealCreatedEntry,
    "deal_stage_changed": DealStageChangedEntry,
    "deal_assigned": DealAssignedEntry,
    "deal_updated": DealUpdatedEntry,
    "deal_deleted": DealDeletedEntry,
    "contact_created": ContactCreatedEntry,
    "contact_updated": ContactUpdatedEntry,
    "contact_deleted": ContactDeletedEntry,
    "activity_created": ActivityCreatedEntry,
    "activity_updated": ActivityUpdatedEntry,
    "activity_completed": ActivityCompletedEntry,
    "activity_deleted": ActivityDeletedEntry,
}

ALL_HISTORY_KINDS: frozenset[str] = frozenset(_KIND_MAP)


# ---------------------------------------------------------------------------
# Serialisation / deserialisation
# meta_json is stored in HistoryEntry.meta_json; rendered at read time.
# ---------------------------------------------------------------------------


def event_to_meta(event: HistoryEvent) -> str:
    """Serialise a typed history event to a JSON string for storage in meta_json.

    asdict() includes init=False fields (like `kind`), so the round-trip
    through event_from_meta() is lossless.
    """
    return json.dumps(asdict(event))


def event_from_meta(meta: str) -> HistoryEvent:
    """Deserialise meta_json back to a typed HistoryEvent.

    Raises ValueError for unknown kinds or malformed payloads.
    """
    try:
        d: dict = json.loads(meta)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"invalid history meta JSON: {exc}") from exc

    kind = d.pop("kind", None)
    cls = _KIND_MAP.get(kind)  # type: ignore[arg-type]
    if cls is None:
        raise ValueError(f"unknown history kind: {kind!r}")

    try:
        return cls(**d)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            f"malformed history meta for kind={kind!r}: {exc}"
        ) from exc
