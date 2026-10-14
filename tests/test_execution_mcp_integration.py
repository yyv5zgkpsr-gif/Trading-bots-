"""End-to-end coverage that spawns the real robinhood_mcp server as a subprocess
(exactly how ExecutionAgent invokes it in production) instead of mocking the MCP
transport. This is what caught a real bug: mcp's stdio_client only forwards a
safety allowlist of env vars (PATH, HOME, ...) to the spawned server by default,
silently dropping ROBINHOOD_MCP_MODE / PAPER_STARTING_CASH / PAPER_STATE_PATH —
so the server always ran in default paper mode regardless of configuration.
"""

import sys

from models.schemas import RiskDecision

from agents.execution import ExecutionAgent

SERVER_COMMAND = f"{sys.executable} -m robinhood_mcp.server"


def _configure_live_paper_mcp(monkeypatch, tmp_path, starting_cash="1000"):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ROBINHOOD_MCP_COMMAND", SERVER_COMMAND)
    monkeypatch.setenv("ROBINHOOD_MCP_MODE", "paper")
    monkeypatch.setenv("PAPER_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("PAPER_STARTING_CASH", starting_cash)


def test_get_account_equity_reflects_configured_starting_cash(monkeypatch, tmp_path):
    _configure_live_paper_mcp(monkeypatch, tmp_path, starting_cash="55555")

    agent = ExecutionAgent()

    assert agent.get_account_equity() == 55555.0
    assert (tmp_path / "state.json").exists()


def test_place_order_fills_against_the_real_server_and_persists_state(monkeypatch, tmp_path):
    _configure_live_paper_mcp(monkeypatch, tmp_path)

    agent = ExecutionAgent()
    risk = RiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_shares=5,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        reasoning="test",
        entry_price=100.0,
    )

    result = agent.run("AAPL", risk)

    assert result.executed is True
    assert result.dry_run is False
    assert result.order_id.startswith("paper-")

    equity_after = agent.get_account_equity()
    assert equity_after == 1000.0  # bought 5 @ 100, cash->position, no P&L yet


def test_broker_rejection_surfaces_as_a_failed_execution(monkeypatch, tmp_path):
    _configure_live_paper_mcp(monkeypatch, tmp_path)

    agent = ExecutionAgent()
    risk = RiskDecision(
        approved=True,
        action="SELL",
        position_size_usd=500.0,
        position_size_shares=5,
        stop_loss_price=105.0,
        take_profit_price=90.0,
        reasoning="test",
        entry_price=100.0,
    )

    result = agent.run("AAPL", risk)  # nothing was ever bought, so this must be rejected

    assert result.executed is False
    assert result.dry_run is False
    assert "Execution failed" in result.details
    assert "0 held" in result.details
