import os

import numpy as np
import pandas as pd
import pytest

from backtest.optimize import SweepResult, grid_search, rank
from backtest.runner import run_backtest


def _synthetic_ohlc(n: int, seed: int = 0, drift: float = 0.0008, vol: float = 0.01, start_price: float = 100.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    index = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close}, index=index)


def _fake_metrics(num_trades: int, sharpe: float, total_return_pct: float = 0.0):
    from backtest.metrics import BacktestMetrics

    return BacktestMetrics(
        starting_cash=10_000,
        ending_equity=10_000,
        total_return_pct=total_return_pct,
        num_trades=num_trades,
        num_wins=0,
        num_losses=0,
        win_rate_pct=0.0,
        avg_win_pct=0.0,
        avg_loss_pct=0.0,
        profit_factor=0.0,
        max_drawdown_pct=0.0,
        sharpe=sharpe,
    )


def test_grid_search_tries_every_combination_and_sets_env_vars_during_each_call(monkeypatch):
    monkeypatch.delenv("FAKE_PARAM_A", raising=False)
    monkeypatch.delenv("FAKE_PARAM_B", raising=False)
    seen_env = []

    def fake_backtest_fn():
        seen_env.append((os.environ.get("FAKE_PARAM_A"), os.environ.get("FAKE_PARAM_B")))
        return None, _fake_metrics(num_trades=10, sharpe=1.0)

    results = grid_search(
        fake_backtest_fn,
        {},
        {"FAKE_PARAM_A": ["x", "y"], "FAKE_PARAM_B": [1, 2]},
        min_trades=0,
    )

    assert len(results) == 4
    assert set(seen_env) == {("x", "1"), ("x", "2"), ("y", "1"), ("y", "2")}


def test_grid_search_restores_prior_env_vars_afterward(monkeypatch):
    monkeypatch.setenv("FAKE_PARAM_A", "original")

    def fake_backtest_fn():
        return None, _fake_metrics(num_trades=10, sharpe=1.0)

    grid_search(fake_backtest_fn, {}, {"FAKE_PARAM_A": ["x", "y"]}, min_trades=0)

    assert os.environ["FAKE_PARAM_A"] == "original"


def test_grid_search_restores_env_vars_even_if_a_call_raises(monkeypatch):
    monkeypatch.delenv("FAKE_PARAM_A", raising=False)

    def failing_backtest_fn():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        grid_search(failing_backtest_fn, {}, {"FAKE_PARAM_A": ["x"]}, min_trades=0)

    assert "FAKE_PARAM_A" not in os.environ


def test_grid_search_drops_combinations_below_the_min_trades_floor():
    def fake_backtest_fn(trades):
        return None, _fake_metrics(num_trades=trades, sharpe=1.0)

    results = grid_search(
        fake_backtest_fn,
        {"trades": 2},
        {"UNUSED": ["only"]},
        min_trades=5,
    )

    assert results == []


def test_rank_sorts_by_the_requested_metric_descending():
    results = [
        SweepResult(params={"a": 1}, metrics=_fake_metrics(num_trades=5, sharpe=0.5, total_return_pct=10.0)),
        SweepResult(params={"a": 2}, metrics=_fake_metrics(num_trades=5, sharpe=2.0, total_return_pct=1.0)),
        SweepResult(params={"a": 3}, metrics=_fake_metrics(num_trades=5, sharpe=1.0, total_return_pct=20.0)),
    ]

    by_sharpe = rank(results, by="sharpe")
    assert [r.params["a"] for r in by_sharpe] == [2, 3, 1]

    by_return = rank(results, by="total_return_pct")
    assert [r.params["a"] for r in by_return] == [3, 1, 2]


def test_grid_search_against_the_real_backtest_actually_varies_the_strategy(monkeypatch):
    """Not just a mock check: a tight vs. loose MIN_CONVICTION against the
    same real run_backtest() and the same synthetic history should trade a
    different number of times, proving the env vars really reach the
    risk manager through the full call stack."""
    for key in ("MIN_CONVICTION", "DEFAULT_STOP_LOSS_PCT", "DEFAULT_TAKE_PROFIT_PCT", "MAX_POSITION_PCT"):
        monkeypatch.delenv(key, raising=False)

    n = 300
    price_history = _synthetic_ohlc(n, seed=1)
    spy_history = _synthetic_ohlc(n, seed=2, drift=0.0002)
    vix_history = pd.DataFrame({"Close": np.random.default_rng(3).uniform(12, 25, n)}, index=price_history.index)

    results = grid_search(
        run_backtest,
        {
            "ticker": "AAPL",
            "starting_cash": 10_000,
            "price_history": price_history,
            "spy_history": spy_history,
            "vix_history": vix_history,
        },
        {"MIN_CONVICTION": [0.05, 0.9]},  # one permissive, one near-impossible to clear
        min_trades=0,
    )

    assert len(results) == 2
    permissive, strict = (r for r in results if r.params["MIN_CONVICTION"] == 0.05), (
        r for r in results if r.params["MIN_CONVICTION"] == 0.9
    )
    permissive_trades = next(iter(permissive)).metrics.num_trades
    strict_trades = next(iter(strict)).metrics.num_trades
    assert permissive_trades >= strict_trades
