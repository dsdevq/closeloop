import pytest

from app.core.stages import (
    DEFAULT_PROBABILITY,
    STAGES,
    stage_probability,
    validate_transition,
)

# Forward transitions among open stages only: won/lost are terminal so won→lost is invalid.
_OPEN = ["lead", "qualified", "proposal", "negotiation"]
FORWARD_PAIRS = list(zip(_OPEN, _OPEN[1:] + ["won"]))  # …→qualified, …→won


@pytest.mark.parametrize("from_s,to_s", FORWARD_PAIRS)
def test_forward_transitions_valid(from_s, to_s):
    assert validate_transition(from_s, to_s) is True


@pytest.mark.parametrize("from_s", ["lead", "qualified", "proposal", "negotiation"])
def test_any_open_stage_can_move_to_won(from_s):
    assert validate_transition(from_s, "won") is True


@pytest.mark.parametrize("from_s", ["lead", "qualified", "proposal", "negotiation"])
def test_any_open_stage_can_move_to_lost(from_s):
    assert validate_transition(from_s, "lost") is True


@pytest.mark.parametrize("to_s", STAGES)
def test_won_is_terminal(to_s):
    assert validate_transition("won", to_s) is False


@pytest.mark.parametrize("to_s", STAGES)
def test_lost_is_terminal(to_s):
    assert validate_transition("lost", to_s) is False


@pytest.mark.parametrize("to_s", STAGES)
def test_none_from_stage_always_valid(to_s):
    assert validate_transition(None, to_s) is True


def test_backward_move_from_open_stage_allowed():
    assert validate_transition("negotiation", "lead") is True
    assert validate_transition("proposal", "qualified") is True


def test_stage_probability_correct():
    assert stage_probability("lead") == pytest.approx(0.1)
    assert stage_probability("qualified") == pytest.approx(0.25)
    assert stage_probability("proposal") == pytest.approx(0.5)
    assert stage_probability("negotiation") == pytest.approx(0.75)
    assert stage_probability("won") == pytest.approx(1.0)
    assert stage_probability("lost") == pytest.approx(0.0)


def test_stage_probability_covers_all_stages():
    for stage in STAGES:
        assert stage in DEFAULT_PROBABILITY
        assert stage_probability(stage) == DEFAULT_PROBABILITY[stage]


def test_invalid_to_stage_raises():
    with pytest.raises(ValueError, match="Unknown stage"):
        validate_transition("lead", "bogus")


def test_invalid_from_stage_raises():
    with pytest.raises(ValueError, match="Unknown stage"):
        validate_transition("bogus", "lead")


def test_stage_probability_invalid_raises():
    with pytest.raises(ValueError, match="Unknown stage"):
        stage_probability("nope")
