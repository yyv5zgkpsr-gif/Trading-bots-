"""Exercises the MCP tool functions directly (bypassing the stdio transport) to
confirm they're wired to the paper broker and shaped the way agents/execution.py
expects."""

import importlib
import sys

import pytest


@pytest.fixture
def server_module(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBINHOOD_MCP_MODE", "paper")
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("PAPER_STARTING_CASH", "10000")
    monkeypatch.setenv("CRYPTO_PAPER_STATE_PATH", str(tmp_path / "crypto_state.json"))
    monkeypatch.setenv("CRYPTO_PAPER_STARTING_CASH", "10000")
    monkeypatch.setenv("RISK_LEDGER_PATH", str(tmp_path / "risk_levels.json"))
    sys.modules.pop("robinhood_mcp.server", None)
    module = importlib.import_module("robinhood_mcp.server")
    yield module
    sys.modules.pop("robinhood_mcp.server", None)


def test_get_account_reports_paper_mode(server_module):
    account = server_module.get_account()
    assert account["mode"] == "paper"
    assert account["cash"] == 10000.0


def test_place_order_fills_and_updates_positions(server_module):
    result = server_module.place_order("AAPL", "buy", 5, price=100.0, stop_loss=95.0, take_profit=110.0)

    assert result["order_id"].startswith("paper-")
    assert result["stop_loss"] == 95.0
    assert result["take_profit"] == 110.0

    positions = server_module.get_positions()
    assert positions == [{"symbol": "AAPL", "quantity": 5, "average_buy_price": 100.0}]


def test_place_order_surfaces_broker_errors_without_raising(server_module):
    result = server_module.place_order("AAPL", "sell", 5, price=100.0)

    assert "error" in result
    assert "0 held" in result["error"]


def test_place_order_records_risk_levels_on_buy(server_module):
    server_module.place_order("AAPL", "buy", 5, price=100.0, stop_loss=95.0, take_profit=110.0)

    levels = server_module.get_risk_levels()

    assert levels == {"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}}


def test_place_order_without_stop_or_target_records_nothing(server_module):
    server_module.place_order("AAPL", "buy", 5, price=100.0)

    assert server_module.get_risk_levels() == {}


def test_place_order_sell_clears_risk_levels(server_module):
    server_module.place_order("AAPL", "buy", 5, price=100.0, stop_loss=95.0, take_profit=110.0)
    server_module.place_order("AAPL", "sell", 5, price=120.0)

    assert server_module.get_risk_levels() == {}


def test_get_quote_errors_in_paper_mode(server_module):
    result = server_module.get_quote("AAPL")

    assert "error" in result
    assert "paper mode" in result["error"]


def test_get_crypto_account_reports_paper_mode(server_module):
    account = server_module.get_crypto_account()
    assert account["mode"] == "paper"
    assert account["cash"] == 10000.0


def test_crypto_account_is_a_separate_balance_from_the_stock_account(server_module):
    server_module.place_order("AAPL", "buy", 5, price=100.0)

    stock_account = server_module.get_account()
    crypto_account = server_module.get_crypto_account()

    assert stock_account["cash"] == 10000.0 - 500.0
    assert crypto_account["cash"] == 10000.0  # untouched by the stock trade


def test_place_crypto_order_fills_fractional_quantity(server_module):
    result = server_module.place_crypto_order("BTC", "buy", 0.01, price=60_000.0, stop_loss=55_000.0, take_profit=65_000.0)

    assert result["order_id"].startswith("crypto-paper-")
    assert result["stop_loss"] == 55_000.0
    assert result["take_profit"] == 65_000.0

    positions = server_module.get_crypto_positions()
    assert positions == [{"symbol": "BTC", "quantity": 0.01, "average_buy_price": 60_000.0}]


def test_place_crypto_order_surfaces_broker_errors_without_raising(server_module):
    result = server_module.place_crypto_order("BTC", "sell", 1.0, price=60_000.0)

    assert "error" in result
    assert "held" in result["error"]


def test_place_crypto_order_records_and_clears_risk_levels(server_module):
    server_module.place_crypto_order("BTC", "buy", 0.01, price=60_000.0, stop_loss=55_000.0, take_profit=65_000.0)
    assert server_module.get_risk_levels() == {"BTC": {"side": "buy", "stop_loss": 55_000.0, "take_profit": 65_000.0}}

    server_module.place_crypto_order("BTC", "sell", 0.01, price=62_000.0)
    assert server_module.get_risk_levels() == {}


def test_risk_ledger_is_shared_across_stocks_and_crypto(server_module):
    server_module.place_order("AAPL", "buy", 5, price=100.0, stop_loss=95.0, take_profit=110.0)
    server_module.place_crypto_order("BTC", "buy", 0.01, price=60_000.0, stop_loss=55_000.0, take_profit=65_000.0)

    levels = server_module.get_risk_levels()
    assert set(levels.keys()) == {"AAPL", "BTC"}


def test_get_crypto_quote_errors_in_paper_mode(server_module):
    result = server_module.get_crypto_quote("BTC")

    assert "error" in result
    assert "paper mode" in result["error"]


def test_unknown_mode_refuses_to_start(monkeypatch, tmp_path):
    monkeypatch.setenv("ROBINHOOD_MCP_MODE", "bogus")
    sys.modules.pop("robinhood_mcp.server", None)
    with pytest.raises(SystemExit, match="unknown ROBINHOOD_MCP_MODE"):
        importlib.import_module("robinhood_mcp.server")
    sys.modules.pop("robinhood_mcp.server", None)
