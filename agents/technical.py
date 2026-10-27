import pandas as pd

from data.market_data import compute_macd, compute_rsi, fetch_price_history, support_resistance
from models.schemas import Direction, TechnicalReport

from agents.base import Agent


def technical_report_from_history(ticker: str, df: pd.DataFrame) -> TechnicalReport:
    """Pure function: trend/RSI/MACD/support-resistance scoring from an OHLC
    DataFrame already in hand. Pulled out of TechnicalAgent.run so the exact
    same scoring logic can run against a live fetch (the agent) or a sliced
    historical window with no lookahead (backtest/strategy.py) — one
    implementation, not two copies to keep in sync."""
    close = df["Close"]

    rsi = compute_rsi(close)
    macd_line, signal_line = compute_macd(close)
    support, resistance = support_resistance(df)

    last_price = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else sma20
    last_rsi = float(rsi.iloc[-1])
    last_macd = float(macd_line.iloc[-1])
    last_signal = float(signal_line.iloc[-1])

    if last_price > sma20 > sma50:
        trend = Direction.BULLISH
    elif last_price < sma20 < sma50:
        trend = Direction.BEARISH
    else:
        trend = Direction.NEUTRAL

    score = 0.0
    score += 0.4 if trend == Direction.BULLISH else (-0.4 if trend == Direction.BEARISH else 0.0)
    score += 0.3 if last_macd > last_signal else -0.3
    if last_rsi > 70:
        score -= 0.2
    elif last_rsi < 30:
        score += 0.2
    score = max(-1.0, min(1.0, score))

    summary = (
        f"{ticker}: trend={trend.value}, RSI={last_rsi:.1f}, "
        f"MACD {'above' if last_macd > last_signal else 'below'} signal, "
        f"price {last_price:.2f} vs support {support:.2f} / resistance {resistance:.2f}."
    )

    return TechnicalReport(
        ticker=ticker,
        trend=trend,
        rsi=round(last_rsi, 2),
        macd=round(last_macd, 4),
        macd_signal=round(last_signal, 4),
        support=round(support, 2),
        resistance=round(resistance, 2),
        last_price=round(last_price, 2),
        technical_score=round(score, 3),
        summary=summary,
    )


class TechnicalAgent(Agent):
    """Trend, momentum oscillators, and support/resistance for a single ticker."""

    name = "technical"

    def run(self, ticker: str) -> TechnicalReport:
        df = fetch_price_history(ticker)
        return technical_report_from_history(ticker, df)
