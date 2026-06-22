_TERMINAL = {"won", "lost"}


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
