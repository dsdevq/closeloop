import pytest

from app.core.forecast import stage_forecast, weighted_forecast


def _deal(stage: str, value: float, probability: float) -> dict:
    return {"stage": stage, "value": value, "probability": probability}


def test_weighted_forecast_empty_returns_zero():
    assert weighted_forecast([]) == 0.0


def test_weighted_forecast_excludes_terminal_won():
    deals = [
        _deal("lead", 1000.0, 0.1),
        _deal("won", 5000.0, 1.0),
    ]
    result = weighted_forecast(deals)
    assert result == pytest.approx(100.0)  # 1000*0.1 only


def test_weighted_forecast_excludes_terminal_lost():
    deals = [
        _deal("qualified", 2000.0, 0.25),
        _deal("lost", 3000.0, 0.0),
    ]
    result = weighted_forecast(deals)
    assert result == pytest.approx(500.0)  # 2000*0.25 only


def test_weighted_forecast_mix_of_stages():
    deals = [
        _deal("lead", 1000.0, 0.1),
        _deal("qualified", 2000.0, 0.25),
        _deal("proposal", 4000.0, 0.5),
        _deal("negotiation", 8000.0, 0.75),
        _deal("won", 10000.0, 1.0),
        _deal("lost", 5000.0, 0.0),
    ]
    result = weighted_forecast(deals)
    # 1000*0.1 + 2000*0.25 + 4000*0.5 + 8000*0.75 = 100 + 500 + 2000 + 6000 = 8600
    assert result == pytest.approx(8600.0)


def test_stage_forecast_empty_returns_empty_dict():
    assert stage_forecast([]) == {}


def test_stage_forecast_excludes_terminal():
    deals = [
        _deal("lead", 1000.0, 0.1),
        _deal("won", 5000.0, 1.0),
        _deal("lost", 3000.0, 0.0),
    ]
    result = stage_forecast(deals)
    assert "won" not in result
    assert "lost" not in result
    assert result["lead"] == pytest.approx(100.0)


def test_stage_forecast_groups_by_stage():
    deals = [
        _deal("lead", 1000.0, 0.1),
        _deal("lead", 500.0, 0.1),
        _deal("qualified", 2000.0, 0.25),
        _deal("qualified", 4000.0, 0.25),
    ]
    result = stage_forecast(deals)
    assert result["lead"] == pytest.approx(150.0)      # (1000+500)*0.1
    assert result["qualified"] == pytest.approx(1500.0)  # (2000+4000)*0.25


def test_stage_forecast_only_open_stages():
    deals = [
        _deal("proposal", 4000.0, 0.5),
        _deal("negotiation", 8000.0, 0.75),
    ]
    result = stage_forecast(deals)
    assert set(result.keys()) == {"proposal", "negotiation"}
    assert result["proposal"] == pytest.approx(2000.0)
    assert result["negotiation"] == pytest.approx(6000.0)
