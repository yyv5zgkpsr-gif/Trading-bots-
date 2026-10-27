"""End-to-end coverage that spawns the real robinhood_mcp server as a
subprocess (exactly how CryptoExecutionAgent invokes it in production)
instead of mocking the MCP transport — same pattern as
test_execution_mcp_integration.py for stocks.
"""

import sys

from models.schemas import CryptoRiskDecision

from agents.crypto_execution import CryptoExecutionAgent

SERVER_COMMAND = f"{sys.executable} -m robinhood_mcp.server"


def _configure_live_paper_mcp(monkeypatch, tmp_path, starting_cash="1000"):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ROBINHOOD_MCP_COMMAND", SERVER_COMMAND)
    monkeypatch.setenv("ROBINHOOD_MCP_MODE", "paper")
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("CRYPTO_PAPER_STATE_PATH", str(tmp_path / "crypto_state.json"))
    monkeypatch.setenv("CRYPTO_PAPER_STARTING_CASH", starting_cash)
    monkeypatch.setenv("RISK_LEDGER_PATH", str(tmp_path / "risk_levels.json"))


def test_get_account_balance_reflects_configured_starting_cash(monkeypatch, tmp_path):
    _configure_live_paper_mcp(monkeypatch, tmp_path, starting_cash="54321")

    agent = CryptoExecutionAgent()

    assert agent.get_account_balance() == 54321.0


def test_place_order_fills_against_the_real_server_and_persists_state(monkeypatch, tmp_path):
    _configure_live_paper_mcp(monkeypatch, tmp_path)

    agent = CryptoExecutionAgent()
    risk = CryptoRiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_quantity=0.01,
        stop_loss_price=55_000.0,
        take_profit_price=65_000.0,
        reasoning="test",
        entry_price=50_000.0,
    )

    result = agent.run("BTC", risk)

    assert result.executed is True
    assert result.dry_run is False
    assert result.order_id.startswith("crypto-paper-")

    balance_after = agent.get_account_balance()
    assert balance_after == 1000.0 - 0.01 * 50_000.0


def test_get_positions_returns_every_held_symbol_not_just_the_first(monkeypatch, tmp_path):
    """get_crypto_positions is a list-returning tool, which this MCP version
    sends as one block PER ITEM rather than a single JSON array (see
    agents/crypto_execution.py's _call_tool docstring) — buying two
    different symbols and checking both come back is what would have
    caught the earlier version of _call_tool silently keeping only the
    first block."""
    _configure_live_paper_mcp(monkeypatch, tmp_path, starting_cash="100000")

    agent = CryptoExecutionAgent()
    btc_risk = CryptoRiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_quantity=0.01,
        stop_loss_price=55_000.0,
        take_profit_price=65_000.0,
        reasoning="test",
        entry_price=50_000.0,
    )
    eth_risk = CryptoRiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_quantity=1.0,
        stop_loss_price=2_500.0,
        take_profit_price=3_500.0,
        reasoning="test",
        entry_price=3_000.0,
    )

    assert agent.run("BTC", btc_risk).executed is True
    assert agent.run("ETH", eth_risk).executed is True

    positions = agent.get_positions()

    assert {p["symbol"] for p in positions} == {"BTC", "ETH"}
    btc_position = next(p for p in positions if p["symbol"] == "BTC")
    assert btc_position["quantity"] == 0.01


def test_get_positions_returns_none_without_live_config(monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)

    agent = CryptoExecutionAgent()

    assert agent.get_positions() is None


def test_broker_rejection_surfaces_as_a_failed_execution(monkeypatch, tmp_path):
    _configure_live_paper_mcp(monkeypatch, tmp_path)

    agent = CryptoExecutionAgent()
    risk = CryptoRiskDecision(
        approved=True,
        action="SELL",
        position_size_usd=500.0,
        position_size_quantity=0.01,
        stop_loss_price=52_000.0,
        take_profit_price=45_000.0,
        reasoning="test",
        entry_price=50_000.0,
    )

    result = agent.run("BTC", risk)  # nothing was ever bought

    assert result.executed is False
    assert result.dry_run is False
    assert "Execution failed" in result.details
    assert "held" in result.details
