"""Technical analysis for crypto. Reuses agents/technical.py's RSI/MACD/trend
scoring unchanged — none of that math cares about asset class, only the
data-fetch side differs: Robinhood's crypto trading API uses a bare ticker
("BTC"), yfinance uses the Yahoo crypto convention ("BTC-USD").
"""

from data.market_data import fetch_price_history
from models.schemas import TechnicalReport

from agents.base import Agent
from agents.technical import technical_report_from_history


def to_yfinance_crypto_symbol(symbol: str) -> str:
    symbol = symbol.upper().strip()
    return symbol if symbol.endswith("-USD") else f"{symbol}-USD"


class CryptoTechnicalAgent(Agent):
    name = "crypto_technical"

    def run(self, symbol: str) -> TechnicalReport:
        df = fetch_price_history(to_yfinance_crypto_symbol(symbol), period="6mo")
        return technical_report_from_history(symbol, df)
