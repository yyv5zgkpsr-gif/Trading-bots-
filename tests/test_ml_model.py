import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS
from ml.model import DirectionModel


def _separable_dataset(n: int = 200):
    """A feature matrix where one column alone perfectly determines the
    label, so a fitted model's predictions are trivially checkable."""
    rng = np.random.default_rng(0)
    X = pd.DataFrame({col: rng.normal(size=n) for col in FEATURE_COLUMNS})
    y = pd.Series(np.where(X["rsi"] > 0, 1, -1), index=X.index)
    return X, y


def test_fit_and_predict_conviction_recovers_a_trivially_separable_signal():
    X, y = _separable_dataset()
    model = DirectionModel()

    model.fit(X, y)
    conviction = model.predict_conviction(X)

    assert (conviction[X["rsi"] > 0] > 0).mean() > 0.9
    assert (conviction[X["rsi"] < 0] < 0).mean() > 0.9


def test_predict_conviction_stays_within_minus_one_to_one():
    X, y = _separable_dataset()
    model = DirectionModel()
    model.fit(X, y)

    conviction = model.predict_conviction(X)

    assert (conviction >= -1).all()
    assert (conviction <= 1).all()


def test_predict_conviction_handles_a_class_never_seen_in_training():
    X = pd.DataFrame({col: np.zeros(20) for col in FEATURE_COLUMNS})
    y = pd.Series([0] * 20)  # model only ever sees HOLD during training
    model = DirectionModel()
    model.fit(X, y)

    conviction = model.predict_conviction(X)

    assert (conviction == 0).all()


def test_save_and_load_round_trips_predictions(tmp_path):
    X, y = _separable_dataset()
    model = DirectionModel()
    model.fit(X, y)
    before = model.predict_conviction(X)

    path = tmp_path / "model.joblib"
    model.save(path)
    loaded = DirectionModel.load(path)
    after = loaded.predict_conviction(X)

    pd.testing.assert_series_equal(before, after)
    assert loaded.feature_columns == model.feature_columns
