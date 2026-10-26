import json

import numpy as np
import pandas as pd
import pytest

import agents.ml_crypto_debate as ml_crypto_debate
from agents.ml_crypto_debate import MLCryptoDebateAgent, ModelNotReadyError
from ml.features import FEATURE_COLUMNS
from ml.model import DirectionModel
from models.schemas import Direction, TechnicalReport


def _technical_stub():
    return TechnicalReport(
        ticker="BTC",
        trend=Direction.BULLISH,
        rsi=60.0,
        macd=1.0,
        macd_signal=0.5,
        support=50_000.0,
        resistance=70_000.0,
        last_price=60_000.0,
        technical_score=0.4,
        summary="stub",
    )


def _save_model(path, conviction_label=1):
    X = pd.DataFrame({col: np.zeros(20) for col in FEATURE_COLUMNS})
    y = pd.Series([conviction_label] * 20)
    model = DirectionModel()
    model.fit(X, y)
    model.save(path)
    return model


def _synthetic_price_history(n: int = 200):
    close = np.linspace(50_000, 60_000, n)  # a plain array, not a Series, so it isn't reindexed against `index` below
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close},
        index=pd.date_range("2022-01-01", periods=n, freq="D"),
    )


def test_run_raises_when_the_model_file_does_not_exist(tmp_path):
    agent = MLCryptoDebateAgent(model_dir=tmp_path)

    with pytest.raises(ModelNotReadyError, match="does not exist"):
        agent.run("BTC", _technical_stub())


def test_run_raises_when_metadata_file_is_missing(tmp_path):
    _save_model(tmp_path / "btc_direction.joblib")
    # no btc_direction.json written

    agent = MLCryptoDebateAgent(model_dir=tmp_path)
    with pytest.raises(ModelNotReadyError, match="is missing"):
        agent.run("BTC", _technical_stub())


def test_run_raises_when_metadata_says_not_profitable(tmp_path):
    _save_model(tmp_path / "btc_direction.joblib")
    (tmp_path / "btc_direction.json").write_text(json.dumps({"profitable": False}))

    agent = MLCryptoDebateAgent(model_dir=tmp_path)
    with pytest.raises(ModelNotReadyError, match="did not judge it"):
        agent.run("BTC", _technical_stub())


def test_run_succeeds_and_predicts_when_metadata_says_profitable(tmp_path, monkeypatch):
    _save_model(tmp_path / "btc_direction.joblib", conviction_label=1)
    (tmp_path / "btc_direction.json").write_text(json.dumps({"profitable": True}))
    monkeypatch.setattr(ml_crypto_debate, "fetch_price_history", lambda symbol, period=None: _synthetic_price_history())

    agent = MLCryptoDebateAgent(model_dir=tmp_path)
    debate = agent.run("BTC", _technical_stub())

    assert debate.recommendation == Direction.BULLISH
    assert debate.conviction > 0


def test_model_is_loaded_only_once_per_symbol_across_multiple_runs(tmp_path, monkeypatch):
    _save_model(tmp_path / "btc_direction.joblib")
    (tmp_path / "btc_direction.json").write_text(json.dumps({"profitable": True}))
    monkeypatch.setattr(ml_crypto_debate, "fetch_price_history", lambda symbol, period=None: _synthetic_price_history())

    load_calls = []
    original_load = DirectionModel.load

    def counting_load(path):
        load_calls.append(path)
        return original_load(path)

    monkeypatch.setattr(DirectionModel, "load", staticmethod(counting_load))

    agent = MLCryptoDebateAgent(model_dir=tmp_path)
    agent.run("BTC", _technical_stub())
    agent.run("BTC", _technical_stub())

    assert len(load_calls) == 1
