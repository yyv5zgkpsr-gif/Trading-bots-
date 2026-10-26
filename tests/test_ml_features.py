import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS, build_feature_frame


def _synthetic_ohlc(n: int, seed: int = 0, drift: float = 0.0005, vol: float = 0.01, start_price: float = 30_000.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    index = pd.date_range("2022-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close}, index=index)


def test_build_feature_frame_has_every_declared_column():
    price_history = _synthetic_ohlc(200)

    features = build_feature_frame(price_history)

    assert list(features.columns) == FEATURE_COLUMNS
    assert len(features) == len(price_history)


def test_early_rows_are_nan_until_sma50_warmup_and_later_rows_are_not():
    price_history = _synthetic_ohlc(200)

    features = build_feature_frame(price_history)

    assert features.iloc[0]["price_vs_sma50"] is not None and pd.isna(features.iloc[0]["price_vs_sma50"])
    assert features.iloc[48].isna().any()  # SMA50 not ready yet
    assert features.iloc[60:].notna().all(axis=None)


def test_rsi_feature_stays_within_its_valid_0_100_range():
    price_history = _synthetic_ohlc(200)

    features = build_feature_frame(price_history)

    valid_rsi = features["rsi"].dropna()
    assert (valid_rsi >= 0).all()
    assert (valid_rsi <= 100).all()


def test_a_steady_uptrend_produces_positive_momentum_features():
    n = 200
    close = np.linspace(30_000, 45_000, n)  # a plain array, not a Series, so it isn't reindexed against `index` below
    price_history = pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close},
        index=pd.date_range("2022-01-01", periods=n, freq="D"),
    )

    features = build_feature_frame(price_history)
    last = features.iloc[-1]

    assert last["return_20d"] > 0
    assert last["price_vs_sma50"] > 0
    assert last["price_vs_low20"] > 0
