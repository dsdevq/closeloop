import pytest

from app.core.forecast import _SCENARIO_BEST, _SCENARIO_EXPECTED, _SCENARIO_WORST, forecast_scenarios


@pytest.fixture
def contact(client):
    res = client.post("/contacts", json={"name": "Forecast User"})
    assert res.status_code == 201
    return res.json()


def test_forecast_empty_pipeline():
    pass  # handled implicitly — no deals means total=0.0


def test_forecast_returns_total_and_by_stage(client, contact):
    client.post("/deals", json={"title": "D1", "contact_id": contact["id"], "value": 1000.0})

    res = client.get("/forecast")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "by_stage" in data


def test_forecast_correct_weighted_total(client, contact):
    # Both deals start at "lead" with probability 0.1
    client.post("/deals", json={"title": "D1", "contact_id": contact["id"], "value": 1000.0})
    client.post("/deals", json={"title": "D2", "contact_id": contact["id"], "value": 2000.0})

    res = client.get("/forecast")
    data = res.json()
    # (1000 + 2000) * 0.1 = 300
    assert data["total"] == pytest.approx(300.0)
    assert data["by_stage"]["lead"] == pytest.approx(300.0)


def test_forecast_excludes_won_deals(client, contact):
    r1 = client.post("/deals", json={"title": "Open", "contact_id": contact["id"], "value": 1000.0})
    r2 = client.post("/deals", json={"title": "Won", "contact_id": contact["id"], "value": 5000.0})

    client.patch(f"/deals/{r2.json()['id']}/stage", json={"stage": "won"})

    res = client.get("/forecast")
    data = res.json()
    # Only the open lead deal: 1000 * 0.1 = 100
    assert data["total"] == pytest.approx(100.0)
    assert "won" not in data["by_stage"]


def test_forecast_excludes_lost_deals(client, contact):
    r1 = client.post("/deals", json={"title": "Open", "contact_id": contact["id"], "value": 2000.0})
    r2 = client.post("/deals", json={"title": "Lost", "contact_id": contact["id"], "value": 8000.0})

    client.patch(f"/deals/{r2.json()['id']}/stage", json={"stage": "lost"})

    res = client.get("/forecast")
    data = res.json()
    # Only the open lead deal: 2000 * 0.1 = 200
    assert data["total"] == pytest.approx(200.0)
    assert "lost" not in data["by_stage"]


def test_forecast_by_stage_breakdown(client, contact):
    r1 = client.post("/deals", json={"title": "L1", "contact_id": contact["id"], "value": 1000.0})
    r2 = client.post("/deals", json={"title": "Q1", "contact_id": contact["id"], "value": 2000.0})

    # Move Q1 to qualified
    client.patch(f"/deals/{r2.json()['id']}/stage", json={"stage": "qualified"})

    res = client.get("/forecast")
    data = res.json()
    # lead: 1000 * 0.1 = 100; qualified: 2000 * 0.25 = 500
    assert data["by_stage"]["lead"] == pytest.approx(100.0)
    assert data["by_stage"]["qualified"] == pytest.approx(500.0)
    assert data["total"] == pytest.approx(600.0)


def test_forecast_zero_value_deals_included_but_contribute_nothing(client, contact):
    client.post("/deals", json={"title": "Zero", "contact_id": contact["id"], "value": 0.0})

    res = client.get("/forecast")
    data = res.json()
    assert data["total"] == pytest.approx(0.0)


# ── Scenario tests (core) ───────────────────────────────────────────────────

def test_forecast_scenarios_returns_three_keys():
    deals = [{"stage": "lead", "value": 1000.0}]
    result = forecast_scenarios(deals)
    assert set(result.keys()) == {"best", "expected", "worst"}


def test_forecast_scenarios_best_gt_expected_gt_worst():
    deals = [{"stage": "lead", "value": 1000.0}, {"stage": "proposal", "value": 2000.0}]
    result = forecast_scenarios(deals)
    assert result["best"] > result["expected"] > result["worst"]


def test_forecast_scenarios_excludes_terminal():
    deals = [
        {"stage": "lead", "value": 1000.0},
        {"stage": "won", "value": 5000.0},
        {"stage": "lost", "value": 3000.0},
    ]
    result = forecast_scenarios(deals)
    # Won/lost excluded; only lead contributes
    assert result["best"] == pytest.approx(1000.0 * _SCENARIO_BEST["lead"])
    assert result["expected"] == pytest.approx(1000.0 * _SCENARIO_EXPECTED["lead"])
    assert result["worst"] == pytest.approx(1000.0 * _SCENARIO_WORST["lead"])


def test_forecast_scenarios_custom_map_included():
    deals = [{"stage": "lead", "value": 1000.0}]
    custom = {"lead": 0.42}
    result = forecast_scenarios(deals, custom_map=custom)
    assert "custom" in result
    assert result["custom"] == pytest.approx(420.0)


def test_forecast_scenarios_no_custom_map_excludes_key():
    deals = [{"stage": "lead", "value": 1000.0}]
    result = forecast_scenarios(deals, custom_map=None)
    assert "custom" not in result


def test_forecast_scenarios_empty_pipeline_all_zero():
    result = forecast_scenarios([])
    assert result["best"] == 0.0
    assert result["expected"] == 0.0
    assert result["worst"] == 0.0


# ── Scenario API tests ──────────────────────────────────────────────────────

def test_scenarios_api_empty_pipeline(client):
    res = client.post("/forecast/scenarios", json={})
    assert res.status_code == 200
    data = res.json()
    assert set(data.keys()) == {"best", "expected", "worst"}
    assert data["best"] == 0.0
    assert data["expected"] == 0.0
    assert data["worst"] == 0.0


def test_scenarios_api_with_deals(client, contact):
    client.post("/deals", json={"title": "D1", "contact_id": contact["id"], "value": 1000.0})

    res = client.post("/forecast/scenarios", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["best"] > data["expected"] > data["worst"]
    assert data["best"] == pytest.approx(1000.0 * _SCENARIO_BEST["lead"])


def test_scenarios_api_custom_probability_overrides(client, contact):
    client.post("/deals", json={"title": "D1", "contact_id": contact["id"], "value": 1000.0})

    custom_map = {"lead": 0.50}
    res = client.post("/forecast/scenarios", json={"probability_overrides": custom_map})
    assert res.status_code == 200
    data = res.json()
    assert "custom" in data
    assert data["custom"] == pytest.approx(500.0)


def test_scenarios_api_excludes_terminal_deals(client, contact):
    d1 = client.post("/deals", json={"title": "Open", "contact_id": contact["id"], "value": 1000.0}).json()
    d2 = client.post("/deals", json={"title": "Won", "contact_id": contact["id"], "value": 9000.0}).json()
    # move d2 to won
    for s in ["qualified", "proposal", "negotiation", "won"]:
        client.patch(f"/deals/{d2['id']}/stage", json={"stage": s})

    res = client.post("/forecast/scenarios", json={})
    data = res.json()
    # Only open lead deal (1000) should contribute
    assert data["best"] == pytest.approx(1000.0 * _SCENARIO_BEST["lead"])
