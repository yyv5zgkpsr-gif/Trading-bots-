from unittest.mock import MagicMock

from models.schemas import (
    DebateResult,
    Direction,
    ExecutionResult,
    FundamentalReport,
    MarketRegimeReport,
    NewsReport,
    Regime,
    RiskDecision,
    SentimentReport,
    TechnicalReport,
)

from agents.orchestrator import Orchestrator


def _stub_reports():
    news = NewsReport(ticker="AAPL", headlines=[], catalysts=[], catalyst_score=0.2, summary="news")
    technical = TechnicalReport(
        ticker="AAPL",
        trend=Direction.BULLISH,
        rsi=60.0,
        macd=1.0,
        macd_signal=0.5,
        support=90.0,
        resistance=110.0,
        last_price=100.0,
        technical_score=0.4,
        summary="technical",
    )
    fundamental = FundamentalReport(
        ticker="AAPL",
        pe_ratio=20.0,
        peg_ratio=1.5,
        debt_to_equity=50.0,
        revenue_growth=0.15,
        profit_margin=0.2,
        fundamental_score=0.3,
        summary="fundamental",
    )
    sentiment = SentimentReport(ticker="AAPL", sentiment_score=0.25, momentum_5d=2.0, momentum_20d=5.0, summary="sentiment")
    regime = MarketRegimeReport(regime=Regime.BULL, volatility=15.0, spy_trend=Direction.BULLISH, rate_10y=4.2, summary="regime")
    debate = DebateResult(bull_thesis="bull", bear_thesis="bear", conviction=0.5, recommendation=Direction.BULLISH)
    risk = RiskDecision(
        approved=True,
        action="BUY",
        position_size_usd=500.0,
        position_size_shares=5,
        stop_loss_price=95.0,
        take_profit_price=110.0,
        reasoning="risk",
    )
    execution = ExecutionResult(executed=False, dry_run=True, order_id=None, details="dry run")
    return news, technical, fundamental, sentiment, regime, debate, risk, execution


def test_orchestrator_wires_agents_and_assembles_decision():
    news, technical, fundamental, sentiment, regime, debate, risk, execution = _stub_reports()

    orchestrator = Orchestrator()
    orchestrator.news_agent = MagicMock(run=MagicMock(return_value=news))
    orchestrator.technical_agent = MagicMock(run=MagicMock(return_value=technical))
    orchestrator.fundamental_agent = MagicMock(run=MagicMock(return_value=fundamental))
    orchestrator.sentiment_agent = MagicMock(run=MagicMock(return_value=sentiment))
    orchestrator.regime_agent = MagicMock(run=MagicMock(return_value=regime))
    orchestrator.debate_agent = MagicMock(run=MagicMock(return_value=debate))
    orchestrator.risk_agent = MagicMock(run=MagicMock(return_value=risk))
    orchestrator.execution_agent = MagicMock(run=MagicMock(return_value=execution))

    decision = orchestrator.run("AAPL", account_equity=10_000)

    orchestrator.news_agent.run.assert_called_once_with("AAPL")
    orchestrator.technical_agent.run.assert_called_once_with("AAPL")
    orchestrator.fundamental_agent.run.assert_called_once_with("AAPL")
    orchestrator.sentiment_agent.run.assert_called_once_with("AAPL", news)
    orchestrator.regime_agent.run.assert_called_once_with()
    orchestrator.debate_agent.run.assert_called_once_with("AAPL", news, technical, fundamental, sentiment, regime)
    orchestrator.risk_agent.run.assert_called_once_with(debate, technical, 10_000)
    orchestrator.execution_agent.run.assert_called_once_with("AAPL", risk)

    assert decision.ticker == "AAPL"
    assert decision.news is news
    assert decision.risk is risk
    assert decision.execution is execution


def test_orchestrator_defaults_account_equity_from_env(monkeypatch):
    news, technical, fundamental, sentiment, regime, debate, risk, execution = _stub_reports()
    monkeypatch.setenv("DEFAULT_ACCOUNT_EQUITY", "42000")

    orchestrator = Orchestrator()
    orchestrator.news_agent = MagicMock(run=MagicMock(return_value=news))
    orchestrator.technical_agent = MagicMock(run=MagicMock(return_value=technical))
    orchestrator.fundamental_agent = MagicMock(run=MagicMock(return_value=fundamental))
    orchestrator.sentiment_agent = MagicMock(run=MagicMock(return_value=sentiment))
    orchestrator.regime_agent = MagicMock(run=MagicMock(return_value=regime))
    orchestrator.debate_agent = MagicMock(run=MagicMock(return_value=debate))
    orchestrator.risk_agent = MagicMock(run=MagicMock(return_value=risk))
    orchestrator.execution_agent = MagicMock(run=MagicMock(return_value=execution))

    orchestrator.run("AAPL")

    orchestrator.risk_agent.run.assert_called_once_with(debate, technical, 42000.0)
