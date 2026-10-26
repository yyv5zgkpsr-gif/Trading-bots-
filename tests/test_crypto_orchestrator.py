from unittest.mock import MagicMock

from models.schemas import (
    DebateResult,
    Direction,
    ExecutionResult,
    TechnicalReport,
)
from models.schemas import CryptoRiskDecision

from agents.crypto_debate import CryptoDebateAgent
from agents.crypto_orchestrator import CryptoOrchestrator
from agents.ml_crypto_debate import MLCryptoDebateAgent


def _stub_reports():
    technical = TechnicalReport(
        ticker="BTC",
        trend=Direction.BULLISH,
        rsi=60.0,
        macd=1.0,
        macd_signal=0.5,
        support=58_000.0,
        resistance=62_000.0,
        last_price=60_000.0,
        technical_score=0.4,
        summary="technical",
    )
    debate = DebateResult(bull_thesis="bull", bear_thesis="bear", conviction=0.4, recommendation=Direction.BULLISH)
    risk = CryptoRiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_quantity=0.0083,
        stop_loss_price=57_000.0,
        take_profit_price=66_000.0,
        reasoning="risk",
        entry_price=60_000.0,
    )
    execution = ExecutionResult(executed=False, dry_run=True, order_id=None, details="dry run")
    return technical, debate, risk, execution


def test_orchestrator_wires_agents_and_assembles_decision():
    technical, debate, risk, execution = _stub_reports()

    orchestrator = CryptoOrchestrator()
    orchestrator.technical_agent = MagicMock(run=MagicMock(return_value=technical))
    orchestrator.debate_agent = MagicMock(run=MagicMock(return_value=debate))
    orchestrator.risk_agent = MagicMock(run=MagicMock(return_value=risk))
    orchestrator.execution_agent = MagicMock(run=MagicMock(return_value=execution))

    decision = orchestrator.run("BTC", account_equity=10_000)

    orchestrator.technical_agent.run.assert_called_once_with("BTC")
    orchestrator.debate_agent.run.assert_called_once_with("BTC", technical)
    orchestrator.risk_agent.run.assert_called_once_with(debate, technical, 10_000)
    orchestrator.execution_agent.run.assert_called_once_with("BTC", risk)

    assert decision.symbol == "BTC"
    assert decision.technical is technical
    assert decision.risk is risk
    assert decision.execution is execution


def test_orchestrator_prefers_live_balance_over_env_default(monkeypatch):
    technical, debate, risk, execution = _stub_reports()
    monkeypatch.setenv("CRYPTO_DEFAULT_ACCOUNT_EQUITY", "42000")

    orchestrator = CryptoOrchestrator()
    orchestrator.technical_agent = MagicMock(run=MagicMock(return_value=technical))
    orchestrator.debate_agent = MagicMock(run=MagicMock(return_value=debate))
    orchestrator.risk_agent = MagicMock(run=MagicMock(return_value=risk))
    orchestrator.execution_agent = MagicMock(
        run=MagicMock(return_value=execution), get_account_balance=MagicMock(return_value=17_500.0)
    )

    orchestrator.run("BTC")

    orchestrator.risk_agent.run.assert_called_once_with(debate, technical, 17_500.0)


def test_orchestrator_defaults_to_env_when_no_live_balance(monkeypatch):
    technical, debate, risk, execution = _stub_reports()
    monkeypatch.setenv("CRYPTO_DEFAULT_ACCOUNT_EQUITY", "42000")

    orchestrator = CryptoOrchestrator()
    orchestrator.technical_agent = MagicMock(run=MagicMock(return_value=technical))
    orchestrator.debate_agent = MagicMock(run=MagicMock(return_value=debate))
    orchestrator.risk_agent = MagicMock(run=MagicMock(return_value=risk))
    orchestrator.execution_agent = MagicMock(
        run=MagicMock(return_value=execution), get_account_balance=MagicMock(return_value=None)
    )

    orchestrator.run("BTC")

    orchestrator.risk_agent.run.assert_called_once_with(debate, technical, 42000.0)


def test_orchestrator_explicit_equity_overrides_live_lookup():
    technical, debate, risk, execution = _stub_reports()

    orchestrator = CryptoOrchestrator()
    orchestrator.technical_agent = MagicMock(run=MagicMock(return_value=technical))
    orchestrator.debate_agent = MagicMock(run=MagicMock(return_value=debate))
    orchestrator.risk_agent = MagicMock(run=MagicMock(return_value=risk))
    orchestrator.execution_agent = MagicMock(
        run=MagicMock(return_value=execution), get_account_balance=MagicMock(return_value=17_500.0)
    )

    orchestrator.run("BTC", account_equity=5_000.0)

    orchestrator.execution_agent.get_account_balance.assert_not_called()
    orchestrator.risk_agent.run.assert_called_once_with(debate, technical, 5_000.0)


def test_orchestrator_uses_rule_based_debate_by_default(monkeypatch):
    monkeypatch.delenv("USE_ML_SIGNAL", raising=False)

    orchestrator = CryptoOrchestrator()

    assert isinstance(orchestrator.debate_agent, CryptoDebateAgent)


def test_orchestrator_uses_ml_debate_when_use_ml_signal_is_set(monkeypatch):
    monkeypatch.setenv("USE_ML_SIGNAL", "true")

    orchestrator = CryptoOrchestrator()

    assert isinstance(orchestrator.debate_agent, MLCryptoDebateAgent)
