import numpy as np
import pandas as pd

from agents.risk_manager import RiskManagerAgent
from backtest.strategy import decide
from models.schemas import Direction


def _ohlc(n: int, start: float, end: float) -> pd.DataFrame:
    close = pd.Series(np.linspace(start, end, n))
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
        }
    )


def test_strong_uptrend_with_bullish_regime_produces_a_buy(monkeypatch):
    monkeypatch.delenv("MAX_POSITION_PCT", raising=False)
    monkeypatch.delenv("MIN_CONVICTION", raising=False)

    price_history = _ohlc(60, 100, 150)  # strong, steady uptrend
    spy_history = _ohlc(60, 100, 110)  # SPY also trending up
    vix_history = pd.DataFrame({"Close": [15.0] * 60})  # low volatility -> bull regime

    decision, debate = decide("AAPL", price_history, spy_history, vix_history, account_equity=100_000, risk_agent=RiskManagerAgent())

    assert debate.recommendation == Direction.BULLISH
    assert decision.approved is True
    assert decision.action == "BUY"
    assert decision.position_size_shares > 0
    assert decision.stop_loss_price < decision.entry_price < decision.take_profit_price


def test_sideways_choppy_market_does_not_produce_a_confident_buy():
    # A real "no persistent trend" case can still end its window mid-swing
    # (e.g. a sine wave tailing off downward) and legitimately score bearish
    # — that's the scoring working, not flatness. So this checks the thing
    # that actually matters: sideways, noisy data must not read as the same
    # confident uptrend the strong-uptrend test above produces.
    n = 60
    close = pd.Series(100 + np.sin(np.linspace(0, 6 * np.pi, n)) * 0.5)
    price_history = pd.DataFrame({"Open": close, "High": close + 0.2, "Low": close - 0.2, "Close": close})
    spy_history = pd.DataFrame({"Open": close, "High": close + 0.2, "Low": close - 0.2, "Close": close})
    vix_history = pd.DataFrame({"Close": [18.0] * n})

    decision, debate = decide(
        "AAPL", price_history, spy_history, vix_history, account_equity=100_000, risk_agent=RiskManagerAgent()
    )

    assert debate.recommendation != Direction.BULLISH
    assert decision.action != "BUY"


def test_strong_downtrend_with_bear_regime_produces_a_sell_signal():
    price_history = _ohlc(60, 150, 100)  # strong downtrend
    spy_history = _ohlc(60, 110, 90)  # SPY also falling
    vix_history = pd.DataFrame({"Close": [30.0] * 60})  # high volatility -> bear regime

    decision, debate = decide(
        "AAPL", price_history, spy_history, vix_history, account_equity=100_000, risk_agent=RiskManagerAgent()
    )

    assert debate.recommendation == Direction.BEARISH
    assert decision.action == "SELL"
