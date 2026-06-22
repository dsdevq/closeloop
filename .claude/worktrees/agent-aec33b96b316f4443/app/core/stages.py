STAGES: list[str] = ["lead", "qualified", "proposal", "negotiation", "won", "lost"]

_TERMINAL = {"won", "lost"}

DEFAULT_PROBABILITY: dict[str, float] = {
    "lead": 0.1,
    "qualified": 0.25,
    "proposal": 0.5,
    "negotiation": 0.75,
    "won": 1.0,
    "lost": 0.0,
}


def validate_transition(from_stage: str | None, to_stage: str) -> bool:
    if to_stage not in DEFAULT_PROBABILITY:
        raise ValueError(f"Unknown stage: {to_stage!r}")
    if from_stage is not None and from_stage not in DEFAULT_PROBABILITY:
        raise ValueError(f"Unknown stage: {from_stage!r}")

    if from_stage is None:
        return True
    if from_stage in _TERMINAL:
        return False
    return True


def stage_probability(stage: str) -> float:
    if stage not in DEFAULT_PROBABILITY:
        raise ValueError(f"Unknown stage: {stage!r}")
    return DEFAULT_PROBABILITY[stage]
