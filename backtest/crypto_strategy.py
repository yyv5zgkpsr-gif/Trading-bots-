"""The backtest-safe crypto decision: reuses agents/technical.py's scoring
and agents/crypto_risk_manager.py's sizing unchanged — the same functions/
class the live crypto pipeline calls, so tuning MIN_CONVICTION/
CRYPTO_MAX_POSITION_PCT/CRYPTO_STOP_LOSS_PCT/CRYPTO_TAKE_PROFIT_PCT against
backtest results is tuning the real thing.

No regime/news/fundamental/sentiment input — matches agents/crypto_debate.py
exactly. That pipeline is narrower than the stock one on purpose (crypto
trades 24/7; SPY/VIX don't mean anything for it, and no news/fundamental/
sentiment agent exists for crypto yet), so this backtest doesn't pretend to
validate more than the live pipeline actually does.
"""

import pandas as pd

from agents.crypto_risk_manager import CryptoRiskManagerAgent
from agents.debate import CONVICTION_THRESHOLD
from agents.technical import technical_report_from_history
from models.schemas import CryptoRiskDecision, DebateResult, Direction


def decide(
    symbol: str,
    price_history: pd.DataFrame,
    account_equity: float,
    risk_agent: CryptoRiskManagerAgent,
) -> tuple[CryptoRiskDecision, DebateResult]:
    """One day's decision, using only data through the end of the given
    (already-sliced) history — callers must slice before calling this to
    avoid lookahead bias; this function never fetches or looks ahead itself.
    """
    technical = technical_report_from_history(symbol, price_history)
    conviction = technical.technical_score

    if conviction > CONVICTION_THRESHOLD:
        recommendation = Direction.BULLISH
    elif conviction < -CONVICTION_THRESHOLD:
        recommendation = Direction.BEARISH
    else:
        recommendation = Direction.NEUTRAL

    debate = DebateResult(
        bull_thesis="(backtest: technical score only, matches agents/crypto_debate.py)",
        bear_thesis="(backtest: technical score only, matches agents/crypto_debate.py)",
        conviction=round(conviction, 3),
        recommendation=recommendation,
    )

    risk = risk_agent.run(debate, technical, account_equity)
    return risk, debate
