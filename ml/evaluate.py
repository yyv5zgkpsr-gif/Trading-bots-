"""Two ways to judge a trained DirectionModel, from least to most relevant:
classifier metrics (did it predict the right label) and a full backtest
(did following its conviction signal actually make money). The backtest
is what should gate a deploy decision, not accuracy alone — a model can
look accurate by predicting HOLD on a mostly-flat series and still be
useless for trading.
"""

from functools import partial

import pandas as pd
from sklearn.metrics import classification_report

from backtest.crypto_runner import run_crypto_backtest
from backtest.metrics import BacktestMetrics
from ml.ml_strategy import decide as ml_decide
from ml.model import DirectionModel


def evaluate_classifier(model: DirectionModel, X: pd.DataFrame, y: pd.Series) -> dict:
    predicted_conviction = model.predict_conviction(X)
    predicted_label = predicted_conviction.apply(lambda c: 1 if c > 0 else (-1 if c < 0 else 0))
    report = classification_report(y, predicted_label, labels=[1, 0, -1], output_dict=True, zero_division=0)

    moved = y != 0
    directional_accuracy = float((predicted_label[moved] == y[moved]).mean()) if moved.any() else None

    return {
        "classification_report": report,
        "directional_accuracy_when_price_moved": directional_accuracy,
        "n_samples": len(y),
    }


def evaluate_as_backtest(
    symbol: str,
    model: DirectionModel,
    price_history: pd.DataFrame,
    starting_cash: float = 10_000.0,
) -> BacktestMetrics:
    """Runs the exact same day-by-day, no-lookahead backtest loop as
    `python -m backtest.crypto_runner`, with the model's conviction
    standing in for the rule-based technical score — same risk sizing,
    same execution, so the only difference from the rule-based backtest
    is where conviction comes from."""
    _portfolio, metrics = run_crypto_backtest(
        symbol,
        starting_cash=starting_cash,
        price_history=price_history,
        decide_fn=partial(ml_decide, model=model),
    )
    return metrics
