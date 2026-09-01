import os
from concurrent.futures import ThreadPoolExecutor

from models.schemas import TradeDecision

from agents.debate import DebateAgent
from agents.execution import ExecutionAgent
from agents.fundamental import FundamentalAgent
from agents.market_regime import MarketRegimeAgent
from agents.news_catalyst import NewsCatalystAgent
from agents.risk_manager import RiskManagerAgent
from agents.sentiment import SentimentAgent
from agents.technical import TechnicalAgent


class Orchestrator:
    """Coordinates the full agent pipeline for one ticker:

    News/Technical/Fundamental (parallel) -> Sentiment + Market Regime (parallel)
    -> Bull/Bear Debate -> Risk Manager -> Execution (Robinhood MCP, dry-run by default).

    Account equity for position sizing is resolved in order: an explicit
    ``account_equity`` argument, then live equity from the Robinhood MCP server
    (only queried when live trading is configured), then ``DEFAULT_ACCOUNT_EQUITY``.
    """

    def __init__(self):
        self.news_agent = NewsCatalystAgent()
        self.technical_agent = TechnicalAgent()
        self.fundamental_agent = FundamentalAgent()
        self.sentiment_agent = SentimentAgent()
        self.regime_agent = MarketRegimeAgent()
        self.debate_agent = DebateAgent()
        self.risk_agent = RiskManagerAgent()
        self.execution_agent = ExecutionAgent()

    def run(self, ticker: str, account_equity: float = None) -> TradeDecision:
        if account_equity is None:
            account_equity = self.execution_agent.get_account_equity()
        if account_equity is None:
            account_equity = float(os.environ.get("DEFAULT_ACCOUNT_EQUITY", "10000"))

        with ThreadPoolExecutor(max_workers=3) as pool:
            news_future = pool.submit(self.news_agent.run, ticker)
            technical_future = pool.submit(self.technical_agent.run, ticker)
            fundamental_future = pool.submit(self.fundamental_agent.run, ticker)
            news = news_future.result()
            technical = technical_future.result()
            fundamental = fundamental_future.result()

        with ThreadPoolExecutor(max_workers=2) as pool:
            sentiment_future = pool.submit(self.sentiment_agent.run, ticker, news)
            regime_future = pool.submit(self.regime_agent.run)
            sentiment = sentiment_future.result()
            regime = regime_future.result()

        debate = self.debate_agent.run(ticker, news, technical, fundamental, sentiment, regime)
        risk = self.risk_agent.run(debate, technical, account_equity)
        execution = self.execution_agent.run(ticker, risk)

        return TradeDecision(
            ticker=ticker,
            news=news,
            technical=technical,
            fundamental=fundamental,
            sentiment=sentiment,
            regime=regime,
            debate=debate,
            risk=risk,
            execution=execution,
        )
