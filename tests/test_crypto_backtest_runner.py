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


def test_run_crypto_backtest_uses_a_custom_decide_fn_when_given_one(monkeypatch):
    """ml/evaluate.py relies on swapping in a different decide_fn (the
    ML-backed one) through the exact same loop; lock in that the override
    is actually used instead of the default rule-based decide()."""
    price_history = _synthetic_ohlc(300, seed=1)
    calls = []

    def fake_decide(symbol, price_history_slice, equity, risk_agent):
        calls.append(symbol)
        from models.schemas import CryptoRiskDecision, DebateResult, Direction

        debate = DebateResult(bull_thesis="stub", bear_thesis="stub", conviction=0.0, recommendation=Direction.NEUTRAL)
        risk = CryptoRiskDecision(
            approved=False,
            action="HOLD",
            position_size_usd=0.0,
            position_size_quantity=0.0,
            stop_loss_price=None,
            take_profit_price=None,
            reasoning="stub always holds",
        )
        return risk, debate

    portfolio, _metrics = run_crypto_backtest(
        "BTC", starting_cash=10_000, price_history=price_history, decide_fn=fake_decide
    )

    assert len(calls) > 0
    assert portfolio.trades == []  # the stub decide_fn never approves a trade
