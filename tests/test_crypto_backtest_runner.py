import numpy as np
import pandas as pd
import pytest

from backtest.crypto_runner import run_crypto_backtest


def _synthetic_ohlc(n: int, seed: int = 0, drift: float = 0.0003, vol: float = 0.01, start_price: float = 30_000.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    index = pd.date_range("2022-01-01", periods=n, freq="D")  # crypto trades every day, not just business days
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close}, index=index)


def test_run_crypto_backtest_produces_metrics_without_any_network_call():
    n = 300
    price_history = _synthetic_ohlc(n, seed=1)

    portfolio, metrics = run_crypto_backtest("BTC", starting_cash=10_000, price_history=price_history)

    assert len(portfolio.equity_curve) == n - 50  # one mark per day after the SMA50 warmup
    assert metrics.ending_equity > 0
    assert metrics.starting_cash == 10_000
    assert isinstance(metrics.num_trades, int)
    assert metrics.num_trades >= 0


def test_run_crypto_backtest_rejects_too_short_a_history():
    short_history = _synthetic_ohlc(40)

    with pytest.raises(ValueError, match="more than"):
        run_crypto_backtest("BTC", price_history=short_history)


def test_run_crypto_backtest_is_deterministic_for_the_same_input():
    price_history = _synthetic_ohlc(200, seed=42)

    _p1, metrics1 = run_crypto_backtest("BTC", starting_cash=10_000, price_history=price_history)
    _p2, metrics2 = run_crypto_backtest("BTC", starting_cash=10_000, price_history=price_history)

    assert metrics1 == metrics2


def test_run_crypto_backtest_sizes_positions_in_fractional_quantities():
    price_history = _synthetic_ohlc(300, seed=7, drift=0.002)  # strong uptrend to force at least one buy

    portfolio, _metrics = run_crypto_backtest("BTC", starting_cash=10_000, price_history=price_history)

    assert portfolio.trades  # the strong uptrend should have triggered at least one trade
    # position sizing is USD-based (fraction of equity / price), so quantities are fractional BTC, not whole coins
    assert any(0 < t.quantity < 1 for t in portfolio.trades)
