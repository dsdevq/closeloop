from datetime import datetime

import pytest

from app.core.lead_score import compute_lead_score


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
