from models.schemas import (
    DebateResult,
    Direction,
    FundamentalReport,
    MarketRegimeReport,
    NewsReport,
    SentimentReport,
    TechnicalReport,
)

from agents.base import Agent

# Relative weight each upstream report contributes to the numeric conviction score.
WEIGHTS = {"news": 0.2, "technical": 0.3, "fundamental": 0.25, "sentiment": 0.25}
CONVICTION_THRESHOLD = 0.15


class DebateAgent(Agent):
    """Runs an adversarial bull-vs-bear debate, then nets the evidence into a
    single conviction score and directional recommendation for the risk manager."""

    name = "debate"

    def run(
        self,
        ticker: str,
        news: NewsReport,
        technical: TechnicalReport,
        fundamental: FundamentalReport,
        sentiment: SentimentReport,
        regime: MarketRegimeReport,
    ) -> DebateResult:
        context = (
            f"Ticker: {ticker}\n"
            f"News/Catalysts: {news.summary} (score {news.catalyst_score})\n"
            f"Technical: {technical.summary} (score {technical.technical_score})\n"
            f"Fundamental: {fundamental.summary} (score {fundamental.fundamental_score})\n"
            f"Sentiment: {sentiment.summary} (score {sentiment.sentiment_score})\n"
            f"Market Regime: {regime.summary}\n"
        )

        bull_thesis = self.ask_llm(
            system=(
                "You are a BULL equity analyst. Build the strongest good-faith bull case in "
                "2-3 sentences using only the evidence given. Do not invent facts."
            ),
            user=context,
        ) or "LLM unavailable: bull case defaults to the positive signals in the evidence above."

        bear_thesis = self.ask_llm(
            system=(
                "You are a BEAR equity analyst. Build the strongest good-faith bear case in "
                "2-3 sentences using only the evidence given. Do not invent facts."
            ),
            user=context,
        ) or "LLM unavailable: bear case defaults to the negative signals in the evidence above."

        conviction = (
            news.catalyst_score * WEIGHTS["news"]
            + technical.technical_score * WEIGHTS["technical"]
            + fundamental.fundamental_score * WEIGHTS["fundamental"]
            + sentiment.sentiment_score * WEIGHTS["sentiment"]
        )
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

        return DebateResult(
            bull_thesis=bull_thesis.strip(),
            bear_thesis=bear_thesis.strip(),
            conviction=round(conviction, 3),
            recommendation=recommendation,
        )
