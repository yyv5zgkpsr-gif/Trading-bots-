from data.market_data import fetch_price_history
from models.schemas import NewsReport, SentimentReport

from agents.base import Agent


class SentimentAgent(Agent):
    """Blends price momentum with news-derived tone into a single sentiment score."""

    name = "sentiment"

    def run(self, ticker: str, news_report: NewsReport = None) -> SentimentReport:
        df = fetch_price_history(ticker, period="2mo")
        close = df["Close"]

        momentum_5d = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if len(close) > 6 else 0.0
        momentum_20d = float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if len(close) > 21 else 0.0

        news_score = news_report.catalyst_score if news_report else 0.0
        momentum_score = max(-1.0, min(1.0, (momentum_5d / 10) + (momentum_20d / 20)))
        sentiment_score = round((news_score * 0.6) + (momentum_score * 0.4), 3)

        summary = (
            f"{ticker}: 5d momentum {momentum_5d:.1f}%, 20d momentum {momentum_20d:.1f}%, "
            f"news-derived sentiment {news_score:.2f}."
        )

        return SentimentReport(
            ticker=ticker,
            sentiment_score=sentiment_score,
            momentum_5d=round(momentum_5d, 2),
            momentum_20d=round(momentum_20d, 2),
            summary=summary,
        )
