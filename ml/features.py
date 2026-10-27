"""Feature engineering for the ML direction model: one row per day, built
only from data available through that day's close (no lookahead) — the
same discipline backtest/crypto_runner.py's day-by-day loop uses, just
computed for every day at once instead of one slice at a time.

Shared by training (ml/train.py) and live inference
(agents/ml_crypto_debate.py) so both see identical features; the only
difference is which rows get used (every valid row during training vs.
just the latest row live).
"""

import pandas as pd

from data.market_data import compute_macd, compute_rsi

FEATURE_COLUMNS = [
    "rsi",
    "macd_hist",
    "price_vs_sma20",
    "price_vs_sma50",
    "sma20_vs_sma50",
    "return_1d",
    "return_5d",
    "return_10d",
    "return_20d",
    "volatility_20d",
    "price_vs_low20",
    "price_vs_high20",
]


def build_feature_frame(price_history: pd.DataFrame) -> pd.DataFrame:
    """Returns a DataFrame indexed like `price_history`, with FEATURE_COLUMNS
    as columns. Early rows are NaN until each feature's warmup window has
    enough history (SMA50 needs 50 prior rows) — callers drop those, same
    as backtest/crypto_runner.py's MIN_LOOKBACK_DAYS."""
    close = price_history["Close"]

    rsi = compute_rsi(close)
    macd_line, signal_line = compute_macd(close)
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    daily_return = close.pct_change()

    features = pd.DataFrame(index=price_history.index)
    features["rsi"] = rsi
    features["macd_hist"] = macd_line - signal_line
    features["price_vs_sma20"] = close / sma20 - 1
    features["price_vs_sma50"] = close / sma50 - 1
    features["sma20_vs_sma50"] = sma20 / sma50 - 1
    features["return_1d"] = close.pct_change(1)
    features["return_5d"] = close.pct_change(5)
    features["return_10d"] = close.pct_change(10)
    features["return_20d"] = close.pct_change(20)
    features["volatility_20d"] = daily_return.rolling(20).std()
    features["price_vs_low20"] = close / price_history["Low"].rolling(20).min() - 1
    features["price_vs_high20"] = close / price_history["High"].rolling(20).max() - 1

    return features[FEATURE_COLUMNS]
