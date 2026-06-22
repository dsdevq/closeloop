"""Deal velocity and stage-aging analysis.

Pure functions only — no I/O, no DB access, injectable clock.
"""

from __future__ import annotations

from datetime import datetime

# Default SLA in days per open stage before a deal is considered "rotting"
_DEFAULT_STAGE_SLA_DAYS: dict[str, int] = {
    "lead": 7,
    "qualified": 14,
    "proposal": 21,
    "negotiation": 30,
}

_TERMINAL = {"won", "lost"}


def _parse_naive(ts: str) -> datetime:
    """Parse ISO-8601 string to a naive UTC datetime."""
    dt = datetime.fromisoformat(ts)
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def time_in_stage_hours(
    transitions: list[dict],
    current_stage: str,
    now: datetime,
) -> float | None:
    """
    Hours the deal has been in ``current_stage``.

    Finds the most recent transition whose ``to_stage`` matches and measures
    elapsed time to ``now``.  Returns ``None`` if no such transition exists.
    """
    relevant = [t for t in transitions if t.get("to_stage") == current_stage]
    if not relevant:
        return None
    latest = max(relevant, key=lambda t: t["occurred_at"])
    entered = _parse_naive(latest["occurred_at"])
    return max(0.0, (_naive(now) - entered).total_seconds() / 3600)


def cycle_time_hours(transitions: list[dict], now: datetime) -> float | None:
    """
    Total hours from the first recorded transition to ``now``.

    Returns ``None`` if there are no transitions.
    """
    if not transitions:
        return None
    earliest = min(_parse_naive(t["occurred_at"]) for t in transitions)
    return max(0.0, (_naive(now) - earliest).total_seconds() / 3600)


def avg_days_per_stage(all_deal_transitions: list[list[dict]]) -> dict[str, float]:
    """
    Average calendar days spent in each stage, computed across multiple deals.

    Each inner list is the full transition log for one deal.  Terminal stages
    (won/lost) are never measured as a duration because there is no next
    transition to mark their end.
    """
    stage_durations: dict[str, list[float]] = {}
    for transitions in all_deal_transitions:
        sorted_trans = sorted(transitions, key=lambda t: t["occurred_at"])
        for i, t in enumerate(sorted_trans):
            stage = t.get("to_stage", "")
            # Terminal stages have no exit; skip as a duration measurement.
            if stage in _TERMINAL or i + 1 >= len(sorted_trans):
                continue
            entered = _parse_naive(t["occurred_at"])
            exited = _parse_naive(sorted_trans[i + 1]["occurred_at"])
            days = max(0.0, (exited - entered).total_seconds() / 86400)
            stage_durations.setdefault(stage, []).append(days)
    return {
        stage: sum(durations) / len(durations)
        for stage, durations in stage_durations.items()
    }


def stage_sla_days() -> dict[str, int]:
    """Return a copy of the default stage SLA map (days per stage)."""
    return dict(_DEFAULT_STAGE_SLA_DAYS)


def is_deal_rotting(
    transitions: list[dict],
    current_stage: str,
    now: datetime,
    sla_days: dict[str, int] | None = None,
) -> bool:
    """
    Return True if the deal has been in ``current_stage`` longer than the SLA.

    Terminal stages are never considered rotting (they have no SLA).
    If no transition into ``current_stage`` exists, returns False.
    """
    if current_stage in _TERMINAL:
        return False
    sla = sla_days if sla_days is not None else _DEFAULT_STAGE_SLA_DAYS
    if current_stage not in sla:
        return False
    hours = time_in_stage_hours(transitions, current_stage, now)
    if hours is None:
        return False
    return hours > sla[current_stage] * 24
