import socket

from starlette.testclient import TestClient

from app.main import app


def test_no_outbound_network(monkeypatch):
    def _blocked(*args, **kwargs):
        raise OSError("no outbound network allowed")

    monkeypatch.setattr(socket, "create_connection", _blocked)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
