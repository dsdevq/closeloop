from datetime import datetime

import pytest

from app.core.lead_score import compute_lead_score, compute_lead_score_v2


def _fixed_clock(dt: datetime):
    return lambda: dt


def test_zero_score_bare_contact_no_deals_no_activities():
    score = compute_lead_score({}, [], [])
    assert score == 0.0


def test_email_adds_five_points():
    score = compute_lead_score({"email": "x@x.com"}, [], [])
    assert score == pytest.approx(5.0)


def test_phone_adds_five_points():
    score = compute_lead_score({"phone": "+1555"}, [], [])
    assert score == pytest.approx(5.0)


def test_email_and_phone_add_ten_points():
    score = compute_lead_score({"email": "x@x.com", "phone": "+1"}, [], [])
    assert score == pytest.approx(10.0)


def test_deal_count_adds_ten_each_capped_at_thirty():
    one_deal = compute_lead_score({}, [{"stage": "lead"}], [])
    assert one_deal == pytest.approx(10.0)

    three_deals = compute_lead_score({}, [{"stage": "lead"}] * 3, [])
    assert three_deals == pytest.approx(30.0)

    # Cap at 30 — 5 deals should not exceed cap
    five_deals = compute_lead_score({}, [{"stage": "lead"}] * 5, [])
    assert five_deals == pytest.approx(30.0)


def test_stage_bonuses_increase_score():
    lead_score = compute_lead_score({}, [{"stage": "lead"}], [])
    qualified_score = compute_lead_score({}, [{"stage": "qualified"}], [])
    proposal_score = compute_lead_score({}, [{"stage": "proposal"}], [])
    negotiation_score = compute_lead_score({}, [{"stage": "negotiation"}], [])

    # +10 base per deal; stage bonuses: qualified+10, proposal+15, negotiation+20
    assert qualified_score > lead_score
    assert proposal_score > qualified_score
    assert negotiation_score > proposal_score

    assert qualified_score == pytest.approx(10.0 + 10.0)
    assert proposal_score == pytest.approx(10.0 + 15.0)
    assert negotiation_score == pytest.approx(10.0 + 20.0)


def test_recent_activity_within_window_adds_score():
    clock = _fixed_clock(datetime(2024, 2, 1))
    # Activity 15 days ago — inside 30-day window
    activities = [{"created_at": "2024-01-17T12:00:00"}]
    score = compute_lead_score({}, [], activities, clock=clock)
    assert score == pytest.approx(5.0)


def test_injected_clock_controls_recent_window():
    activities = [{"created_at": "2024-01-01T00:00:00"}]

    # Clock set 40 days later — activity falls outside 30-day window
    late_clock = _fixed_clock(datetime(2024, 2, 10))
    score_outside = compute_lead_score({}, [], activities, clock=late_clock)

    # Clock set 24 days later — activity is inside 30-day window
    early_clock = _fixed_clock(datetime(2024, 1, 25))
    score_inside = compute_lead_score({}, [], activities, clock=early_clock)

    assert score_inside > score_outside
    assert score_outside == pytest.approx(0.0)
    assert score_inside == pytest.approx(5.0)


def test_recent_activity_capped_at_twenty():
    clock = _fixed_clock(datetime(2024, 2, 1))
    # 10 activities all within the window — cap is 20 (4 × 5)
    activities = [{"created_at": "2024-01-20T00:00:00"} for _ in range(10)]
    score = compute_lead_score({}, [], activities, clock=clock)
    assert score == pytest.approx(20.0)


def test_score_capped_at_one_hundred():
    clock = _fixed_clock(datetime(2024, 2, 1))
    contact = {"email": "x@x.com", "phone": "+1"}
    many_deals = [{"stage": "negotiation"}] * 10
    many_activities = [{"created_at": "2024-01-20T00:00:00"} for _ in range(20)]
    score = compute_lead_score(contact, many_deals, many_activities, clock=clock)
    assert score <= 100.0


def test_timezone_aware_timestamps_handled():
    clock = _fixed_clock(datetime(2024, 2, 1))
    activities = [{"created_at": "2024-01-20T12:00:00+00:00"}]
    score = compute_lead_score({}, [], activities, clock=clock)
    assert score == pytest.approx(5.0)


# ── Lead-score v2 tests ───────────────────────────────────────────────────────

def test_v2_use_decay_false_matches_v1():
    """When use_decay=False and default weights, v2 must equal v1 exactly."""
    clock = _fixed_clock(datetime(2024, 2, 1))
    contact = {"email": "x@x.com", "phone": "+1"}
    deals = [{"stage": "qualified"}]
    activities = [{"created_at": "2024-01-20T00:00:00"}]
    v1 = compute_lead_score(contact, deals, activities, clock=clock)
    v2 = compute_lead_score_v2(contact, deals, activities, clock=clock, use_decay=False)
    assert v1 == v2


def test_v2_decay_reduces_score_for_older_activities():
    clock = _fixed_clock(datetime(2024, 2, 1))
    # Activity 1 day ago vs 25 days ago — decay mode should score day-1 higher
    recent_act = [{"created_at": "2024-01-31T00:00:00"}]
    old_act = [{"created_at": "2024-01-07T00:00:00"}]
    score_recent = compute_lead_score_v2({}, [], recent_act, clock=clock, use_decay=True)
    score_old = compute_lead_score_v2({}, [], old_act, clock=clock, use_decay=True)
    assert score_recent > score_old


def test_v2_activity_far_in_past_contributes_near_zero():
    clock = _fixed_clock(datetime(2024, 2, 1))
    # Activity 365 days ago with default half-life (15 days) → negligible contribution
    ancient = [{"created_at": "2023-02-01T00:00:00"}]
    score = compute_lead_score_v2({}, [], ancient, clock=clock, use_decay=True)
    assert score < 0.1


def test_v2_custom_weights_change_deal_base():
    score_default = compute_lead_score_v2({}, [{"stage": "lead"}], [], use_decay=False)
    score_custom = compute_lead_score_v2(
        {}, [{"stage": "lead"}], [], use_decay=False, weights={"deal_base": 20.0}
    )
    assert score_custom == pytest.approx(20.0)
    assert score_default == pytest.approx(10.0)


def test_v2_custom_weights_email_bonus():
    score = compute_lead_score_v2({"email": "x@x.com"}, [], [], weights={"email_bonus": 15.0})
    assert score == pytest.approx(15.0)


def test_v2_custom_weights_cap_is_respected():
    # deal_cap=5 means no matter how many deals, contribution capped at 5
    many_deals = [{"stage": "lead"}] * 10
    score = compute_lead_score_v2({}, many_deals, [], weights={"deal_cap": 5.0, "deal_base": 10.0})
    assert score == pytest.approx(5.0)


def test_v2_score_capped_at_100():
    clock = _fixed_clock(datetime(2024, 2, 1))
    contact = {"email": "x@x.com", "phone": "+1"}
    many_deals = [{"stage": "negotiation"}] * 10
    many_activities = [{"created_at": "2024-02-01T00:00:00"} for _ in range(50)]
    score = compute_lead_score_v2(
        contact, many_deals, many_activities, clock=clock, use_decay=False
    )
    assert score <= 100.0


def test_v2_monotonicity_more_recent_higher_score():
    """All else equal, a more recently active contact scores higher in decay mode."""
    clock = _fixed_clock(datetime(2024, 2, 1))
    five_days = [{"created_at": "2024-01-27T00:00:00"}]
    twenty_days = [{"created_at": "2024-01-12T00:00:00"}]
    assert (
        compute_lead_score_v2({}, [], five_days, clock=clock, use_decay=True)
        > compute_lead_score_v2({}, [], twenty_days, clock=clock, use_decay=True)
    )
