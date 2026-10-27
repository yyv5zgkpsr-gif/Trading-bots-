"""Nets a technical score into a conviction and direction for crypto.

Crypto trades 24/7 and this repo has no news/fundamental/sentiment pipeline
or SPY/VIX-style regime check for it — so conviction here is the technical
score alone. Simpler than agents/debate.py's blend on purpose, not an
oversight: there is nothing else reproducible to blend in yet.
"""

from models.schemas import DebateResult, Direction, TechnicalReport

from agents.base import Agent
from agents.debate import CONVICTION_THRESHOLD


class CryptoDebateAgent(Agent):
    name = "crypto_debate"

    def run(self, symbol: str, technical: TechnicalReport) -> DebateResult:
        conviction = technical.technical_score

        if conviction > CONVICTION_THRESHOLD:
            recommendation = Direction.BULLISH
        elif conviction < -CONVICTION_THRESHOLD:
            recommendation = Direction.BEARISH
        else:
            recommendation = Direction.NEUTRAL

        thesis = (
            f"{symbol}: technical score {technical.technical_score} ({technical.summary}). "
            "No news/fundamental/sentiment/regime input yet for crypto."
        )

        return DebateResult(
            bull_thesis=thesis,
            bear_thesis=thesis,
            conviction=round(conviction, 3),
            recommendation=recommendation,
        )
