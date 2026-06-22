_TERMINAL = {"won", "lost"}

# Built-in scenario probability maps (stage → probability)
_SCENARIO_BEST: dict[str, float] = {
    "lead": 0.25,
    "qualified": 0.50,
    "proposal": 0.75,
    "negotiation": 0.90,
}
_SCENARIO_EXPECTED: dict[str, float] = {
    "lead": 0.10,
    "qualified": 0.25,
    "proposal": 0.50,
    "negotiation": 0.75,
}
_SCENARIO_WORST: dict[str, float] = {
    "lead": 0.02,
    "qualified": 0.10,
    "proposal": 0.25,
    "negotiation": 0.50,
}


def weighted_forecast(deals: list[dict]) -> float:
    """Sum of value * probability for all non-terminal deals."""
    return sum(
        d["value"] * d["probability"]
        for d in deals
        if d.get("stage") not in _TERMINAL
    )


def weighted_forecast_with_overrides(deals: list[dict], probability_map: dict[str, float]) -> float:
    """Weighted forecast using a custom per-stage probability map instead of stored probabilities."""
    return sum(
        d["value"] * probability_map.get(d.get("stage", ""), 0.0)
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


def forecast_scenarios(deals: list[dict], custom_map: dict[str, float] | None = None) -> dict:
    """
    Returns best/expected/worst pipeline forecasts using built-in probability maps.
    Optionally includes a custom scenario when custom_map is provided.
    """
    result: dict = {
        "best": weighted_forecast_with_overrides(deals, _SCENARIO_BEST),
        "expected": weighted_forecast_with_overrides(deals, _SCENARIO_EXPECTED),
        "worst": weighted_forecast_with_overrides(deals, _SCENARIO_WORST),
    }
    if custom_map is not None:
        result["custom"] = weighted_forecast_with_overrides(deals, custom_map)
    return result
