import numpy as np
import pandas as pd

from data.market_data import compute_macd, compute_rsi, support_resistance


def test_rsi_is_high_for_strictly_rising_series():
    close = pd.Series(np.linspace(100, 150, 40))
    rsi = compute_rsi(close, period=14)
    assert rsi.iloc[-1] > 70


def test_rsi_is_low_for_strictly_falling_series():
    close = pd.Series(np.linspace(150, 100, 40))
    rsi = compute_rsi(close, period=14)
    assert rsi.iloc[-1] < 30


def test_rsi_is_bounded_0_to_100():
    close = pd.Series(np.random.default_rng(0).normal(100, 5, 60).cumsum())
    rsi = compute_rsi(close)
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_macd_positive_when_trending_up():
    close = pd.Series(np.linspace(100, 200, 60))
    macd_line, signal_line = compute_macd(close)
    assert macd_line.iloc[-1] > 0
    assert macd_line.iloc[-1] > signal_line.iloc[-1]


def test_support_resistance_bounds_recent_window():
    df = pd.DataFrame(
        {
            "Low": [10, 9, 11, 8, 12] * 5,
            "High": [15, 16, 14, 17, 13] * 5,
        }
    )
    support, resistance = support_resistance(df, window=5)
    assert support == 8.0
    assert resistance == 17.0
