"""Tests dashboard/app.py's HTTP layer with its state object's underlying
loops monkeypatched out, so no real orchestrator/network call ever runs.
DASHBOARD_TOKEN must exist before dashboard.app is first imported, since
the module raises at import time if it's missing (see app.py's docstring).

Uses `with TestClient(app) as client` (not a bare TestClient(app)) so the
app's lifespan keeps ONE event loop alive across every request in a test —
without it, each request gets its own short-lived event loop, and a
background asyncio task (the exit monitor) created during one request is
gone by the time the next request checks on it.
"""

import os

os.environ["DASHBOARD_TOKEN"] = "test-token"

import pytest
from fastapi.testclient import TestClient

import dashboard.state as state_module
from dashboard.app import app, state

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _cleanup_trading():
    # Only the trading daemon: it's plain threading, safe to stop from any
    # context. The monitor is an asyncio task tied to the `client` fixture's
    # lifespan-managed event loop — each monitor test below stops it itself,
    # inside that same loop, rather than from a fresh asyncio.run() here
    # (which would own a different, soon-closed loop and fail to await it).
    yield
    state.stop_trading()


def test_status_requires_a_token(client):
    res = client.get("/api/status")
    assert res.status_code == 401


def test_status_rejects_a_wrong_token(client):
    res = client.get("/api/status", headers={"Authorization": "Bearer wrong"})
    assert res.status_code == 401


def test_status_returns_trading_and_monitor_state_with_the_right_token(client):
    res = client.get("/api/status", headers=AUTH)

    assert res.status_code == 200
    body = res.json()
    assert body["trading"]["running"] is False
    assert body["monitor"]["running"] is False


def test_index_page_is_served_without_a_token(client):
    res = client.get("/")

    assert res.status_code == 200
    assert "Crypto Trading Dashboard" in res.text


def test_start_trading_requires_at_least_one_symbol(client):
    res = client.post("/api/trading/start", headers=AUTH, json={"symbols": [], "interval_minutes": 15})

    assert res.status_code == 400


def test_start_trading_starts_the_daemon_and_stop_stops_it(client, monkeypatch):
    calls = []

    def fake_loop_forever(symbols, interval_minutes, account_equity, stop_event):
        calls.append(symbols)
        stop_event.wait(timeout=5)

    monkeypatch.setattr(state_module.crypto_daemon, "loop_forever", fake_loop_forever)

    res = client.post("/api/trading/start", headers=AUTH, json={"symbols": ["btc", "eth"], "interval_minutes": 5})
    assert res.status_code == 200

    status = client.get("/api/status", headers=AUTH).json()
    assert status["trading"]["running"] is True
    assert status["trading"]["symbols"] == ["BTC", "ETH"]

    res = client.post("/api/trading/stop", headers=AUTH, json={})
    assert res.status_code == 200
    assert client.get("/api/status", headers=AUTH).json()["trading"]["running"] is False
    assert calls == [["BTC", "ETH"]]


def test_starting_trading_twice_returns_409(client, monkeypatch):
    def fake_loop_forever(symbols, interval_minutes, account_equity, stop_event):
        stop_event.wait(timeout=5)

    monkeypatch.setattr(state_module.crypto_daemon, "loop_forever", fake_loop_forever)

    client.post("/api/trading/start", headers=AUTH, json={"symbols": ["BTC"]})

    res = client.post("/api/trading/start", headers=AUTH, json={"symbols": ["ETH"]})
    assert res.status_code == 409


def test_start_and_stop_monitor(client, monkeypatch):
    async def fake_loop_forever(stop_event):
        await stop_event.wait()

    monkeypatch.setattr(state_module.exit_monitor, "loop_forever", fake_loop_forever)

    res = client.post("/api/monitor/start", headers=AUTH, json={})
    assert res.status_code == 200
    assert client.get("/api/status", headers=AUTH).json()["monitor"]["running"] is True

    res = client.post("/api/monitor/stop", headers=AUTH, json={})
    assert res.status_code == 200
    assert client.get("/api/status", headers=AUTH).json()["monitor"]["running"] is False


def test_starting_monitor_twice_returns_409(client, monkeypatch):
    async def fake_loop_forever(stop_event):
        await stop_event.wait()

    monkeypatch.setattr(state_module.exit_monitor, "loop_forever", fake_loop_forever)

    client.post("/api/monitor/start", headers=AUTH, json={})

    res = client.post("/api/monitor/start", headers=AUTH, json={})
    assert res.status_code == 409

    client.post("/api/monitor/stop", headers=AUTH, json={})


def test_get_account_requires_a_token(client):
    res = client.get("/api/account")
    assert res.status_code == 401


def test_get_account_returns_the_state_snapshot(client, monkeypatch):
    monkeypatch.setattr(state, "account_snapshot", lambda: {"balance": 999.0, "positions": []})

    res = client.get("/api/account", headers=AUTH)

    assert res.status_code == 200
    assert res.json() == {"balance": 999.0, "positions": []}


def test_auto_start_trading_and_monitor_from_env_vars(monkeypatch):
    """A fresh `with TestClient(app)` re-runs the app's lifespan, so this
    exercises AUTO_START_TRADING/AUTO_START_MONITOR independently of the
    shared `client` fixture (which entered the lifespan once already,
    before these env vars existed)."""
    monkeypatch.setenv("AUTO_START_TRADING", "true")
    monkeypatch.setenv("DASHBOARD_SYMBOLS", "btc,eth")
    monkeypatch.setenv("AUTO_START_MONITOR", "true")

    def fake_trading_loop(symbols, interval_minutes, account_equity, stop_event):
        stop_event.wait(timeout=5)

    async def fake_monitor_loop(stop_event):
        await stop_event.wait()

    monkeypatch.setattr(state_module.crypto_daemon, "loop_forever", fake_trading_loop)
    monkeypatch.setattr(state_module.exit_monitor, "loop_forever", fake_monitor_loop)

    with TestClient(app) as fresh_client:
        status = fresh_client.get("/api/status", headers=AUTH).json()
        assert status["trading"]["running"] is True
        assert status["trading"]["symbols"] == ["BTC", "ETH"]
        assert status["monitor"]["running"] is True

        fresh_client.post("/api/trading/stop", headers=AUTH, json={})
        fresh_client.post("/api/monitor/stop", headers=AUTH, json={})
