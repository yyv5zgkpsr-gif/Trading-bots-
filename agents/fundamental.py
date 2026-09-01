from data.fundamentals_data import fetch_fundamentals
from models.schemas import FundamentalReport

from agents.base import Agent


class FundamentalAgent(Agent):
    """Valuation, growth, margin and leverage assessment for a single ticker."""

    name = "fundamental"

    def run(self, ticker: str) -> FundamentalReport:
        info = fetch_fundamentals(ticker)
        pe = info.get("pe_ratio")
        peg = info.get("peg_ratio")
        debt_to_equity = info.get("debt_to_equity")
        growth = info.get("revenue_growth")
        margin = info.get("profit_margin")

        score = 0.0
        if pe is not None:
            score += 0.25 if 0 < pe < 25 else (-0.15 if pe > 40 else 0.0)
        if growth is not None:
            score += 0.35 if growth > 0.1 else (-0.2 if growth < 0 else 0.0)
        if margin is not None:
            score += 0.2 if margin > 0.1 else (-0.1 if margin < 0 else 0.0)
        if debt_to_equity is not None:
            score += -0.2 if debt_to_equity > 200 else (0.1 if debt_to_equity < 50 else 0.0)
        score = max(-1.0, min(1.0, score))

        summary = (
            f"{ticker}: PE={pe}, PEG={peg}, Debt/Equity={debt_to_equity}, "
            f"RevenueGrowth={growth}, ProfitMargin={margin}."
        )

        llm_summary = self.ask_llm(
            system="You are a fundamental equity analyst. Be concise (2-3 sentences, no preamble).",
            user=f"Given these fundamentals for {ticker}: {info}, give a brief fundamental assessment.",
        )
        if llm_summary:
            summary = llm_summary.strip()

        return FundamentalReport(
            ticker=ticker,
            pe_ratio=pe,
            peg_ratio=peg,
            debt_to_equity=debt_to_equity,
            revenue_growth=growth,
            profit_margin=margin,
            fundamental_score=round(score, 3),
            summary=summary,
        )
