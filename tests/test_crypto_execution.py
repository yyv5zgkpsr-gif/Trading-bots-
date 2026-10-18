from models.schemas import CryptoRiskDecision

from agents.crypto_execution import CryptoExecutionAgent


def _approved_risk_decision() -> CryptoRiskDecision:
    return CryptoRiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_quantity=0.01,
        stop_loss_price=55_000.0,
        take_profit_price=65_000.0,
        reasoning="stub",
        entry_price=60_000.0,
    )


def test_defaults_to_dry_run_without_config(monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)

    agent = CryptoExecutionAgent()
    result = agent.run("BTC", _approved_risk_decision())

    assert result.executed is False
    assert result.dry_run is True
    assert "DRY RUN" in result.details


def test_live_flag_without_mcp_command_stays_dry_run(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)

    agent = CryptoExecutionAgent()
    result = agent.run("BTC", _approved_risk_decision())

    assert result.executed is False
    assert result.dry_run is True


def test_unapproved_risk_decision_never_executes(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ROBINHOOD_MCP_COMMAND", "echo mock-server")

    agent = CryptoExecutionAgent()
    hold_decision = CryptoRiskDecision(
        approved=False,
        action="HOLD",
        position_size_usd=0.0,
        position_size_quantity=0.0,
        stop_loss_price=None,
        take_profit_price=None,
        reasoning="stub",
    )
    result = agent.run("BTC", hold_decision)

    assert result.executed is False
    assert "did not approve" in result.details


def test_get_account_balance_returns_none_without_live_config(monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)

    agent = CryptoExecutionAgent()

    assert agent.get_account_balance() is None
