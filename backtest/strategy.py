"""The backtest-safe slice of the live decision pipeline.

What this validates: technical score (RSI/MACD/trend, from
agents/technical.py) + market regime (SPY trend/VIX, from
agents/market_regime.py) -> conviction -> RiskManagerAgent sizing. This
reuses the exact same functions/class the live orchestrator calls — not a
reimplementation — so tuning MIN_CONVICTION/MAX_POSITION_PCT/stop/target
against backtest results is tuning the real thing.

What this deliberately leaves out, and why: news/fundamental/sentiment and
the LLM-driven bull/bear debate (agents/news_catalyst.py,
agents/fundamental.py, agents/sentiment.py, agents/debate.py) are not
reproducible as of a past date — today's headlines aren't yesterday's, and
nobody wants (or can afford) one Anthropic call per symbol per historical
day. So this is a backtest of the technical+regime+risk-manager slice of the
strategy, not the full live pipeline. Live performance will differ — the
live pipeline sees more (and sometimes contradictory) signal than this does.
"""

import pandas as pd

from agents.debate import CONVICTION_THRESHOLD
from agents.market_regime import regime_report_from_history
from agents.risk_manager import RiskManagerAgent
from agents.technical import technical_report_from_history
from models.schemas import DebateResult, Direction, RiskDecision


def decide(
    ticker: str,
    price_history: pd.DataFrame,
    spy_history: pd.DataFrame,
    vix_history: pd.DataFrame,
    account_equity: float,
    risk_agent: RiskManagerAgent,
) -> tuple[RiskDecision, DebateResult]:
    """One day's decision, using only data through the end of the given
    (already-sliced) history — callers must slice before calling this to
    avoid lookahead bias; this function never fetches or looks ahead itself.
    """
    technical = technical_report_from_history(ticker, price_history)
    regime = regime_report_from_history(spy_history, vix_history)

    # technical is the only signal available historically, so it gets the full
    # weight (agents/debate.py would normally blend it with news/fundamental/
    # sentiment at 0.3 of the total). Same regime nudge agents/debate.py uses.
    conviction = technical.technical_score
    if regime.regime.value == "bear":
        conviction -= 0.15
    elif regime.regime.value == "bull":
        conviction += 0.1
    conviction = max(-1.0, min(1.0, conviction))

    if conviction > CONVICTION_THRESHOLD:
        recommendation = Direction.BULLISH
    elif conviction < -CONVICTION_THRESHOLD:
        recommendation = Direction.BEARISH
    else:
        recommendation = Direction.NEUTRAL

    debate = DebateResult(
        bull_thesis="(backtest: technical + regime only, no news/fundamental/sentiment/LLM)",
        bear_thesis="(backtest: technical + regime only, no news/fundamental/sentiment/LLM)",
        conviction=round(conviction, 3),
        recommendation=recommendation,
    )

    risk = risk_agent.run(debate, technical, account_equity)
    return risk, debate
