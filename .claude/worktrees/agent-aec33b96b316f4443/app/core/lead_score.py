import math
from datetime import datetime, timedelta

_STAGE_BONUS: dict[str, float] = {
    "qualified": 10.0,
    "proposal": 15.0,
    "negotiation": 20.0,
}

# Default weights for v2 — chosen so a contact with max activity and richness
# approaches 100 pts (same ceiling as v1).
_DEFAULT_WEIGHTS_V2: dict[str, float] = {
    "deal_weight": 10.0,       # points per deal (before stage bonus)
    "stage_bonus_mult": 1.0,   # multiplier on _STAGE_BONUS values
    "max_deal_score": 30.0,    # cap for deal-count contribution
    "max_activity_score": 20.0,  # cap for activity contribution
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
    Score 0.0–100.0 for a contact.

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
    half_life_days: float = 14.0,
    weights: dict | None = None,
) -> float:
    """
    Lead score v2 with exponential decay on activity recency.

    Each activity contributes ``exp(-ln(2) * age_days / half_life_days)``
    (value approaches 1.0 for very recent, 0.5 at exactly half_life_days,
    approaches 0 for old activities).  Contributions are summed and scaled to
    the ``max_activity_score`` weight.

    Deal scoring and contact-richness bonuses match v1 (configurable via
    ``weights``).
    """
    w = dict(_DEFAULT_WEIGHTS_V2)
    if weights:
        w.update(weights)

    score = 0.0

    # Deal contribution (count-based, capped)
    score += min(len(deals) * w["deal_weight"], w["max_deal_score"])

    # Stage bonuses
    for deal in deals:
        bonus = _STAGE_BONUS.get(deal.get("stage", ""), 0.0)
        score += bonus * w["stage_bonus_mult"]

    # Activity contribution via exponential decay
    now = clock()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)

    _ln2 = math.log(2)
    decay_sum = 0.0
    for a in activities:
        dt = _parse_naive(a.get("created_at"))
        if dt is None:
            continue
        age_days = max((now - dt).total_seconds() / 86400.0, 0.0)
        decay_sum += math.exp(-_ln2 * age_days / half_life_days)

    # Normalise: one activity right now would contribute 1.0 raw; cap at max
    # We scale the raw sum so that ~4 recent activities hit the cap (same
    # feel as v1's "cap 20 = 4 × 5").
    scale = w["max_activity_score"] / max(w["max_activity_score"] / w.get("deal_weight", 10.0), 1.0)
    activity_score = min(decay_sum * (w["max_activity_score"] / 4.0), w["max_activity_score"])
    score += activity_score

    # Contact richness
    if contact.get("email"):
        score += w["email_bonus"]
    if contact.get("phone"):
        score += w["phone_bonus"]

    return round(min(score, 100.0), 1)
