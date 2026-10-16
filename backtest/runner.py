"""Day-by-day backtest loop.

Timing, to avoid lookahead bias: each day's decision is made using price
history only through that day's close, then executed at the NEXT day's
open — exactly the lag a real daily-bar strategy would have (you can't react
to today's close before today ends). An open position's stop_loss/take_profit
is checked against each day's High/Low and exits intraday at the breached
level, the same day it's breached — daily bars have no true intraday path, so
this is the standard approximation, not a guarantee of that exact fill.

Only one risk-manager-recommended entry/exit is evaluated per day; a stop/
target exit on a given day skips that day's regular signal (the position is
already closed by the time it would run).
"""

import os

import pandas as pd

from agents.risk_manager import RiskManagerAgent
from backtest.engine import Portfolio
from backtest.metrics import BacktestMetrics, compute_metrics
from backtest.strategy import decide
from data.market_data import fetch_price_history

MIN_LOOKBACK_DAYS = 50  # SMA50 needs this many bars before it means anything


def run_backtest(
    ticker: str,
    period: str = "2y",
    starting_cash: float = 10_000.0,
    price_history: pd.DataFrame = None,
    spy_history: pd.DataFrame = None,
    vix_history: pd.DataFrame = None,
) -> tuple[Portfolio, BacktestMetrics]:
    """Runs the technical+regime+risk-manager strategy over historical daily
    bars. Pass price_history/spy_history/vix_history directly (e.g. in tests)
    to skip the network fetch; otherwise they're pulled via yfinance for
    `period`.
    """
    price_history = price_history if price_history is not None else fetch_price_history(ticker, period=period)
    spy_history = spy_history if spy_history is not None else fetch_price_history("SPY", period=period)
    vix_history = vix_history if vix_history is not None else fetch_price_history("^VIX", period=period)

    if len(price_history) <= MIN_LOOKBACK_DAYS + 1:
        raise ValueError(
            f"Need more than {MIN_LOOKBACK_DAYS + 1} bars of history to backtest "
            f"(got {len(price_history)}); use a longer `period`."
        )

    risk_agent = RiskManagerAgent()
    portfolio = Portfolio(starting_cash)
    open_stop = None
    open_target = None

    dates = price_history.index[MIN_LOOKBACK_DAYS:]

    for i, date in enumerate(dates):
        today = price_history.loc[date]
        stopped_out = False

        # 1. Check the still-open position's stop/target against today's range.
        if portfolio.shares > 0 and (open_stop is not None or open_target is not None):
            if open_stop is not None and today["Low"] <= open_stop:
                portfolio.sell(date, portfolio.shares, open_stop, reason="stop_loss")
                open_stop = open_target = None
                stopped_out = True
            elif open_target is not None and today["High"] >= open_target:
                portfolio.sell(date, portfolio.shares, open_target, reason="take_profit")
                open_stop = open_target = None
                stopped_out = True

        # 2. Decide using data through today's close; execute at tomorrow's open.
        if not stopped_out and i + 1 < len(dates):
            next_date = dates[i + 1]
            next_open = float(price_history.loc[next_date, "Open"])
            idx = price_history.index.get_loc(date)

            decision, _debate = decide(
                ticker,
                price_history.iloc[: idx + 1],
                spy_history.loc[:date],
                vix_history.loc[:date],
                portfolio.equity(float(today["Close"])),
                risk_agent,
            )

            if decision.approved and decision.action == "BUY":
                portfolio.buy(next_date, decision.position_size_shares, next_open, reason="signal")
                if portfolio.shares > 0:
                    open_stop, open_target = decision.stop_loss_price, decision.take_profit_price
            elif decision.approved and decision.action == "SELL" and portfolio.shares > 0:
                portfolio.sell(next_date, decision.position_size_shares, next_open, reason="signal")
                if portfolio.shares == 0:
                    open_stop = open_target = None

        portfolio.mark(date, float(today["Close"]))

    return portfolio, compute_metrics(portfolio)


def _format_report(ticker: str, period: str, metrics: BacktestMetrics) -> str:
    lines = [
        f"=== Backtest: {ticker} ({period}) — technical + regime + risk-manager only ===",
        f"Starting cash     : ${metrics.starting_cash:,.2f}",
        f"Ending equity      : ${metrics.ending_equity:,.2f}",
        f"Total return       : {metrics.total_return_pct:+.2f}%",
        f"Round-trip trades  : {metrics.num_trades}",
        f"Win rate           : {metrics.win_rate_pct:.1f}% ({metrics.num_wins}W / {metrics.num_losses}L)",
        f"Avg win / avg loss : {metrics.avg_win_pct:+.2f}% / {metrics.avg_loss_pct:+.2f}%",
        f"Profit factor      : {metrics.profit_factor}",
        f"Max drawdown       : {metrics.max_drawdown_pct:.2f}%",
        f"Sharpe (annualized): {metrics.sharpe}",
    ]
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backtest the technical+regime+risk-manager strategy slice.")
    parser.add_argument("ticker")
    parser.add_argument("--period", default="2y", help="yfinance period, e.g. 1y, 2y, 5y (default: 2y)")
    parser.add_argument("--equity", type=float, default=float(os.environ.get("DEFAULT_ACCOUNT_EQUITY", "10000")))
    args = parser.parse_args()

    _portfolio, metrics = run_backtest(args.ticker.upper(), period=args.period, starting_cash=args.equity)
    print(_format_report(args.ticker.upper(), args.period, metrics))


if __name__ == "__main__":
    main()
