import pandas as pd

from data.market_data import fetch_price_history
from models.schemas import Direction, MarketRegimeReport, Regime

from agents.base import Agent


def regime_report_from_history(spy_df: pd.DataFrame, vix_df: pd.DataFrame = None, rate_10y: float = None) -> MarketRegimeReport:
    """Pure function: SPY trend + VIX level scoring from history already in
    hand, with no network call. Lets backtest/strategy.py evaluate the market
    regime as of a historical date using a sliced window, with the exact same
    logic MarketRegimeAgent uses live."""
    spy_close = spy_df["Close"]
    sma50 = float(spy_close.rolling(50).mean().iloc[-1])
    last_spy = float(spy_close.iloc[-1])
    spy_trend = Direction.BULLISH if last_spy > sma50 else Direction.BEARISH

    volatility = float(vix_df["Close"].iloc[-1]) if vix_df is not None and not vix_df.empty else 20.0

    if spy_trend == Direction.BULLISH and volatility < 20:
        regime = Regime.BULL
    elif spy_trend == Direction.BEARISH and volatility > 25:
        regime = Regime.BEAR
    else:
        regime = Regime.SIDEWAYS

    summary = (
        f"Market regime: {regime.value}, SPY trend {spy_trend.value}, "
        f"VIX {volatility:.1f}" + (f", 10Y yield {rate_10y:.2f}%." if rate_10y else ".")
    )

    return MarketRegimeReport(
        regime=regime,
        volatility=round(volatility, 2),
        spy_trend=spy_trend,
        rate_10y=round(rate_10y, 3) if rate_10y else None,
        summary=summary,
    )


class MarketRegimeAgent(Agent):
    """Broad market context: SPY trend, VIX volatility regime, and the 10Y yield."""

    name = "market_regime"

    def run(self) -> MarketRegimeReport:
        spy_df = fetch_price_history("SPY", period="6mo")

        try:
            vix_df = fetch_price_history("^VIX", period="1mo")
        except Exception:
            vix_df = None

        try:
            rate_10y = float(fetch_price_history("^TNX", period="5d")["Close"].iloc[-1]) / 10
        except Exception:
            rate_10y = None

        return regime_report_from_history(spy_df, vix_df, rate_10y)
