"""Day-by-day crypto backtest loop.

Same lookahead discipline as backtest/runner.py: decide using price history
only through today's close, execute at tomorrow's open, check the recorded
stop-loss/take-profit against each day's High/Low (crypto trades 24/7, but
yfinance still hands back daily bars, so the same daily-bar approximation
applies — see backtest/runner.py's docstring for the caveat).
"""

import os

import pandas as pd

from agents.crypto_risk_manager import CryptoRiskManagerAgent
from agents.crypto_technical import to_yfinance_crypto_symbol
from backtest.crypto_engine import CryptoPortfolio
from backtest.crypto_strategy import decide
from backtest.metrics import BacktestMetrics, compute_metrics
from data.market_data import fetch_price_history

MIN_LOOKBACK_DAYS = 50  # SMA50 needs this many bars before it means anything


def run_crypto_backtest(
    symbol: str,
    period: str = "2y",
    starting_cash: float = 10_000.0,
    price_history: pd.DataFrame = None,
) -> tuple[CryptoPortfolio, BacktestMetrics]:
    """Runs the technical+risk-manager crypto strategy over historical daily
    bars. Pass `price_history` directly (e.g. in tests) to skip the network
    fetch; otherwise it's pulled via yfinance's `<SYMBOL>-USD` convention for
    `period`.
    """
    price_history = (
        price_history
        if price_history is not None
        else fetch_price_history(to_yfinance_crypto_symbol(symbol), period=period)
    )

    if len(price_history) <= MIN_LOOKBACK_DAYS + 1:
        raise ValueError(
            f"Need more than {MIN_LOOKBACK_DAYS + 1} bars of history to backtest "
            f"(got {len(price_history)}); use a longer `period`."
        )

    risk_agent = CryptoRiskManagerAgent()
    portfolio = CryptoPortfolio(starting_cash)
    open_stop = None
    open_target = None

    dates = price_history.index[MIN_LOOKBACK_DAYS:]

    for i, date in enumerate(dates):
        today = price_history.loc[date]
        stopped_out = False

        # 1. Check the still-open position's stop/target against today's range.
        if portfolio.quantity > 0 and (open_stop is not None or open_target is not None):
            if open_stop is not None and today["Low"] <= open_stop:
                portfolio.sell(date, portfolio.quantity, open_stop, reason="stop_loss")
                open_stop = open_target = None
                stopped_out = True
            elif open_target is not None and today["High"] >= open_target:
                portfolio.sell(date, portfolio.quantity, open_target, reason="take_profit")
                open_stop = open_target = None
                stopped_out = True

        # 2. Decide using data through today's close; execute at tomorrow's open.
        if not stopped_out and i + 1 < len(dates):
            next_date = dates[i + 1]
            next_open = float(price_history.loc[next_date, "Open"])
            idx = price_history.index.get_loc(date)

            decision, _debate = decide(
                symbol,
                price_history.iloc[: idx + 1],
                portfolio.equity(float(today["Close"])),
                risk_agent,
            )

            if decision.approved and decision.action == "BUY":
                portfolio.buy(next_date, decision.position_size_quantity, next_open, reason="signal")
                if portfolio.quantity > 0:
                    open_stop, open_target = decision.stop_loss_price, decision.take_profit_price
            elif decision.approved and decision.action == "SELL" and portfolio.quantity > 0:
                portfolio.sell(next_date, decision.position_size_quantity, next_open, reason="signal")
                if portfolio.quantity == 0:
                    open_stop = open_target = None

        portfolio.mark(date, float(today["Close"]))

    return portfolio, compute_metrics(portfolio)


def _format_report(symbol: str, period: str, metrics: BacktestMetrics) -> str:
    lines = [
        f"=== Crypto Backtest: {symbol} ({period}) — technical + risk-manager only ===",
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

    parser = argparse.ArgumentParser(description="Backtest the crypto technical+risk-manager strategy.")
    parser.add_argument("symbol", help="Crypto ticker, e.g. BTC, ETH")
    parser.add_argument("--period", default="2y", help="yfinance period, e.g. 1y, 2y, 5y (default: 2y)")
    parser.add_argument(
        "--equity", type=float, default=float(os.environ.get("CRYPTO_DEFAULT_ACCOUNT_EQUITY", "10000"))
    )
    args = parser.parse_args()

    _portfolio, metrics = run_crypto_backtest(args.symbol.upper(), period=args.period, starting_cash=args.equity)
    print(_format_report(args.symbol.upper(), args.period, metrics))


if __name__ == "__main__":
    main()
