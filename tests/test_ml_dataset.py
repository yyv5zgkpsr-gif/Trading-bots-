import numpy as np
import pandas as pd
import pytest

from ml.dataset import build_dataset, chronological_split


def _trend_ohlc(n: int, start: float, end: float) -> pd.DataFrame:
    close = np.linspace(start, end, n)  # a plain array, not a Series, so it isn't reindexed against `index` below
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close},
        index=pd.date_range("2022-01-01", periods=n, freq="D"),
    )


def test_build_dataset_labels_a_strong_uptrend_as_mostly_buy():
    price_history = _trend_ohlc(200, 30_000, 60_000)  # +100% over the whole series

    X, y = build_dataset(price_history, horizon=5, threshold=0.02)

    assert len(X) == len(y)
    assert len(X) > 0
    assert (y == 1).sum() > (y == -1).sum()  # dominated by BUY labels, not SELL


def test_build_dataset_labels_a_strong_downtrend_as_mostly_sell():
    price_history = _trend_ohlc(200, 60_000, 30_000)  # -50% over the whole series

    X, y = build_dataset(price_history, horizon=5, threshold=0.02)

    assert (y == -1).sum() > (y == 1).sum()


def test_build_dataset_labels_a_flat_series_as_hold():
    n = 200
    price_history = _trend_ohlc(n, 30_000, 30_000)

    X, y = build_dataset(price_history, horizon=5, threshold=0.02)

    assert (y == 0).all()


def test_build_dataset_drops_warmup_and_final_horizon_rows():
    n = 200
    horizon = 5
    price_history = _trend_ohlc(n, 30_000, 45_000)

    X, y = build_dataset(price_history, horizon=horizon, threshold=0.02)

    # last `horizon` rows of price_history can never be labeled (no future close yet)
    assert X.index[-1] <= price_history.index[-1 - horizon]
    # no NaNs survive into the returned dataset
    assert not X.isna().any(axis=None)
    assert not y.isna().any()


def test_chronological_split_divides_in_time_order_with_no_overlap():
    train, val, test = chronological_split(100, train_frac=0.6, val_frac=0.2)

    assert train == slice(0, 60)
    assert val == slice(60, 80)
    assert test == slice(80, 100)

    indices = list(range(100))
    assert indices[train] + indices[val] + indices[test] == indices  # covers everything, in order, no gaps


@pytest.mark.parametrize("train_frac,val_frac", [(0.0, 0.2), (1.0, 0.0), (0.6, 0.5), (0.5, 0.5)])
def test_chronological_split_rejects_invalid_fractions(train_frac, val_frac):
    with pytest.raises(ValueError):
        chronological_split(100, train_frac=train_frac, val_frac=val_frac)
