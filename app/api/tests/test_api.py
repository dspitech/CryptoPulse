import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.update({"API_KEY": "test-key-0123456789abcdef", "API_METRICS_PORT": "0", "POSTGRES_PASSWORD": "x"})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

KEY = {"X-API-Key": os.environ["API_KEY"]}


@pytest.fixture()
def client(monkeypatch):
    calls = []

    def fake_query(sql, params=()):
        calls.append((sql, params))
        return [{"coin_id": "bitcoin", "price_usd": 1.5}]

    monkeypatch.setattr(main, "query", fake_query)
    with TestClient(main.app) as c:
        c.calls = calls
        yield c


def test_health_needs_no_key(client):
    assert client.get("/health").json()["status"] == "ok"


def test_missing_or_wrong_key_is_rejected(client):
    assert client.get("/v1/coins").status_code == 401
    assert client.get("/v1/coins", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.calls == []


def test_valid_key_returns_data(client):
    response = client.get("/v1/coins", headers=KEY)
    assert response.status_code == 200
    assert response.json()[0]["coin_id"] == "bitcoin"


def test_invalid_coin_id_is_rejected_before_query(client):
    assert client.get("/v1/indicators/BTC;DROP", headers=KEY).status_code == 422
    assert client.get("/v1/indicators/..%2f", headers=KEY).status_code in (404, 422)
    assert client.calls == []


def test_queries_are_parameterized(client):
    client.get("/v1/prices/bitcoin/daily?limit=5&start=2026-01-01", headers=KEY)
    sql, params = client.calls[-1]
    assert "bitcoin" in params and 5 in params
    assert "bitcoin" not in sql


def test_limit_bounds(client):
    assert client.get("/v1/indicators/bitcoin?limit=0", headers=KEY).status_code == 422
    assert client.get("/v1/indicators/bitcoin?limit=1001", headers=KEY).status_code == 422


def test_latest_price_unknown_coin_is_404(client, monkeypatch):
    monkeypatch.setattr(main, "query", lambda sql, params=(): [])
    assert client.get("/v1/prices/unknown/latest", headers=KEY).status_code == 404


def test_server_refuses_to_start_without_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "short")
    with pytest.raises(RuntimeError), TestClient(main.app):
        pass


def test_decimals_are_returned_as_json_numbers(monkeypatch):
    from decimal import Decimal

    assert main.normalize({"price": Decimal("60000.5"), "name": "x", "n": 3, "none": None}) == {
        "price": 60000.5, "name": "x", "n": 3, "none": None}
    row = main.normalize({"price": Decimal("1.25")})
    with TestClient(main.app) as c:
        monkeypatch.setattr(main, "query", lambda sql, params=(): [row])
        assert c.get("/v1/prices/latest", headers=KEY).json() == [{"price": 1.25}]
