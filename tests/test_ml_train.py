import numpy as np
import pandas as pd

from backtest.metrics import BacktestMetrics
from ml.dataset import build_dataset
from ml.train import MIN_TRADES_TO_JUDGE, is_profitable, train_and_evaluate


def _fake_metrics(num_trades: int, total_return_pct: float) -> BacktestMetrics:
    return BacktestMetrics(
        starting_cash=10_000,
        ending_equity=10_000 * (1 + total_return_pct / 100),
        total_return_pct=total_return_pct,
        num_trades=num_trades,
        num_wins=0,
        num_losses=0,
        win_rate_pct=0.0,
        avg_win_pct=0.0,
        avg_loss_pct=0.0,
        profit_factor=0.0,
        max_drawdown_pct=0.0,
        sharpe=0.0,
    )


def _result(val_trades, val_return, test_trades, test_return):
    return {
        "val_backtest_metrics": _fake_metrics(val_trades, val_return),
        "test_backtest_metrics": _fake_metrics(test_trades, test_return),
    }


def test_is_profitable_requires_positive_return_on_both_folds():
    assert is_profitable(_result(MIN_TRADES_TO_JUDGE, 5.0, MIN_TRADES_TO_JUDGE, 5.0)) is True
    assert is_profitable(_result(MIN_TRADES_TO_JUDGE, -5.0, MIN_TRADES_TO_JUDGE, 5.0)) is False
    assert is_profitable(_result(MIN_TRADES_TO_JUDGE, 5.0, MIN_TRADES_TO_JUDGE, -5.0)) is False


def test_is_profitable_requires_enough_trades_to_not_be_noise():
    assert is_profitable(_result(MIN_TRADES_TO_JUDGE - 1, 50.0, MIN_TRADES_TO_JUDGE, 50.0)) is False
    assert is_profitable(_result(MIN_TRADES_TO_JUDGE, 50.0, MIN_TRADES_TO_JUDGE - 1, 50.0)) is False


def test_is_profitable_false_when_a_fold_was_never_evaluated():
    assert is_profitable({"val_backtest_metrics": None, "test_backtest_metrics": _fake_metrics(5, 5.0)}) is False


def _synthetic_ohlc(n: int, seed: int, drift: float, vol: float = 0.012, start_price: float = 30_000.0):
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    close = start_price * np.cumprod(1 + returns)
    high = close * (1 + np.abs(rng.normal(0, 0.003, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.003, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    index = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close}, index=index)


def test_train_and_evaluate_runs_end_to_end_on_synthetic_history():
    price_history = _synthetic_ohlc(900, seed=1, drift=0.0006)
    X, _y = build_dataset(price_history, horizon=5, threshold=0.02)

    result = train_and_evaluate("BTC", price_history, horizon=5, threshold=0.02, train_frac=0.6, val_frac=0.2)

    assert result["n_train"] + result["n_val"] + result["n_test"] == len(X)
    assert result["n_train"] > result["n_val"] > 0
    assert result["n_test"] > 0
    assert result["val_backtest_metrics"] is not None
    assert result["test_backtest_metrics"] is not None
    assert result["val_classifier_metrics"]["n_samples"] == result["n_val"]
    assert result["test_classifier_metrics"]["n_samples"] == result["n_test"]
    # the saved model itself is directly usable for prediction
    conviction = result["model"].predict_conviction(X)
    assert conviction.between(-1, 1).all()
