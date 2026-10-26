import asyncio
import time

import pytest

import dashboard.state as state_module
from dashboard.state import DashboardState


def test_trading_status_reports_stopped_before_anything_starts():
    state = DashboardState()

    status = state.trading_status()

    assert status.running is False
    assert status.symbols == []


def test_start_trading_runs_loop_forever_in_a_background_thread_and_stop_joins_it(monkeypatch):
    calls = []

    def fake_loop_forever(symbols, interval_minutes, account_equity, stop_event):
        calls.append((symbols, interval_minutes, account_equity))
        stop_event.wait(timeout=5)  # blocks until stop_trading() sets it

    monkeypatch.setattr(state_module.crypto_daemon, "loop_forever", fake_loop_forever)

    state = DashboardState()
    state.start_trading(["BTC"], 15.0, account_equity=1000.0)
    time.sleep(0.1)

    status = state.trading_status()
    assert status.running is True
    assert status.symbols == ["BTC"]
    assert status.interval_minutes == 15.0

    state.stop_trading()

    assert state.trading_status().running is False
    assert calls == [(["BTC"], 15.0, 1000.0)]


def test_start_trading_twice_without_stopping_raises(monkeypatch):
    def fake_loop_forever(symbols, interval_minutes, account_equity, stop_event):
        stop_event.wait(timeout=5)

    monkeypatch.setattr(state_module.crypto_daemon, "loop_forever", fake_loop_forever)

    state = DashboardState()
    state.start_trading(["BTC"], 15.0)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            state.start_trading(["ETH"], 15.0)
    finally:
        state.stop_trading()


def test_start_monitor_runs_loop_forever_as_an_asyncio_task(monkeypatch):
    calls = []

    async def fake_loop_forever(stop_event):
        calls.append("started")
        await stop_event.wait()
        calls.append("stopped")

    monkeypatch.setattr(state_module.exit_monitor, "loop_forever", fake_loop_forever)

    async def scenario():
        state = DashboardState()
        assert state.monitor_status().running is False

        state.start_monitor()
        await asyncio.sleep(0.05)
        assert state.monitor_status().running is True

        await state.stop_monitor()
        assert state.monitor_status().running is False

    asyncio.run(scenario())
    assert calls == ["started", "stopped"]


def test_start_monitor_twice_without_stopping_raises(monkeypatch):
    async def fake_loop_forever(stop_event):
        await stop_event.wait()

    monkeypatch.setattr(state_module.exit_monitor, "loop_forever", fake_loop_forever)

    async def scenario():
        state = DashboardState()
        state.start_monitor()
        with pytest.raises(RuntimeError, match="already running"):
            state.start_monitor()
        await state.stop_monitor()

    asyncio.run(scenario())
