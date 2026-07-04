"""Automation rule core types and scheduling logic — pure, no I/O (ADR-0001).

Two trigger families (see .devclaw/research/workflow-automation.md §2):

  after_save  — fires synchronously when a matching entity mutation is saved.
                Borrowed from Salesforce Record-Triggered Flow / HubSpot
                Property-Based Enrollment / Pipedrive "Deal Updated" trigger.

  scheduled   — fires on a time-based cadence.  Two schedule modes:
                  interval    — every N days since last_fired_at.
                  field_offset — N days before/after a date field on the entity.
                Borrowed from Salesforce Scheduled Actions, HubSpot Delay Steps,
                Zoho Time-Based Actions.

`is_rule_due()` is the testable seam the scheduler-wiring PR will call into: a
pure function with no DB access that answers "should this scheduled rule fire
now?" given a ScheduleConfig, a reference time, and optional context values.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

# ---------------------------------------------------------------------------
# Trigger-type constants
# ---------------------------------------------------------------------------

TRIGGER_AFTER_SAVE = "after_save"
TRIGGER_SCHEDULED = "scheduled"

VALID_TRIGGER_TYPES: frozenset[str] = frozenset({TRIGGER_AFTER_SAVE, TRIGGER_SCHEDULED})

# ---------------------------------------------------------------------------
# Schedule-mode constants
# ---------------------------------------------------------------------------

SCHEDULE_MODE_INTERVAL = "interval"
SCHEDULE_MODE_FIELD_OFFSET = "field_offset"

VALID_SCHEDULE_MODES: frozenset[str] = frozenset(
    {SCHEDULE_MODE_INTERVAL, SCHEDULE_MODE_FIELD_OFFSET}
)

# ---------------------------------------------------------------------------
# ScheduleConfig — payload for trigger_type='scheduled' rules
# ---------------------------------------------------------------------------


@dataclass
class ScheduleConfig:
    """Scheduling config stored in AutomationRule.schedule_config_json.

    Two modes:

    interval:
      Fires every `interval_days` days.  The interval fence is `last_fired_at`
      (or rule creation time when the rule has never fired).

    field_offset:
      Fires `offset_days` days after the entity's `anchor_field` date.
      `offset_days` is a signed integer — negative values mean "before" the
      anchor date (e.g., offset_days=-3 with anchor_field="expected_close_date"
      fires 3 days before the expected close date).  Borrowed from Zoho
      Time-Based Actions which allow negative offsets.

    Exactly one mode is active per config; the unused fields are None.
    """

    mode: Literal["interval", "field_offset"]
    interval_days: int | None = None
    anchor_field: str | None = None
    offset_days: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in VALID_SCHEDULE_MODES:
            raise ValueError(f"unknown schedule mode: {self.mode!r}")
        if self.mode == SCHEDULE_MODE_INTERVAL:
            if self.interval_days is None or self.interval_days < 1:
                raise ValueError("interval mode requires interval_days >= 1")
        else:  # field_offset
            if not self.anchor_field:
                raise ValueError("field_offset mode requires a non-empty anchor_field")
            if self.offset_days is None:
                raise ValueError("field_offset mode requires offset_days")


# ---------------------------------------------------------------------------
# Serialisation / deserialisation
# schedule_config_json is stored in AutomationRule.schedule_config_json.
# ---------------------------------------------------------------------------


def schedule_config_to_json(cfg: ScheduleConfig) -> str:
    """Serialise a ScheduleConfig to JSON for storage in schedule_config_json."""
    return json.dumps(asdict(cfg))


def schedule_config_from_json(raw: str) -> ScheduleConfig:
    """Deserialise schedule_config_json back to a ScheduleConfig.

    Raises ValueError for malformed JSON or unknown/invalid mode.
    """
    try:
        d: dict = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"invalid schedule config JSON: {exc}") from exc
    try:
        return ScheduleConfig(**d)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"malformed schedule config: {exc}") from exc


# ---------------------------------------------------------------------------
# is_rule_due — the scheduler-wiring seam (pure, no I/O)
# ---------------------------------------------------------------------------


def is_rule_due(
    cfg: ScheduleConfig,
    reference_time: datetime,
    *,
    last_fired_at: datetime | None = None,
    anchor_field_value: datetime | None = None,
) -> bool:
    """Return True iff a scheduled rule should fire at *reference_time*.

    interval mode:
      - Never fired (last_fired_at is None) → due immediately.
      - Otherwise due when reference_time >= last_fired_at + interval_days days.

    field_offset mode:
      - anchor_field_value must be provided; raises ValueError if absent.
      - Due when reference_time >= anchor_field_value + offset_days days.
        offset_days may be negative (fire before the anchor date).

    The caller (scheduler-wiring PR) is responsible for:
      - Supplying the injected clock's .now() as reference_time (ADR-0006).
      - Resolving anchor_field_value from the entity row for field_offset rules.
      - Updating last_fired_at on the rule after a successful fire.
    """
    if cfg.mode == SCHEDULE_MODE_INTERVAL:
        if last_fired_at is None:
            return True
        if cfg.interval_days is None:
            raise ValueError("interval ScheduleConfig missing interval_days")
        return reference_time >= last_fired_at + timedelta(days=cfg.interval_days)

    if cfg.mode == SCHEDULE_MODE_FIELD_OFFSET:
        if anchor_field_value is None:
            raise ValueError(
                "field_offset is_rule_due() requires anchor_field_value"
            )
        if cfg.offset_days is None:
            raise ValueError("field_offset ScheduleConfig missing offset_days")
        return reference_time >= anchor_field_value + timedelta(days=cfg.offset_days)

    raise ValueError(f"unknown schedule mode: {cfg.mode!r}")
