import numpy as np
import pandas as pd
import pytest

from backtest.runner import run_backtest


def _synthetic_ohlc(n: int, seed: int = 0, drift: float = 0.0003, vol: float = 0.01, start_price: float = 100.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    index = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close}, index=index)


def test_run_backtest_produces_metrics_without_any_network_call():
    n = 300
    price_history = _synthetic_ohlc(n, seed=1)
    spy_history = _synthetic_ohlc(n, seed=2, drift=0.0002)
    vix_history = pd.DataFrame(
        {"Close": np.random.default_rng(3).uniform(12, 25, n)}, index=price_history.index
    )

    portfolio, metrics = run_backtest(
        "AAPL",
        starting_cash=10_000,
        price_history=price_history,
        spy_history=spy_history,
        vix_history=vix_history,
    )

    assert len(portfolio.equity_curve) == n - 50  # one mark per day after the SMA50 warmup
    assert metrics.ending_equity > 0
    assert metrics.starting_cash == 10_000
    assert isinstance(metrics.num_trades, int)
    assert metrics.num_trades >= 0


def test_run_backtest_rejects_too_short_a_history():
    short_history = _synthetic_ohlc(40)

    with pytest.raises(ValueError, match="more than"):
        run_backtest("AAPL", price_history=short_history, spy_history=short_history, vix_history=short_history)


def test_run_backtest_is_deterministic_for_the_same_input():
    price_history = _synthetic_ohlc(200, seed=42)
    spy_history = _synthetic_ohlc(200, seed=43)
    vix_history = pd.DataFrame({"Close": [18.0] * 200}, index=price_history.index)

    _p1, metrics1 = run_backtest(
        "AAPL", starting_cash=10_000, price_history=price_history, spy_history=spy_history, vix_history=vix_history
    )
    _p2, metrics2 = run_backtest(
        "AAPL", starting_cash=10_000, price_history=price_history, spy_history=spy_history, vix_history=vix_history
    )

    assert metrics1 == metrics2
