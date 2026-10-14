"""Unit tests for the exit-monitor's per-cycle decision logic (`_check_once`),
using a fake MCP session so there's no real subprocess involved. The shape of
fake responses mirrors what the real MCP transport actually sends: a
dict-returning tool arrives as one JSON text block, a list-returning tool
arrives as one block per item (verified against the real stdio transport
while building this)."""

import asyncio
import json
import types

from robinhood_mcp import monitor


class FakeSession:
    def __init__(self, positions, risk_levels, quotes):
        self.positions = positions
        self.risk_levels = risk_levels
        self.quotes = quotes
        self.calls = []

    async def call_tool(self, tool_name, arguments=None):
        arguments = arguments or {}
        self.calls.append((tool_name, arguments))

        if tool_name == "get_positions":
            payload = self.positions
        elif tool_name == "get_risk_levels":
            payload = self.risk_levels
        elif tool_name == "get_quote":
            payload = self.quotes[arguments["symbol"]]
        elif tool_name == "place_order":
            payload = {"order_id": "fake-order-1", "state": "filled"}
        else:
            raise AssertionError(f"unexpected tool call: {tool_name}")

        if isinstance(payload, list):
            blocks = [types.SimpleNamespace(type="text", text=json.dumps(item)) for item in payload]
        else:
            blocks = [types.SimpleNamespace(type="text", text=json.dumps(payload))]
        return types.SimpleNamespace(content=blocks)


def _run(coro):
    return asyncio.run(coro)


def test_no_positions_or_levels_does_nothing():
    session = FakeSession(positions=[], risk_levels={}, quotes={})

    _run(monitor._check_once(session))

    assert [c[0] for c in session.calls] == ["get_positions", "get_risk_levels"]


def test_stale_ledger_entry_without_a_position_is_skipped():
    session = FakeSession(
        positions=[],
        risk_levels={"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}},
        quotes={},
    )

    _run(monitor._check_once(session))

    # nothing held under that symbol, so no get_quote / place_order call either
    assert [c[0] for c in session.calls] == ["get_positions", "get_risk_levels"]


def test_price_within_range_does_not_exit():
    session = FakeSession(
        positions=[{"symbol": "AAPL", "quantity": 5, "average_buy_price": 100.0}],
        risk_levels={"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}},
        quotes={"AAPL": {"symbol": "AAPL", "price": 102.0}},
    )

    _run(monitor._check_once(session))

    assert all(c[0] != "place_order" for c in session.calls)


def test_stop_loss_breach_submits_a_market_sell():
    session = FakeSession(
        positions=[{"symbol": "AAPL", "quantity": 5, "average_buy_price": 100.0}],
        risk_levels={"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}},
        quotes={"AAPL": {"symbol": "AAPL", "price": 94.0}},
    )

    _run(monitor._check_once(session))

    sell_calls = [c for c in session.calls if c[0] == "place_order"]
    assert len(sell_calls) == 1
    assert sell_calls[0][1] == {
        "symbol": "AAPL",
        "side": "sell",
        "quantity": 5,
        "order_type": "market",
        "price": 94.0,
    }


def test_take_profit_breach_submits_a_market_sell():
    session = FakeSession(
        positions=[{"symbol": "AAPL", "quantity": 5, "average_buy_price": 100.0}],
        risk_levels={"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}},
        quotes={"AAPL": {"symbol": "AAPL", "price": 111.0}},
    )

    _run(monitor._check_once(session))

    sell_calls = [c for c in session.calls if c[0] == "place_order"]
    assert len(sell_calls) == 1
    assert sell_calls[0][1]["side"] == "sell"
    assert sell_calls[0][1]["quantity"] == 5


def test_quote_error_skips_without_placing_an_order():
    session = FakeSession(
        positions=[{"symbol": "AAPL", "quantity": 5, "average_buy_price": 100.0}],
        risk_levels={"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}},
        quotes={"AAPL": {"error": "quote feed unavailable"}},
    )

    _run(monitor._check_once(session))

    assert all(c[0] != "place_order" for c in session.calls)


def test_run_never_connects_when_not_live_mode(monkeypatch, capsys):
    monkeypatch.delenv("ROBINHOOD_MCP_MODE", raising=False)  # defaults to "paper"
    monkeypatch.setattr(
        monitor, "stdio_client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not connect"))
    )

    _run(monitor.run())

    assert "nothing to monitor" in capsys.readouterr().out


def test_run_never_connects_without_mcp_command(monkeypatch, capsys):
    monkeypatch.setenv("ROBINHOOD_MCP_MODE", "live")
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)
    monkeypatch.setattr(
        monitor, "stdio_client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not connect"))
    )

    _run(monitor.run())

    assert "ROBINHOOD_MCP_COMMAND is not set" in capsys.readouterr().out


def test_only_one_of_several_held_symbols_breaches():
    session = FakeSession(
        positions=[
            {"symbol": "AAPL", "quantity": 5, "average_buy_price": 100.0},
            {"symbol": "MSFT", "quantity": 2, "average_buy_price": 300.0},
        ],
        risk_levels={
            "AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0},
            "MSFT": {"side": "buy", "stop_loss": 280.0, "take_profit": 320.0},
        },
        quotes={
            "AAPL": {"symbol": "AAPL", "price": 102.0},  # within range
            "MSFT": {"symbol": "MSFT", "price": 325.0},  # take-profit breached
        },
    )

    _run(monitor._check_once(session))

    sell_calls = [c for c in session.calls if c[0] == "place_order"]
    assert len(sell_calls) == 1
    assert sell_calls[0][1]["symbol"] == "MSFT"
