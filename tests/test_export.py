"""Tests verifying that CSV export endpoints return correct header rows."""

from app.interchange.config import REGISTRY


def test_contacts_csv_headers(client):
    response = client.get("/contacts/export?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    header_line = response.content.decode().splitlines()[0]
    assert header_line == ",".join(REGISTRY["contacts"].columns)


def test_deals_csv_headers(client):
    response = client.get("/deals/export?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    header_line = response.content.decode().splitlines()[0]
    assert header_line == ",".join(REGISTRY["deals"].columns)


def test_activities_csv_headers(client):
    response = client.get("/activities/export?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    header_line = response.content.decode().splitlines()[0]
    assert header_line == ",".join(REGISTRY["activities"].columns)
