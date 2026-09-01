from models.schemas import RiskDecision

from agents.execution import ExecutionAgent


def _approved_risk_decision() -> RiskDecision:
    return RiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_shares=5,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        reasoning="stub",
    )


def test_defaults_to_dry_run_without_config(monkeypatch):
    monkeypatch.delenv("ENABLE_LIVE_TRADING", raising=False)
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)

    agent = ExecutionAgent()
    result = agent.run("AAPL", _approved_risk_decision())

    assert result.executed is False
    assert result.dry_run is True
    assert "DRY RUN" in result.details


def test_live_flag_without_mcp_command_stays_dry_run(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.delenv("ROBINHOOD_MCP_COMMAND", raising=False)

    agent = ExecutionAgent()
    result = agent.run("AAPL", _approved_risk_decision())

    assert result.executed is False
    assert result.dry_run is True


def test_unapproved_risk_decision_never_executes(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("ROBINHOOD_MCP_COMMAND", "echo mock-server")

    agent = ExecutionAgent()
    hold_decision = RiskDecision(
        approved=False,
        action="HOLD",
        position_size_usd=0.0,
        position_size_shares=0,
        stop_loss_price=None,
        take_profit_price=None,
        reasoning="stub",
    )
    result = agent.run("AAPL", hold_decision)

    assert result.executed is False
    assert "did not approve" in result.details
