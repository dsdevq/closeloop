"""
Deal-velocity and stage-aging calculations.

All inputs are plain dicts; no SQLAlchemy models imported here.
"""

from __future__ import annotations

from datetime import datetime

# SLA thresholds in days per non-terminal stage.
STAGE_SLA_DAYS: dict[str, int] = {
    "lead": 30,
    "qualified": 21,
    "proposal": 14,
    "negotiation": 7,
}


def _parse_naive(ts: str) -> datetime:
    """Parse ISO-8601 string to a naive UTC datetime."""
    dt = datetime.fromisoformat(ts)
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def stage_ages(transitions: list[dict], now: datetime) -> dict:
    """
    Compute stage-age metadata for a single deal.

    Parameters
    ----------
    transitions:
        List of dicts with keys ``from_stage``, ``to_stage``, ``occurred_at``
        (ISO-8601 string).  Ordered ascending is assumed but we sort anyway.
    now:
        Current wall-clock time (naive UTC).

    Returns
    -------
    dict with:
        current_stage, days_in_current_stage, total_cycle_days,
        stage_history: list[{stage, days}]
    """
    if not transitions:
        return {
            "current_stage": None,
            "days_in_current_stage": 0.0,
            "total_cycle_days": 0.0,
            "stage_history": [],
        }

    now_naive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    sorted_transitions = sorted(transitions, key=lambda t: t["occurred_at"])

    # Build list of (stage, entered_at) pairs
    entries: list[tuple[str, datetime]] = []
    for tr in sorted_transitions:
        entries.append((tr["to_stage"], _parse_naive(tr["occurred_at"])))

    # Compute per-stage durations
    stage_history: list[dict] = []
    for i, (stage, entered_at) in enumerate(entries):
        end = entries[i + 1][1] if i + 1 < len(entries) else now_naive
        days = max((end - entered_at).total_seconds() / 86400.0, 0.0)
        # Merge consecutive identical stages (shouldn't happen, but be safe)
        if stage_history and stage_history[-1]["stage"] == stage:
            stage_history[-1]["days"] += days
        else:
            stage_history.append({"stage": stage, "days": round(days, 4)})

    current_stage = entries[-1][0]
    days_in_current_stage = stage_history[-1]["days"] if stage_history else 0.0
    first_entry = entries[0][1]
    total_cycle_days = (now_naive - first_entry).total_seconds() / 86400.0

    return {
        "current_stage": current_stage,
        "days_in_current_stage": round(days_in_current_stage, 4),
        "total_cycle_days": round(max(total_cycle_days, 0.0), 4),
        "stage_history": stage_history,
    }


def avg_days_per_stage(
    deals_transitions: list[list[dict]],
    now: datetime,
) -> dict[str, float]:
    """
    Average days per stage across a collection of deals.

    Only non-empty transition lists are counted per stage.

    Parameters
    ----------
    deals_transitions:
        Outer list = one element per deal; inner list = transitions for that deal.
    now:
        Current wall-clock time (naive UTC).

    Returns
    -------
    Mapping of stage name → average days spent in that stage.
    """
    stage_totals: dict[str, float] = {}
    stage_counts: dict[str, int] = {}

    for transitions in deals_transitions:
        if not transitions:
            continue
        info = stage_ages(transitions, now)
        for entry in info["stage_history"]:
            s = entry["stage"]
            stage_totals[s] = stage_totals.get(s, 0.0) + entry["days"]
            stage_counts[s] = stage_counts.get(s, 0) + 1

    return {
        stage: round(stage_totals[stage] / stage_counts[stage], 4)
        for stage in stage_totals
    }


def is_rotting(
    stage: str,
    days_in_stage: float,
    sla_days: dict[str, int] | None = None,
) -> bool:
    """
    Return True if the deal has exceeded its stage SLA.

    Won/lost deals are never considered rotting (no SLA defined for them).
    """
    thresholds = sla_days if sla_days is not None else STAGE_SLA_DAYS
    if stage not in thresholds:
        return False
    return days_in_stage > thresholds[stage]
