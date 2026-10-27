import numpy as np
import pandas as pd

from agents.crypto_risk_manager import CryptoRiskManagerAgent
from ml.ml_strategy import decide
from models.schemas import Direction


class _FixedConvictionModel:
    """Stands in for a trained DirectionModel: always returns the same
    conviction, regardless of the features it's handed, so decide()'s
    gating logic can be tested independently of any real model's math."""

    def __init__(self, conviction: float):
        self.conviction = conviction

    def predict_conviction(self, X: pd.DataFrame) -> pd.Series:
        return pd.Series([self.conviction] * len(X), index=X.index)


def _ohlc(n: int = 60, start: float = 50_000.0, end: float = 55_000.0) -> pd.DataFrame:
    close = np.linspace(start, end, n)  # a plain array, not a Series, so it isn't reindexed against `index` below
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close},
        index=pd.date_range("2022-01-01", periods=n, freq="D"),
    )


def test_decide_buys_when_model_conviction_is_strongly_bullish(monkeypatch):
    monkeypatch.delenv("CRYPTO_MAX_POSITION_PCT", raising=False)
    monkeypatch.delenv("MAX_POSITION_PCT", raising=False)
    monkeypatch.delenv("MIN_CONVICTION", raising=False)

    risk, debate = decide("BTC", _ohlc(), account_equity=100_000, risk_agent=CryptoRiskManagerAgent(), model=_FixedConvictionModel(0.8))

    assert debate.recommendation == Direction.BULLISH
    assert debate.conviction == 0.8
    assert risk.approved is True
    assert risk.action == "BUY"
    assert risk.position_size_quantity > 0


def test_decide_sells_when_model_conviction_is_strongly_bearish():
    risk, debate = decide("BTC", _ohlc(), account_equity=100_000, risk_agent=CryptoRiskManagerAgent(), model=_FixedConvictionModel(-0.8))

    assert debate.recommendation == Direction.BEARISH
    assert risk.action == "SELL"


def test_decide_holds_when_model_conviction_is_near_zero():
    risk, debate = decide("BTC", _ohlc(), account_equity=100_000, risk_agent=CryptoRiskManagerAgent(), model=_FixedConvictionModel(0.01))

    assert debate.recommendation == Direction.NEUTRAL
    assert risk.action == "HOLD"
    assert risk.approved is False


def test_decide_holds_when_history_is_too_short_for_every_feature_to_warm_up():
    short_history = _ohlc(n=10)  # far short of the SMA50/rolling-20 warmup

    risk, debate = decide(
        "BTC", short_history, account_equity=100_000, risk_agent=CryptoRiskManagerAgent(), model=_FixedConvictionModel(0.9)
    )

    assert debate.conviction == 0.0  # model's conviction is ignored; not enough history to trust it
    assert risk.action == "HOLD"
