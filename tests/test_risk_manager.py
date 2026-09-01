from models.schemas import DebateResult, Direction, TechnicalReport
from agents.risk_manager import RiskManagerAgent


def _technical(price: float) -> TechnicalReport:
    return TechnicalReport(
        ticker="TEST",
        trend=Direction.BULLISH,
        rsi=55.0,
        macd=0.5,
        macd_signal=0.2,
        support=price * 0.9,
        resistance=price * 1.1,
        last_price=price,
        technical_score=0.5,
        summary="stub",
    )


def test_neutral_debate_results_in_hold():
    agent = RiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.05, recommendation=Direction.NEUTRAL)

    decision = agent.run(debate, _technical(100.0), account_equity=10_000)

    assert decision.approved is False
    assert decision.action == "HOLD"
    assert decision.position_size_shares == 0


def test_low_conviction_below_threshold_results_in_hold():
    agent = RiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.1, recommendation=Direction.BULLISH)

    decision = agent.run(debate, _technical(100.0), account_equity=10_000)

    assert decision.approved is False
    assert decision.action == "HOLD"


def test_strong_bullish_conviction_sizes_a_buy_with_stop_and_target():
    agent = RiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.8, recommendation=Direction.BULLISH)

    decision = agent.run(debate, _technical(100.0), account_equity=10_000)

    assert decision.approved is True
    assert decision.action == "BUY"
    assert decision.position_size_shares > 0
    assert decision.stop_loss_price < 100.0
    assert decision.take_profit_price > 100.0


def test_strong_bearish_conviction_sizes_a_sell_with_stop_and_target():
    agent = RiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=-0.8, recommendation=Direction.BEARISH)

    decision = agent.run(debate, _technical(100.0), account_equity=10_000)

    assert decision.approved is True
    assert decision.action == "SELL"
    assert decision.stop_loss_price > 100.0
    assert decision.take_profit_price < 100.0


def test_tiny_equity_rounds_down_to_zero_shares_and_holds():
    agent = RiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.8, recommendation=Direction.BULLISH)

    decision = agent.run(debate, _technical(100_000.0), account_equity=100)

    assert decision.approved is False
    assert decision.action == "HOLD"
