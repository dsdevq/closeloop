from app.core.stages import DEFAULT_PROBABILITY

_TERMINAL = {"won", "lost"}

# Scenario probability maps (non-terminal stages only; won/lost inherit 1.0/0.0)
_BEST_PROBABILITY: dict[str, float] = {
    "lead": 0.20,
    "qualified": 0.40,
    "proposal": 0.70,
    "negotiation": 0.90,
    "won": 1.0,
    "lost": 0.0,
}

_WORST_PROBABILITY: dict[str, float] = {
    "lead": 0.05,
    "qualified": 0.15,
    "proposal": 0.30,
    "negotiation": 0.60,
    "won": 1.0,
    "lost": 0.0,
}


def weighted_forecast(deals: list[dict]) -> float:
    """Sum of value * probability for all non-terminal deals."""
    return sum(
        d["value"] * d["probability"]
        for d in deals
        if d.get("stage") not in _TERMINAL
    )


def stage_forecast(deals: list[dict]) -> dict[str, float]:
    """Same breakdown as weighted_forecast, keyed by stage."""
    result: dict[str, float] = {}
    for d in deals:
        if d.get("stage") in _TERMINAL:
            continue
        stage = d["stage"]
        result[stage] = result.get(stage, 0.0) + d["value"] * d["probability"]
    return result


def _scenario_total(deals: list[dict], prob_map: dict[str, float]) -> float:
    """Sum value * scenario_probability for all non-terminal deals."""
    return sum(
        d["value"] * prob_map.get(d.get("stage", ""), 0.0)
        for d in deals
        if d.get("stage") not in _TERMINAL
    )


def forecast_scenarios(
    deals: list[dict],
    probability_overrides: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Return {best, expected, worst} scenario forecasts.

    ``probability_overrides`` replaces probabilities in the expected-case map
    only (per-stage). Keys must be valid stage names; unknown keys are ignored.
    """
    expected_map = dict(DEFAULT_PROBABILITY)
    if probability_overrides:
        for stage, prob in probability_overrides.items():
            if stage in expected_map:
                expected_map[stage] = prob

    return {
        "best": round(_scenario_total(deals, _BEST_PROBABILITY), 4),
        "expected": round(_scenario_total(deals, expected_map), 4),
        "worst": round(_scenario_total(deals, _WORST_PROBABILITY), 4),
    }
