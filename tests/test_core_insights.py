"""Pure unit tests for app/core/insights.py.

No DB fixtures needed — functions are pure and operate on plain dicts.
"""

from datetime import datetime, timedelta

import pytest

from app.core.insights import (
    conversion_funnel,
    rep_leaderboard,
    source_cohorts,
    trends,
)

_NOW = datetime(2025, 6, 1, 12, 0, 0)
_CLOCK = lambda: _NOW  # noqa: E731


# ── fixture helpers ───────────────────────────────────────────────────────────

def _deal(
    *,
    stage: str = "lead",
    value: float = 1000.0,
    owner_id: int | None = 1,
    owner_name: str | None = None,
    contact_id: int = 1,
    created_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> dict:
    created = created_at if created_at is not None else (_NOW - timedelta(days=10))
    return {
        "stage": stage,
        "value": value,
        "owner_id": owner_id,
        "owner_name": owner_name,
        "contact_id": contact_id,
        "created_at": created.isoformat(),
        "closed_at": closed_at.isoformat() if closed_at is not None else None,
    }


def _contact(*, id: int = 1, source: str | None = "inbound") -> dict:
    return {"id": id, "source": source}


def _transition(
    *,
    deal_id: int,
    to_stage: str,
    occurred_at: datetime,
    from_stage: str | None = None,
) -> dict:
    return {
        "deal_id": deal_id,
        "to_stage": to_stage,
        "from_stage": from_stage,
        "occurred_at": occurred_at.isoformat(),
    }


# ── trends ────────────────────────────────────────────────────────────────────

class TestTrends:
    def test_empty_deals_returns_empty(self):
        assert trends([], 30, clock=_CLOCK) == {}

    def test_counts_deals_within_window(self):
        deals = [
            _deal(stage="lead", created_at=_NOW - timedelta(days=5)),
            _deal(stage="qualified", created_at=_NOW - timedelta(days=10)),
        ]
        result = trends(deals, 30, clock=_CLOCK)
        assert result == {"lead": 1, "qualified": 1}

    def test_excludes_deals_outside_window(self):
        deals = [
            _deal(stage="lead", created_at=_NOW - timedelta(days=5)),
            _deal(stage="lead", created_at=_NOW - timedelta(days=31)),
        ]
        result = trends(deals, 30, clock=_CLOCK)
        assert result == {"lead": 1}

    def test_aggregates_multiple_deals_per_stage(self):
        deals = [
            _deal(stage="lead", created_at=_NOW - timedelta(days=1)),
            _deal(stage="lead", created_at=_NOW - timedelta(days=2)),
            _deal(stage="qualified", created_at=_NOW - timedelta(days=3)),
        ]
        result = trends(deals, 30, clock=_CLOCK)
        assert result["lead"] == 2
        assert result["qualified"] == 1

    def test_wider_window_includes_older_deals(self):
        deals = [_deal(stage="lead", created_at=_NOW - timedelta(days=100))]
        assert trends(deals, 30, clock=_CLOCK) == {}
        assert trends(deals, 365, clock=_CLOCK) == {"lead": 1}

    def test_deal_at_exact_cutoff_included(self):
        # cutoff = now - window_days; created_at == cutoff means created >= cutoff → included
        deals = [_deal(stage="lead", created_at=_NOW - timedelta(days=30))]
        assert trends(deals, 30, clock=_CLOCK) == {"lead": 1}

    def test_deal_one_second_past_cutoff_excluded(self):
        deals = [_deal(stage="lead", created_at=_NOW - timedelta(days=30, seconds=1))]
        assert trends(deals, 30, clock=_CLOCK) == {}

    def test_deal_one_second_before_cutoff_included(self):
        deals = [_deal(stage="lead", created_at=_NOW - timedelta(days=29, hours=23, minutes=59))]
        result = trends(deals, 30, clock=_CLOCK)
        assert result == {"lead": 1}

    def test_deal_without_created_at_excluded(self):
        deal = _deal(stage="lead")
        deal["created_at"] = None
        assert trends([deal], 30, clock=_CLOCK) == {}


# ── conversion_funnel ─────────────────────────────────────────────────────────

class TestConversionFunnel:
    def test_all_four_funnel_stages_always_present(self):
        result = conversion_funnel([])
        assert set(result.keys()) == {"lead", "qualified", "proposal", "negotiation"}

    def test_empty_deals_all_zero_rates(self):
        result = conversion_funnel([])
        for stage_data in result.values():
            assert stage_data["conversion_rate"] == 0.0

    def test_conversion_rate_math(self):
        # 40 lead, 30 qualified, 20 proposal, 10 won — no negotiation, no lost
        # lead:       past=60 (30+20+10), at_or_past=100 (40+60)   → 0.60
        # qualified:  past=30 (20+10),    at_or_past=60  (30+30)   → 0.50
        # proposal:   past=10 (won),      at_or_past=30  (20+10)   → 0.3333
        # negotiation:past=10 (won),      at_or_past=10  (0+10)    → 1.00
        deals = (
            [_deal(stage="lead")] * 40
            + [_deal(stage="qualified")] * 30
            + [_deal(stage="proposal")] * 20
            + [_deal(stage="won")] * 10
        )
        result = conversion_funnel(deals)
        assert result["lead"]["conversion_rate"] == pytest.approx(0.6, abs=1e-4)
        assert result["qualified"]["conversion_rate"] == pytest.approx(0.5, abs=1e-4)
        assert result["proposal"]["conversion_rate"] == pytest.approx(1 / 3, abs=1e-4)
        assert result["negotiation"]["conversion_rate"] == pytest.approx(1.0, abs=1e-4)

    def test_lost_deals_excluded_from_snapshot_counts(self):
        # lost deals should not appear in at_or_past counts for open stages
        deals = [_deal(stage="lead"), _deal(stage="lost"), _deal(stage="lost")]
        result = conversion_funnel(deals)
        # lead: past=0, at_or_past=1 (only the lead deal) → 0.0
        assert result["lead"]["conversion_rate"] == pytest.approx(0.0)

    def test_terminal_stages_absent_from_result(self):
        result = conversion_funnel([_deal(stage="won"), _deal(stage="lost")])
        assert "won" not in result
        assert "lost" not in result

    def test_avg_time_in_stage_none_without_history(self):
        result = conversion_funnel([_deal(stage="lead")])
        for stage_data in result.values():
            assert stage_data["avg_time_in_stage_days"] is None

    def test_avg_time_in_stage_from_transitions(self):
        base = datetime(2025, 1, 1)
        history = [
            _transition(deal_id=1, to_stage="lead", occurred_at=base),
            _transition(deal_id=1, to_stage="qualified", occurred_at=base + timedelta(days=5)),
            _transition(deal_id=1, to_stage="won", occurred_at=base + timedelta(days=12)),
        ]
        result = conversion_funnel([_deal(stage="won")], stage_history=history)
        assert result["lead"]["avg_time_in_stage_days"] == pytest.approx(5.0)
        assert result["qualified"]["avg_time_in_stage_days"] == pytest.approx(7.0)
        # won is terminal — no avg_time entry for it; proposal/negotiation not in history
        assert result["proposal"]["avg_time_in_stage_days"] is None

    def test_avg_time_in_stage_averaged_across_deals(self):
        base = datetime(2025, 1, 1)
        history = [
            # deal 1: 4 days in lead
            _transition(deal_id=1, to_stage="lead", occurred_at=base),
            _transition(deal_id=1, to_stage="won", occurred_at=base + timedelta(days=4)),
            # deal 2: 8 days in lead
            _transition(deal_id=2, to_stage="lead", occurred_at=base),
            _transition(deal_id=2, to_stage="won", occurred_at=base + timedelta(days=8)),
        ]
        result = conversion_funnel(
            [_deal(stage="won"), _deal(stage="won")], stage_history=history
        )
        assert result["lead"]["avg_time_in_stage_days"] == pytest.approx(6.0)  # (4+8)/2


# ── rep_leaderboard ───────────────────────────────────────────────────────────

class TestRepLeaderboard:
    def test_empty_deals_returns_empty(self):
        assert rep_leaderboard([]) == []

    def test_non_won_deals_excluded(self):
        deals = [_deal(stage="lead", owner_id=1), _deal(stage="lost", owner_id=1)]
        assert rep_leaderboard(deals) == []

    def test_aggregates_revenue_and_count_per_rep(self):
        deals = [
            _deal(stage="won", value=1000.0, owner_id=1),
            _deal(stage="won", value=2000.0, owner_id=1),
        ]
        result = rep_leaderboard(deals)
        assert len(result) == 1
        row = result[0]
        assert row["owner_id"] == 1
        assert row["revenue"] == pytest.approx(3000.0)
        assert row["deals_closed"] == 2

    def test_avg_cycle_days_calculated_correctly(self):
        deals = [
            _deal(stage="won", owner_id=1, created_at=_NOW - timedelta(days=10), closed_at=_NOW),
            _deal(stage="won", owner_id=1, created_at=_NOW - timedelta(days=20), closed_at=_NOW),
        ]
        result = rep_leaderboard(deals)
        assert result[0]["avg_cycle_days"] == pytest.approx(15.0)  # (10 + 20) / 2

    def test_avg_cycle_days_none_when_closed_at_missing(self):
        deal = _deal(stage="won", owner_id=1)
        # closed_at is None by default from _deal()
        result = rep_leaderboard([deal])
        assert result[0]["avg_cycle_days"] is None

    def test_sorted_by_revenue_descending(self):
        deals = [
            _deal(stage="won", value=500.0, owner_id=2),
            _deal(stage="won", value=1500.0, owner_id=1),
        ]
        result = rep_leaderboard(deals)
        assert result[0]["owner_id"] == 1
        assert result[1]["owner_id"] == 2

    def test_scope_none_includes_all_reps(self):
        deals = [
            _deal(stage="won", value=1000.0, owner_id=1),
            _deal(stage="won", value=2000.0, owner_id=2),
        ]
        result = rep_leaderboard(deals, scope=None)
        assert len(result) == 2

    def test_scope_rep_id_excludes_other_reps_deals(self):
        """rep_leaderboard must enforce the scope restriction itself."""
        deals = [
            _deal(stage="won", value=5000.0, owner_id=1),
            _deal(stage="won", value=9999.0, owner_id=2),  # must be excluded
        ]
        result = rep_leaderboard(deals, scope=1)
        assert len(result) == 1
        assert result[0]["owner_id"] == 1
        assert result[0]["revenue"] == pytest.approx(5000.0)

    def test_scope_rep_id_sees_only_own_aggregate_metrics(self):
        deals = [
            _deal(stage="won", value=1000.0, owner_id=1),
            _deal(stage="won", value=2000.0, owner_id=1),
            _deal(stage="won", value=9999.0, owner_id=99),  # different rep — excluded
        ]
        result = rep_leaderboard(deals, scope=1)
        assert len(result) == 1
        assert result[0]["deals_closed"] == 2
        assert result[0]["revenue"] == pytest.approx(3000.0)

    def test_avg_cycle_days_excludes_open_deals(self):
        """Open deals (no closed_at) must not affect avg_cycle_days for won deals."""
        deals = [
            _deal(stage="won", owner_id=1, created_at=_NOW - timedelta(days=10), closed_at=_NOW),
            _deal(stage="lead", owner_id=1),  # open — excluded from avg and row entirely
        ]
        result = rep_leaderboard(deals)
        assert len(result) == 1  # only the won deal creates a row
        assert result[0]["avg_cycle_days"] == pytest.approx(10.0)

    def test_avg_cycle_days_partial_when_some_won_deals_lack_closed_at(self):
        """Won deals missing closed_at are excluded from cycle avg but count toward revenue."""
        deals = [
            _deal(stage="won", owner_id=1, value=1000.0,
                  created_at=_NOW - timedelta(days=10), closed_at=_NOW),
            _deal(stage="won", owner_id=1, value=2000.0),  # closed_at=None
        ]
        result = rep_leaderboard(deals)
        assert len(result) == 1
        row = result[0]
        assert row["revenue"] == pytest.approx(3000.0)
        assert row["deals_closed"] == 2
        # Only the first deal contributes to the average
        assert row["avg_cycle_days"] == pytest.approx(10.0)

    def test_deal_without_owner_id_excluded(self):
        deal = _deal(stage="won", owner_id=None)
        assert rep_leaderboard([deal]) == []

    def test_multiple_reps_each_get_correct_totals(self):
        deals = [
            _deal(stage="won", value=100.0, owner_id=1),
            _deal(stage="won", value=200.0, owner_id=2),
            _deal(stage="won", value=300.0, owner_id=1),
        ]
        result = rep_leaderboard(deals)
        by_owner = {r["owner_id"]: r for r in result}
        assert by_owner[1]["revenue"] == pytest.approx(400.0)
        assert by_owner[1]["deals_closed"] == 2
        assert by_owner[2]["revenue"] == pytest.approx(200.0)
        assert by_owner[2]["deals_closed"] == 1

    def test_owner_name_present_in_every_row(self):
        deals = [_deal(stage="won", owner_id=1, owner_name="Alice Jones")]
        result = rep_leaderboard(deals)
        assert len(result) == 1
        assert "owner_name" in result[0]
        assert result[0]["owner_name"] == "Alice Jones"

    def test_owner_name_none_when_user_deleted(self):
        """Deals whose owner has been deleted arrive with owner_name=None; row still appears."""
        deals = [_deal(stage="won", owner_id=42, owner_name=None)]
        result = rep_leaderboard(deals)
        assert len(result) == 1
        assert result[0]["owner_name"] is None

    def test_owner_name_first_non_none_wins_across_multiple_deals(self):
        """When multiple deals share an owner, the first non-None name is kept."""
        deals = [
            _deal(stage="won", owner_id=7, owner_name=None),
            _deal(stage="won", owner_id=7, owner_name="Bob Smith"),
            _deal(stage="won", owner_id=7, owner_name="Should Not Win"),
        ]
        result = rep_leaderboard(deals)
        assert len(result) == 1
        assert result[0]["owner_name"] == "Bob Smith"


# ── source_cohorts ────────────────────────────────────────────────────────────

class TestSourceCohorts:
    def test_empty_returns_empty(self):
        assert source_cohorts([], []) == {}

    def test_groups_deals_by_contact_source(self):
        contacts = [_contact(id=1, source="referral"), _contact(id=2, source="inbound")]
        deals = [_deal(contact_id=1), _deal(contact_id=2)]
        result = source_cohorts(deals, contacts)
        assert "referral" in result
        assert "inbound" in result

    def test_avg_deal_value_per_source(self):
        contacts = [_contact(id=1, source="referral")]
        deals = [
            _deal(value=1000.0, contact_id=1),
            _deal(value=3000.0, contact_id=1),
        ]
        result = source_cohorts(deals, contacts)
        assert result["referral"]["avg_deal_value"] == pytest.approx(2000.0)

    def test_win_rate_per_source(self):
        contacts = [_contact(id=1, source="outbound")]
        deals = [
            _deal(stage="won", contact_id=1),
            _deal(stage="won", contact_id=1),
            _deal(stage="lead", contact_id=1),
            _deal(stage="lost", contact_id=1),
        ]
        result = source_cohorts(deals, contacts)
        assert result["outbound"]["win_rate"] == pytest.approx(0.5)  # 2 won / 4 total

    def test_deal_count_per_source(self):
        contacts = [_contact(id=1, source="event"), _contact(id=2, source="event")]
        deals = [_deal(contact_id=1), _deal(contact_id=2), _deal(contact_id=2)]
        result = source_cohorts(deals, contacts)
        assert result["event"]["deal_count"] == 3

    def test_missing_source_mapped_to_other(self):
        contacts = [_contact(id=1, source=None)]
        deals = [_deal(contact_id=1)]
        result = source_cohorts(deals, contacts)
        assert "other" in result
        assert result["other"]["deal_count"] == 1

    def test_unknown_contact_id_mapped_to_other(self):
        # No contact with id=999 in the contacts list
        deals = [_deal(contact_id=999)]
        result = source_cohorts(deals, [])
        assert "other" in result
        assert result["other"]["deal_count"] == 1

    def test_zero_win_rate_when_no_won_deals(self):
        contacts = [_contact(id=1, source="inbound")]
        deals = [_deal(stage="lead", contact_id=1), _deal(stage="lost", contact_id=1)]
        result = source_cohorts(deals, contacts)
        assert result["inbound"]["win_rate"] == pytest.approx(0.0)

    def test_multiple_sources_independent(self):
        contacts = [
            _contact(id=1, source="referral"),
            _contact(id=2, source="inbound"),
        ]
        deals = [
            _deal(stage="won", value=5000.0, contact_id=1),
            _deal(stage="lead", value=1000.0, contact_id=2),
            _deal(stage="lead", value=2000.0, contact_id=2),
        ]
        result = source_cohorts(deals, contacts)
        assert result["referral"]["win_rate"] == pytest.approx(1.0)
        assert result["referral"]["avg_deal_value"] == pytest.approx(5000.0)
        assert result["inbound"]["win_rate"] == pytest.approx(0.0)
        assert result["inbound"]["avg_deal_value"] == pytest.approx(1500.0)
        assert result["inbound"]["deal_count"] == 2
