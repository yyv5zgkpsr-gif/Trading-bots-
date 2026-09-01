from data.market_data import fetch_price_history
from models.schemas import Direction, MarketRegimeReport, Regime

from agents.base import Agent


class MarketRegimeAgent(Agent):
    """Broad market context: SPY trend, VIX volatility regime, and the 10Y yield."""

    name = "market_regime"

    def run(self) -> MarketRegimeReport:
        spy_close = fetch_price_history("SPY", period="6mo")["Close"]
        sma50 = float(spy_close.rolling(50).mean().iloc[-1])
        last_spy = float(spy_close.iloc[-1])
        spy_trend = Direction.BULLISH if last_spy > sma50 else Direction.BEARISH

        try:
            volatility = float(fetch_price_history("^VIX", period="1mo")["Close"].iloc[-1])
        except Exception:
            volatility = 20.0

        try:
            rate_10y = float(fetch_price_history("^TNX", period="5d")["Close"].iloc[-1]) / 10
        except Exception:
            rate_10y = None

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
