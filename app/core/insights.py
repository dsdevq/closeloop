"""CRM pipeline insights and analytics aggregations.

Pure functions — no I/O, no DB access, injectable clock (ADR-0006).
All timestamps are ISO-8601 strings; parsed internally.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Open pipeline stages in funnel order (terminal stages excluded)
_FUNNEL_STAGES: list[str] = ["lead", "qualified", "proposal", "negotiation"]
_TERMINAL: frozenset[str] = frozenset({"won", "lost"})


def _parse_naive(ts: str | None) -> datetime | None:
    """Parse ISO-8601 string to a naive UTC datetime, stripping tz info."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    except (ValueError, TypeError):
        return None


def trends(
    deals: list[dict],
    window_days: int = 30,
    *,
    clock: object = datetime.utcnow,
) -> dict[str, int]:
    """Count of deals by current stage created within window_days of now.

    window_days is typically 30, 90, or 365.
    Deals without a parseable created_at are excluded.
    """
    now = clock()
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    cutoff = now - timedelta(days=window_days)

    result: dict[str, int] = {}
    for deal in deals:
        created = _parse_naive(deal.get("created_at"))
        if created is None or created < cutoff:
            continue
        stage = deal.get("stage", "")
        result[stage] = result.get(stage, 0) + 1
    return result


def conversion_funnel(
    deals: list[dict],
    stage_history: list[dict] | None = None,
) -> dict[str, dict]:
    """Per-stage conversion rate and average time spent in each open stage.

    Conversion rate for stage S = deals now at a later open stage (or won)
    divided by deals at stage S or any later open stage (or won).  Lost deals
    are excluded from the snapshot because their prior stage is unknown.

    stage_history is a flat list of StageTransition dicts (keys: deal_id,
    to_stage, occurred_at).  When provided, avg_time_in_stage_days is computed
    for each open stage; otherwise it is None.

    Returns a dict keyed by the four open funnel stages.
    """
    counts: dict[str, int] = {}
    for deal in deals:
        stage = deal.get("stage", "")
        counts[stage] = counts.get(stage, 0) + 1

    avg_times: dict[str, float] = {}
    if stage_history:
        stage_durations: dict[str, list[float]] = {}
        # Group transitions by deal so we can measure inter-transition gaps
        by_deal: dict[object, list[dict]] = {}
        for t in stage_history:
            by_deal.setdefault(t.get("deal_id"), []).append(t)
        for trans_list in by_deal.values():
            sorted_trans = sorted(trans_list, key=lambda t: t.get("occurred_at", ""))
            for i, t in enumerate(sorted_trans):
                stage = t.get("to_stage", "")
                if stage in _TERMINAL or i + 1 >= len(sorted_trans):
                    continue
                entered = _parse_naive(t["occurred_at"])
                exited = _parse_naive(sorted_trans[i + 1]["occurred_at"])
                if entered is None or exited is None:
                    continue
                days = max(0.0, (exited - entered).total_seconds() / 86400)
                stage_durations.setdefault(stage, []).append(days)
        for stage, durations in stage_durations.items():
            avg_times[stage] = sum(durations) / len(durations)

    result: dict[str, dict] = {}
    for i, stage in enumerate(_FUNNEL_STAGES):
        past_count = (
            sum(counts.get(s, 0) for s in _FUNNEL_STAGES[i + 1 :])
            + counts.get("won", 0)
        )
        at_or_past = counts.get(stage, 0) + past_count
        rate = past_count / at_or_past if at_or_past > 0 else 0.0
        result[stage] = {
            "conversion_rate": round(rate, 4),
            "avg_time_in_stage_days": avg_times.get(stage),
        }
    return result


def rep_leaderboard(
    deals: list[dict],
    scope: int | None = None,
) -> list[dict]:
    """Per-rep closed-won revenue, deal count, and average cycle time.

    scope=None  → aggregate across all reps (admin / manager view).
    scope=rep_id → restrict to that rep's own deals only.  This function
                   enforces the restriction; callers must not pre-filter.

    Cycle time = days from deal created_at to closed_at (won deals only;
    deals missing either timestamp are excluded from the cycle-time average).

    Result is sorted by revenue descending.
    """
    if scope is not None:
        deals = [d for d in deals if d.get("owner_id") == scope]

    revenue: dict[int, float] = {}
    deal_count: dict[int, int] = {}
    cycle_days: dict[int, list[float]] = {}

    for deal in deals:
        if deal.get("stage") != "won":
            continue
        owner_id = deal.get("owner_id")
        if owner_id is None:
            continue
        value = float(deal.get("value") or 0.0)
        revenue[owner_id] = revenue.get(owner_id, 0.0) + value
        deal_count[owner_id] = deal_count.get(owner_id, 0) + 1
        created = _parse_naive(deal.get("created_at"))
        closed = _parse_naive(deal.get("closed_at"))
        if created is not None and closed is not None:
            days = max(0.0, (closed - created).total_seconds() / 86400)
            cycle_days.setdefault(owner_id, []).append(days)

    rows = []
    for owner_id in revenue:
        cd_list = cycle_days.get(owner_id, [])
        rows.append(
            {
                "owner_id": owner_id,
                "revenue": revenue[owner_id],
                "deals_closed": deal_count[owner_id],
                "avg_cycle_days": sum(cd_list) / len(cd_list) if cd_list else None,
            }
        )
    rows.sort(key=lambda r: r["revenue"], reverse=True)
    return rows


def source_cohorts(
    deals: list[dict],
    contacts: list[dict],
) -> dict[str, dict]:
    """Deals grouped by contact acquisition source with avg value and win rate.

    Sources: referral / inbound / outbound / event / other.
    Contacts with a missing or unrecognised source are mapped to 'other'.
    Deals whose contact_id has no matching contact entry are also mapped to 'other'.

    Returns a dict keyed by source with:
    - deal_count
    - avg_deal_value
    - win_rate  (fraction of deals with stage == 'won')
    """
    contact_source: dict[int, str] = {
        c["id"]: (c.get("source") or "other")
        for c in contacts
        if c.get("id") is not None
    }

    totals: dict[str, int] = {}
    won_counts: dict[str, int] = {}
    values: dict[str, list[float]] = {}

    for deal in deals:
        cid = deal.get("contact_id")
        source = contact_source.get(cid, "other") if cid is not None else "other"
        totals[source] = totals.get(source, 0) + 1
        values.setdefault(source, []).append(float(deal.get("value") or 0.0))
        if deal.get("stage") == "won":
            won_counts[source] = won_counts.get(source, 0) + 1

    return {
        source: {
            "deal_count": total,
            "avg_deal_value": sum(values[source]) / total,
            "win_rate": won_counts.get(source, 0) / total,
        }
        for source, total in totals.items()
    }
