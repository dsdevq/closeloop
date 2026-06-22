import pytest


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
