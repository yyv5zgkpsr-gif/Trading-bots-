"""Turns a feature frame into a labeled, chronologically-ordered training
set, and splits it in time order — never randomly, which would leak future
bars into the training fold and make validation/test numbers meaningless.
"""

import pandas as pd

from ml.features import build_feature_frame

DEFAULT_HORIZON_DAYS = 5
DEFAULT_LABEL_THRESHOLD = 0.02  # +/- 2% forward return over the horizon


def build_dataset(
    price_history: pd.DataFrame,
    horizon: int = DEFAULT_HORIZON_DAYS,
    threshold: float = DEFAULT_LABEL_THRESHOLD,
) -> tuple[pd.DataFrame, pd.Series]:
    """Label at day t is BUY (1) if the close `horizon` days later is up more
    than `threshold`, SELL (-1) if down more than `threshold`, else HOLD (0).

    Drops the warmup rows (features not ready yet) and the final `horizon`
    rows (no future close exists yet to label them with)."""
    features = build_feature_frame(price_history)
    close = price_history["Close"]
    forward_return = close.shift(-horizon) / close - 1

    label = pd.Series(0, index=price_history.index, dtype=int)
    label[forward_return > threshold] = 1
    label[forward_return < -threshold] = -1

    valid = features.notna().all(axis=1) & forward_return.notna()
    return features[valid], label[valid]


def chronological_split(n: int, train_frac: float = 0.6, val_frac: float = 0.2) -> tuple[slice, slice, slice]:
    """Splits `n` rows (already in time order) into train/val/test slices
    with no shuffling: train is the earliest `train_frac`, val the next
    `val_frac`, test is whatever's left — the most recent data, touched
    only once, after training and threshold-tuning are both finished."""
    if not (0 < train_frac < 1) or not (0 < val_frac < 1) or train_frac + val_frac >= 1:
        raise ValueError("train_frac and val_frac must each be in (0, 1) and sum to less than 1")
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n)
