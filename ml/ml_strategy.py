"""backtest/crypto_strategy.py's decide(), but conviction comes from a
trained DirectionModel instead of the raw technical score. Same risk
sizing (agents/crypto_risk_manager.py) and the same CONVICTION_THRESHOLD
gate, so backtesting this against the same history as
backtest/crypto_strategy.py's decide() is an apples-to-apples test of
whether the model adds anything over the rule-based technical score alone
(see ml/evaluate.py's evaluate_as_backtest).
"""

import pandas as pd

from agents.crypto_risk_manager import CryptoRiskManagerAgent
from agents.debate import CONVICTION_THRESHOLD
from agents.technical import technical_report_from_history
from ml.features import build_feature_frame
from ml.model import DirectionModel
from models.schemas import CryptoRiskDecision, DebateResult, Direction


def decide(
    symbol: str,
    price_history: pd.DataFrame,
    account_equity: float,
    risk_agent: CryptoRiskManagerAgent,
    model: DirectionModel,
) -> tuple[CryptoRiskDecision, DebateResult]:
    """One day's decision, using only data through the end of the given
    (already-sliced) history — callers must slice before calling this to
    avoid lookahead bias, same contract as backtest/crypto_strategy.py's
    decide()."""
    technical = technical_report_from_history(symbol, price_history)

    latest_features = build_feature_frame(price_history).iloc[[-1]]
    if latest_features.isna().any(axis=None):
        conviction = 0.0  # not enough history yet for every feature's warmup window
    else:
        conviction = float(model.predict_conviction(latest_features).iloc[0])

    if conviction > CONVICTION_THRESHOLD:
        recommendation = Direction.BULLISH
    elif conviction < -CONVICTION_THRESHOLD:
        recommendation = Direction.BEARISH
    else:
        recommendation = Direction.NEUTRAL

    debate = DebateResult(
        bull_thesis=f"(ML model conviction {round(conviction, 3)})",
        bear_thesis=f"(ML model conviction {round(conviction, 3)})",
        conviction=round(conviction, 3),
        recommendation=recommendation,
    )

    risk = risk_agent.run(debate, technical, account_equity)
    return risk, debate
