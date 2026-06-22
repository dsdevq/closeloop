from datetime import datetime, timedelta

_STAGE_BONUS: dict[str, float] = {
    "qualified": 10.0,
    "proposal": 15.0,
    "negotiation": 20.0,
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
