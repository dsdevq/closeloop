import math
from datetime import datetime, timedelta

_STAGE_BONUS: dict[str, float] = {
    "qualified": 10.0,
    "proposal": 15.0,
    "negotiation": 20.0,
}

# Default weights for v1-compatible scoring
_DEFAULT_WEIGHTS: dict[str, float] = {
    "deal_base": 10.0,
    "deal_cap": 30.0,
    "activity_base": 5.0,
    "activity_cap": 20.0,
    "activity_window_days": 30.0,
    "email_bonus": 5.0,
    "phone_bonus": 5.0,
}


def _parse_naive(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp to a naive UTC datetime, stripping tz info."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    except (ValueError, TypeError):
        return None


def compute_lead_score(
    contact: dict,
    deals: list[dict],
    activities: list[dict],
    *,
    clock: object = datetime.utcnow,
) -> float:
    """
    Score 0.0–100.0 for a contact (v1 formula, backward-compatible).

    +10 per deal (cap 30), stage bonuses (qualified+10, proposal+15, negotiation+20),
    +5 per activity in last 30 days (cap 20), +5 for email, +5 for phone.
    """
    score = 0.0

    # Deals: +10 each, cap 30
    score += min(len(deals) * 10.0, 30.0)

    # Stage bonuses
    for deal in deals:
        score += _STAGE_BONUS.get(deal.get("stage", ""), 0.0)

    # Recent activities in last 30 days: +5 each, cap 20
    now = clock()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    cutoff = now - timedelta(days=30)

    recent = 0
    for a in activities:
        dt = _parse_naive(a.get("created_at"))
        if dt is not None and dt >= cutoff:
            recent += 1
    score += min(recent * 5.0, 20.0)

    # Contact richness
    if contact.get("email"):
        score += 5.0
    if contact.get("phone"):
        score += 5.0

    return round(min(score, 100.0), 1)


def compute_lead_score_v2(
    contact: dict,
    deals: list[dict],
    activities: list[dict],
    *,
    clock: object = datetime.utcnow,
    weights: dict[str, float] | None = None,
    use_decay: bool = True,
) -> float:
    """
    Score 0.0–100.0 for a contact (v2 formula).

    Identical structure to v1 but adds:
    - Temporal decay on activity contribution: each activity's score decays
      exponentially as it ages, using half-life = activity_window_days/2.
      An activity at t=0 contributes full activity_base; at t=window/2 it
      contributes activity_base/2; beyond window it contributes < 5% of base.
    - Configurable weights via the `weights` dict (keys mirror _DEFAULT_WEIGHTS).

    When use_decay=False the result matches v1 exactly (useful for backtests).
    """
    w = {**_DEFAULT_WEIGHTS, **(weights or {})}

    score = 0.0

    # Deals: +deal_base each, cap deal_cap
    score += min(len(deals) * w["deal_base"], w["deal_cap"])

    # Stage bonuses (not configurable — structural feature, not a weight)
    for deal in deals:
        score += _STAGE_BONUS.get(deal.get("stage", ""), 0.0)

    now = clock()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)

    window = w["activity_window_days"]
    half_life = window / 2.0  # exponential decay half-life

    activity_score = 0.0
    for a in activities:
        dt = _parse_naive(a.get("created_at"))
        if dt is None:
            continue
        days_ago = (now - dt).total_seconds() / 86400
        if days_ago < 0:
            days_ago = 0.0
        if use_decay:
            # Exponential decay: score = base * 2^(-days_ago / half_life)
            contribution = w["activity_base"] * math.pow(2.0, -days_ago / half_life)
        else:
            # Binary window (v1 compatible)
            contribution = w["activity_base"] if days_ago <= window else 0.0
        activity_score += contribution

    score += min(activity_score, w["activity_cap"])

    # Contact richness
    if contact.get("email"):
        score += w["email_bonus"]
    if contact.get("phone"):
        score += w["phone_bonus"]

    return round(min(score, 100.0), 1)
