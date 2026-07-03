"""Pure unit tests for app/core/history.py.

No DB fixtures needed — all functions are pure and operate on plain values.
"""
import json

import pytest

from app.core.history import (
    ALL_HISTORY_KINDS,
    ActivityCompletedEntry,
    ActivityCreatedEntry,
    ActivityDeletedEntry,
    ActivityUpdatedEntry,
    ContactCreatedEntry,
    ContactDeletedEntry,
    ContactUpdatedEntry,
    DealAssignedEntry,
    DealCreatedEntry,
    DealDeletedEntry,
    DealStageChangedEntry,
    DealUpdatedEntry,
    event_from_meta,
    event_to_meta,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _deal_created(**kw) -> DealCreatedEntry:
    defaults = dict(deal_id=1, deal_title="Acme Deal", actor_id=2)
    return DealCreatedEntry(**{**defaults, **kw})


def _deal_stage_changed(**kw) -> DealStageChangedEntry:
    defaults = dict(
        deal_id=1, deal_title="Acme Deal", actor_id=2,
        from_stage="Prospecting", to_stage="Proposal",
    )
    return DealStageChangedEntry(**{**defaults, **kw})


def _deal_assigned(**kw) -> DealAssignedEntry:
    defaults = dict(
        deal_id=1, deal_title="Acme Deal", actor_id=2,
        from_owner_id=3, to_owner_id=4,
    )
    return DealAssignedEntry(**{**defaults, **kw})


def _deal_updated(**kw) -> DealUpdatedEntry:
    defaults = dict(deal_id=1, deal_title="Acme Deal", actor_id=2)
    return DealUpdatedEntry(**{**defaults, **kw})


def _deal_deleted(**kw) -> DealDeletedEntry:
    defaults = dict(deal_id=1, deal_title="Acme Deal", actor_id=2)
    return DealDeletedEntry(**{**defaults, **kw})


def _contact_created(**kw) -> ContactCreatedEntry:
    defaults = dict(contact_id=5, contact_name="Jane Doe", actor_id=2)
    return ContactCreatedEntry(**{**defaults, **kw})


def _activity_created(**kw) -> ActivityCreatedEntry:
    defaults = dict(
        activity_id=10, activity_title="Intro call", activity_type="call",
        actor_id=2, deal_id=1, contact_id=5,
    )
    return ActivityCreatedEntry(**{**defaults, **kw})


def _activity_completed(**kw) -> ActivityCompletedEntry:
    defaults = dict(
        activity_id=10, activity_title="Intro call", activity_type="call", actor_id=2,
    )
    return ActivityCompletedEntry(**{**defaults, **kw})


# ── ALL_HISTORY_KINDS ─────────────────────────────────────────────────────────


def test_all_history_kinds_contains_expected_values():
    assert ALL_HISTORY_KINDS == {
        "deal_created",
        "deal_stage_changed",
        "deal_assigned",
        "deal_updated",
        "deal_deleted",
        "contact_created",
        "contact_updated",
        "contact_deleted",
        "activity_created",
        "activity_updated",
        "activity_completed",
        "activity_deleted",
    }


# ── event_to_meta ─────────────────────────────────────────────────────────────


class TestEventToMeta:
    def test_deal_created_serialises_kind(self):
        d = json.loads(event_to_meta(_deal_created()))
        assert d["kind"] == "deal_created"

    def test_deal_stage_changed_serialises_from_and_to(self):
        e = _deal_stage_changed(from_stage="Prospecting", to_stage="Proposal")
        d = json.loads(event_to_meta(e))
        assert d["from_stage"] == "Prospecting"
        assert d["to_stage"] == "Proposal"

    def test_deal_stage_changed_from_stage_none(self):
        e = _deal_stage_changed(from_stage=None)
        d = json.loads(event_to_meta(e))
        assert d["from_stage"] is None

    def test_deal_assigned_serialises_owner_ids(self):
        e = _deal_assigned(from_owner_id=3, to_owner_id=7)
        d = json.loads(event_to_meta(e))
        assert d["from_owner_id"] == 3
        assert d["to_owner_id"] == 7

    def test_deal_assigned_from_owner_id_none_for_first_assignment(self):
        e = _deal_assigned(from_owner_id=None, to_owner_id=7)
        d = json.loads(event_to_meta(e))
        assert d["from_owner_id"] is None

    def test_activity_created_serialises_deal_and_contact(self):
        e = _activity_created(deal_id=5, contact_id=None)
        d = json.loads(event_to_meta(e))
        assert d["deal_id"] == 5
        assert d["contact_id"] is None

    def test_activity_type_preserved(self):
        e = _activity_created(activity_type="note")
        d = json.loads(event_to_meta(e))
        assert d["activity_type"] == "note"


# ── event_from_meta ───────────────────────────────────────────────────────────


class TestEventFromMeta:
    def test_round_trip_deal_created(self):
        original = _deal_created(deal_id=42, deal_title="Big Deal", actor_id=3)
        restored = event_from_meta(event_to_meta(original))
        assert isinstance(restored, DealCreatedEntry)
        assert restored.deal_id == 42
        assert restored.deal_title == "Big Deal"
        assert restored.actor_id == 3
        assert restored.kind == "deal_created"

    def test_round_trip_deal_stage_changed(self):
        original = _deal_stage_changed(from_stage="Prospecting", to_stage="Closed-Won")
        restored = event_from_meta(event_to_meta(original))
        assert isinstance(restored, DealStageChangedEntry)
        assert restored.from_stage == "Prospecting"
        assert restored.to_stage == "Closed-Won"

    def test_round_trip_deal_stage_changed_from_none(self):
        original = _deal_stage_changed(from_stage=None)
        restored = event_from_meta(event_to_meta(original))
        assert restored.from_stage is None

    def test_round_trip_deal_assigned(self):
        original = _deal_assigned(from_owner_id=None, to_owner_id=9)
        restored = event_from_meta(event_to_meta(original))
        assert isinstance(restored, DealAssignedEntry)
        assert restored.from_owner_id is None
        assert restored.to_owner_id == 9

    def test_round_trip_deal_updated(self):
        restored = event_from_meta(event_to_meta(_deal_updated()))
        assert isinstance(restored, DealUpdatedEntry)

    def test_round_trip_deal_deleted(self):
        restored = event_from_meta(event_to_meta(_deal_deleted()))
        assert isinstance(restored, DealDeletedEntry)

    def test_round_trip_contact_created(self):
        original = _contact_created(contact_id=7, contact_name="Bob")
        restored = event_from_meta(event_to_meta(original))
        assert isinstance(restored, ContactCreatedEntry)
        assert restored.contact_id == 7

    def test_round_trip_contact_updated(self):
        e = ContactUpdatedEntry(contact_id=1, contact_name="Alice", actor_id=2)
        restored = event_from_meta(event_to_meta(e))
        assert isinstance(restored, ContactUpdatedEntry)

    def test_round_trip_contact_deleted(self):
        e = ContactDeletedEntry(contact_id=1, contact_name="Alice", actor_id=2)
        restored = event_from_meta(event_to_meta(e))
        assert isinstance(restored, ContactDeletedEntry)

    def test_round_trip_activity_created(self):
        original = _activity_created(deal_id=None, contact_id=5)
        restored = event_from_meta(event_to_meta(original))
        assert isinstance(restored, ActivityCreatedEntry)
        assert restored.deal_id is None
        assert restored.contact_id == 5

    def test_round_trip_activity_updated(self):
        e = ActivityUpdatedEntry(
            activity_id=1, activity_title="X", activity_type="email", actor_id=2
        )
        restored = event_from_meta(event_to_meta(e))
        assert isinstance(restored, ActivityUpdatedEntry)

    def test_round_trip_activity_completed(self):
        restored = event_from_meta(event_to_meta(_activity_completed()))
        assert isinstance(restored, ActivityCompletedEntry)
        assert restored.kind == "activity_completed"

    def test_round_trip_activity_deleted(self):
        e = ActivityDeletedEntry(
            activity_id=1, activity_title="Old Call", activity_type="call", actor_id=2
        )
        restored = event_from_meta(event_to_meta(e))
        assert isinstance(restored, ActivityDeletedEntry)

    def test_unknown_kind_raises_value_error(self):
        bad = json.dumps({"kind": "no_such_kind", "foo": 1})
        with pytest.raises(ValueError, match="unknown history kind"):
            event_from_meta(bad)

    def test_malformed_json_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid history meta JSON"):
            event_from_meta("{not valid json")

    def test_missing_field_raises_value_error(self):
        # deal_created requires deal_id, deal_title, actor_id
        bad = json.dumps({"kind": "deal_created", "deal_id": 1})
        with pytest.raises(ValueError, match="malformed history meta"):
            event_from_meta(bad)
