from models.schemas import DebateResult, Direction, TechnicalReport
from agents.crypto_risk_manager import CryptoRiskManagerAgent


def _technical(price: float) -> TechnicalReport:
    return TechnicalReport(
        ticker="BTC",
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
    agent = CryptoRiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.05, recommendation=Direction.NEUTRAL)

    decision = agent.run(debate, _technical(60_000.0), account_equity=10_000)

    assert decision.approved is False
    assert decision.action == "HOLD"
    assert decision.position_size_quantity == 0.0


def test_strong_bullish_conviction_sizes_a_fractional_buy():
    agent = CryptoRiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.8, recommendation=Direction.BULLISH)

    decision = agent.run(debate, _technical(60_000.0), account_equity=10_000)

    assert decision.approved is True
    assert decision.action == "BUY"
    assert decision.position_size_quantity > 0
    assert decision.stop_loss_price < decision.entry_price < decision.take_profit_price


def test_strong_bearish_conviction_sizes_a_sell_signal():
    agent = CryptoRiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=-0.8, recommendation=Direction.BEARISH)

    decision = agent.run(debate, _technical(60_000.0), account_equity=10_000)

    assert decision.approved is True
    assert decision.action == "SELL"
    assert decision.stop_loss_price > decision.entry_price > decision.take_profit_price


def test_position_below_minimum_order_size_holds(monkeypatch):
    monkeypatch.setenv("MIN_CRYPTO_ORDER_USD", "100")
    agent = CryptoRiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=0.2, recommendation=Direction.BULLISH)

    # equity small enough that 5% * conviction_scale is well under $100
    decision = agent.run(debate, _technical(60_000.0), account_equity=100)

    assert decision.approved is False
    assert decision.action == "HOLD"


def test_env_overrides_change_sizing(monkeypatch):
    monkeypatch.setenv("CRYPTO_MAX_POSITION_PCT", "0.5")
    agent = CryptoRiskManagerAgent()
    debate = DebateResult(bull_thesis="", bear_thesis="", conviction=1.0, recommendation=Direction.BULLISH)

    decision = agent.run(debate, _technical(100.0), account_equity=10_000)

    assert decision.position_size_usd == 5_000.0
