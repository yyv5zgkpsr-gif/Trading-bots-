from data.fundamentals_data import fetch_fundamentals
from data.news_data import fetch_news_headlines, fetch_sec_filings
from models.schemas import NewsReport

from agents.base import Agent

POSITIVE_WORDS = {"beats", "surge", "upgrade", "record", "growth", "approval", "partnership", "buyback"}
NEGATIVE_WORDS = {"miss", "lawsuit", "downgrade", "investigation", "recall", "layoff", "plunge", "fraud"}


class NewsCatalystAgent(Agent):
    """Breaking news, SEC filing events, and headline-derived catalyst scoring."""

    name = "news_catalyst"

    def run(self, ticker: str) -> NewsReport:
        try:
            company = fetch_fundamentals(ticker).get("short_name", ticker)
        except Exception:
            company = ticker

        headlines = fetch_news_headlines(ticker, company_name=company)
        filings = fetch_sec_filings(ticker)

        score = 0.0
        for headline in headlines:
            title = headline["title"].lower()
            score += sum(1 for w in POSITIVE_WORDS if w in title) * 0.15
            score -= sum(1 for w in NEGATIVE_WORDS if w in title) * 0.15
        score = max(-1.0, min(1.0, score))

        catalysts = [f["title"] for f in filings if f.get("title")]
        summary = f"{len(headlines)} recent headlines, {len(filings)} recent SEC 8-K filings."

        llm_input = "\n".join(h["title"] for h in headlines[:10])
        llm_summary = self.ask_llm(
            system=(
                "You are a market catalyst analyst. Summarize the key catalysts in 2-3 "
                "sentences and note whether the tone is positive, negative, or mixed."
            ),
            user=f"Recent headlines for {ticker} ({company}):\n{llm_input}\n\nRecent SEC 8-K filings: {catalysts}",
        )
        if llm_summary:
            summary = llm_summary.strip()

        return NewsReport(
            ticker=ticker,
            headlines=[h["title"] for h in headlines],
            catalysts=catalysts,
            catalyst_score=round(score, 3),
            summary=summary,
        )
