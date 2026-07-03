"""Pure unit tests for app/core/notifications.py.

No DB fixtures needed — all functions are pure and operate on plain values.
"""

import json

import pytest

from app.core.notifications import (
    ALL_KINDS,
    DealAssignedEvent,
    MentionEvent,
    StageChangedEvent,
    TaskOverdueEvent,
    event_from_payload,
    event_to_payload,
    render_notification,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _deal_assigned(**kw) -> DealAssignedEvent:
    defaults = dict(deal_id=1, deal_title="Big Deal", actor_id=2)
    return DealAssignedEvent(**{**defaults, **kw})


def _stage_changed(**kw) -> StageChangedEvent:
    defaults = dict(
        deal_id=1, deal_title="Big Deal", actor_id=2,
        from_stage="Qualification", to_stage="Proposal",
    )
    return StageChangedEvent(**{**defaults, **kw})


def _task_overdue(**kw) -> TaskOverdueEvent:
    defaults = dict(activity_id=5, activity_title="Follow up call", due_at="2026-07-01T09:00:00")
    return TaskOverdueEvent(**{**defaults, **kw})


def _mention(**kw) -> MentionEvent:
    defaults = dict(actor_id=3, entity_type="deal", entity_id=7, snippet="Can you check this?")
    return MentionEvent(**{**defaults, **kw})


# ── ALL_KINDS ─────────────────────────────────────────────────────────────────


def test_all_kinds_contains_expected_values():
    assert ALL_KINDS == {"deal_assigned", "stage_changed", "task_overdue", "mention"}


# ── event_to_payload ──────────────────────────────────────────────────────────


class TestEventToPayload:
    def test_deal_assigned_serialises_kind(self):
        payload = event_to_payload(_deal_assigned())
        d = json.loads(payload)
        assert d["kind"] == "deal_assigned"

    def test_deal_assigned_serialises_all_fields(self):
        e = _deal_assigned(deal_id=10, deal_title="Acme", actor_id=4, previous_owner_id=3)
        d = json.loads(event_to_payload(e))
        assert d["deal_id"] == 10
        assert d["deal_title"] == "Acme"
        assert d["actor_id"] == 4
        assert d["previous_owner_id"] == 3

    def test_deal_assigned_previous_owner_null_when_first_assignment(self):
        d = json.loads(event_to_payload(_deal_assigned()))
        assert d["previous_owner_id"] is None

    def test_stage_changed_serialises_from_and_to(self):
        e = _stage_changed(from_stage="Qualification", to_stage="Proposal")
        d = json.loads(event_to_payload(e))
        assert d["from_stage"] == "Qualification"
        assert d["to_stage"] == "Proposal"
        assert d["kind"] == "stage_changed"

    def test_stage_changed_from_stage_can_be_none(self):
        e = _stage_changed(from_stage=None, to_stage="Prospecting")
        d = json.loads(event_to_payload(e))
        assert d["from_stage"] is None

    def test_task_overdue_serialises_all_fields(self):
        e = _task_overdue()
        d = json.loads(event_to_payload(e))
        assert d["kind"] == "task_overdue"
        assert d["activity_id"] == 5
        assert d["activity_title"] == "Follow up call"
        assert d["due_at"] == "2026-07-01T09:00:00"

    def test_mention_serialises_snippet(self):
        e = _mention(snippet="Hey, take a look at this!")
        d = json.loads(event_to_payload(e))
        assert d["kind"] == "mention"
        assert d["snippet"] == "Hey, take a look at this!"


# ── event_from_payload ────────────────────────────────────────────────────────


class TestEventFromPayload:
    @pytest.mark.parametrize("event", [
        _deal_assigned(),
        _deal_assigned(previous_owner_id=99),
        _stage_changed(),
        _stage_changed(from_stage=None),
        _task_overdue(),
        _mention(),
    ])
    def test_roundtrip(self, event):
        reconstructed = event_from_payload(event_to_payload(event))
        assert reconstructed == event

    def test_unknown_kind_raises_value_error(self):
        payload = json.dumps({"kind": "mystery_kind", "x": 1})
        with pytest.raises(ValueError, match="unknown notification kind"):
            event_from_payload(payload)

    def test_invalid_json_raises_value_error(self):
        with pytest.raises(ValueError, match="invalid notification payload JSON"):
            event_from_payload("not json at all")

    def test_missing_required_field_raises_value_error(self):
        # deal_id is required but omitted
        payload = json.dumps({"kind": "deal_assigned", "deal_title": "x", "actor_id": 1})
        with pytest.raises(ValueError, match="malformed notification payload"):
            event_from_payload(payload)

    def test_extra_fields_raise_value_error(self):
        # Unexpected keyword causes TypeError → ValueError
        payload = json.dumps({
            "kind": "deal_assigned",
            "deal_id": 1,
            "deal_title": "x",
            "actor_id": 2,
            "previous_owner_id": None,
            "unexpected_field": True,
        })
        with pytest.raises(ValueError, match="malformed notification payload"):
            event_from_payload(payload)

    def test_kind_absent_raises_value_error(self):
        payload = json.dumps({"deal_id": 1, "deal_title": "x", "actor_id": 2})
        with pytest.raises(ValueError, match="unknown notification kind"):
            event_from_payload(payload)


# ── render_notification ───────────────────────────────────────────────────────


class TestRenderNotification:
    def test_deal_assigned_message(self):
        msg = render_notification(_deal_assigned(deal_title="Acme Corp"))
        assert msg == 'Deal "Acme Corp" was assigned to you'

    def test_stage_changed_with_from_stage(self):
        msg = render_notification(_stage_changed(
            deal_title="Acme Corp",
            from_stage="Qualification",
            to_stage="Proposal",
        ))
        assert msg == 'Deal "Acme Corp" moved from Qualification to Proposal'

    def test_stage_changed_without_from_stage(self):
        msg = render_notification(_stage_changed(
            deal_title="New Deal",
            from_stage=None,
            to_stage="Prospecting",
        ))
        assert msg == 'Deal "New Deal" moved to Prospecting'

    def test_task_overdue_message(self):
        msg = render_notification(_task_overdue(
            activity_title="Send proposal",
            due_at="2026-06-30T17:00:00",
        ))
        assert msg == 'Task "Send proposal" is overdue (due 2026-06-30T17:00:00)'

    def test_mention_deal(self):
        msg = render_notification(_mention(entity_type="deal"))
        assert msg == "You were mentioned in a deal"

    def test_mention_activity(self):
        msg = render_notification(_mention(entity_type="activity"))
        assert msg == "You were mentioned in a activity"

    def test_mention_contact(self):
        msg = render_notification(_mention(entity_type="contact"))
        assert msg == "You were mentioned in a contact"


# ── Event field invariants ────────────────────────────────────────────────────


class TestEventKindField:
    def test_deal_assigned_kind_is_not_in_init(self):
        # kind must not appear in __init__ — only set by the dataclass default
        import inspect
        sig = inspect.signature(DealAssignedEvent.__init__)
        assert "kind" not in sig.parameters

    def test_stage_changed_kind_is_not_in_init(self):
        import inspect
        sig = inspect.signature(StageChangedEvent.__init__)
        assert "kind" not in sig.parameters

    def test_task_overdue_kind_is_not_in_init(self):
        import inspect
        sig = inspect.signature(TaskOverdueEvent.__init__)
        assert "kind" not in sig.parameters

    def test_mention_kind_is_not_in_init(self):
        import inspect
        sig = inspect.signature(MentionEvent.__init__)
        assert "kind" not in sig.parameters

    @pytest.mark.parametrize("event,expected_kind", [
        (_deal_assigned(), "deal_assigned"),
        (_stage_changed(), "stage_changed"),
        (_task_overdue(), "task_overdue"),
        (_mention(), "mention"),
    ])
    def test_kind_attribute_matches_expected(self, event, expected_kind):
        assert event.kind == expected_kind
