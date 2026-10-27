import numpy as np
import pandas as pd

from agents.crypto_risk_manager import CryptoRiskManagerAgent
from backtest.crypto_strategy import decide
from models.schemas import Direction


def _ohlc(n: int, start: float, end: float) -> pd.DataFrame:
    close = pd.Series(np.linspace(start, end, n))
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close})


def test_strong_uptrend_produces_a_buy(monkeypatch):
    monkeypatch.delenv("CRYPTO_MAX_POSITION_PCT", raising=False)
    monkeypatch.delenv("MAX_POSITION_PCT", raising=False)
    monkeypatch.delenv("MIN_CONVICTION", raising=False)

    price_history = _ohlc(60, 50_000, 70_000)  # strong, steady uptrend

    decision, debate = decide("BTC", price_history, account_equity=100_000, risk_agent=CryptoRiskManagerAgent())

    assert debate.recommendation == Direction.BULLISH
    assert decision.approved is True
    assert decision.action == "BUY"
    assert decision.position_size_quantity > 0
    assert decision.stop_loss_price < decision.entry_price < decision.take_profit_price


def test_sideways_choppy_market_does_not_produce_a_confident_buy():
    n = 60
    close = pd.Series(60_000 + np.sin(np.linspace(0, 6 * np.pi, n)) * 300)
    price_history = pd.DataFrame({"Open": close, "High": close + 100, "Low": close - 100, "Close": close})

    decision, debate = decide("BTC", price_history, account_equity=100_000, risk_agent=CryptoRiskManagerAgent())

    assert debate.recommendation != Direction.BULLISH
    assert decision.action != "BUY"


def test_strong_downtrend_produces_a_sell_signal():
    price_history = _ohlc(60, 70_000, 50_000)  # strong downtrend

    decision, debate = decide("BTC", price_history, account_equity=100_000, risk_agent=CryptoRiskManagerAgent())

    assert debate.recommendation == Direction.BEARISH
    assert decision.action == "SELL"
