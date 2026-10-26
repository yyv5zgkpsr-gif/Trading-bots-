"""Grid search over the risk-manager's sizing knobs (MIN_CONVICTION,
stop-loss/take-profit percents), so you can find a better combination
*before* loosening a threshold to chase more trades — the natural next
step after "Backtesting before you tune for trade frequency" in the
README: validate first, then search for better parameters, then scale.

Takes an already-fetched price history and re-runs the backtest loop once
per parameter combination with the matching env vars set. Safe to do
because run_backtest() and run_crypto_backtest() both construct their
risk-manager fresh on every call, reading every sizing knob from the
environment at that moment — nothing about the strategy is cached across
calls, so setting env vars between calls is enough to change its behavior.
"""

import itertools
import math
import os
from dataclasses import dataclass
from typing import Any, Callable

from backtest.metrics import BacktestMetrics

DEFAULT_STOCK_GRID: dict[str, list[Any]] = {
    "MIN_CONVICTION": [0.10, 0.15, 0.20, 0.25],
    "DEFAULT_STOP_LOSS_PCT": [0.03, 0.05, 0.08],
    "DEFAULT_TAKE_PROFIT_PCT": [0.08, 0.12, 0.16],
}

DEFAULT_CRYPTO_GRID: dict[str, list[Any]] = {
    "MIN_CONVICTION": [0.10, 0.15, 0.20, 0.25],
    "CRYPTO_STOP_LOSS_PCT": [0.04, 0.07, 0.10],
    "CRYPTO_TAKE_PROFIT_PCT": [0.10, 0.15, 0.20],
}


@dataclass
class SweepResult:
    params: dict[str, Any]
    metrics: BacktestMetrics


def grid_search(
    backtest_fn: Callable[..., tuple[Any, BacktestMetrics]],
    backtest_kwargs: dict[str, Any],
    param_grid: dict[str, list[Any]],
    min_trades: int = 5,
) -> list[SweepResult]:
    """Runs `backtest_fn(**backtest_kwargs)` once per combination in the
    cartesian product of `param_grid`'s values, setting each combination
    as environment variables (its keys) before the call and restoring
    whatever those variables held beforehand afterward, even if a call
    raises.

    Drops any combination whose backtest produced fewer than `min_trades`
    round trips: a handful of trades can "win" 100% of the time by chance,
    and ranking by return alone would surface exactly those as if they
    were a real edge.
    """
    keys = list(param_grid.keys())
    original = {key: os.environ.get(key) for key in keys}
    results: list[SweepResult] = []
    try:
        for combo in itertools.product(*param_grid.values()):
            overrides = dict(zip(keys, combo))
            for key, value in overrides.items():
                os.environ[key] = str(value)
            _state, metrics = backtest_fn(**backtest_kwargs)
            if metrics.num_trades >= min_trades:
                results.append(SweepResult(params=overrides, metrics=metrics))
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return results


def rank(results: list[SweepResult], by: str = "sharpe") -> list[SweepResult]:
    """Sorts sweep results by a BacktestMetrics field, descending."""
    return sorted(results, key=lambda r: getattr(r.metrics, by), reverse=True)


def _format_leaderboard(results: list[SweepResult], by: str, top_n: int) -> str:
    header = f"{'params':<60} {'return%':>8} {'trades':>7} {'win%':>6} {'sharpe':>7} {'maxdd%':>7}"
    lines = [header]
    for r in rank(results, by=by)[:top_n]:
        params_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
        m = r.metrics
        lines.append(
            f"{params_str:<60} {m.total_return_pct:>8.2f} {m.num_trades:>7} "
            f"{m.win_rate_pct:>6.1f} {m.sharpe:>7.2f} {m.max_drawdown_pct:>7.2f}"
        )
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Grid-search MIN_CONVICTION/stop-loss/take-profit against one historical period."
    )
    parser.add_argument("symbol")
    parser.add_argument("--asset-class", choices=["stock", "crypto"], default="stock")
    parser.add_argument("--period", default="2y", help="yfinance period, e.g. 1y, 2y, 5y (default: 2y)")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--min-trades", type=int, default=5, help="drop combinations with fewer round trips")
    parser.add_argument("--rank-by", default="sharpe", choices=["sharpe", "total_return_pct", "profit_factor"])
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    symbol = args.symbol.upper()

    if args.asset_class == "crypto":
        from agents.crypto_technical import to_yfinance_crypto_symbol
        from backtest.crypto_runner import run_crypto_backtest
        from data.market_data import fetch_price_history

        grid = DEFAULT_CRYPTO_GRID
        price_history = fetch_price_history(to_yfinance_crypto_symbol(symbol), period=args.period)
        backtest_kwargs = {"symbol": symbol, "starting_cash": args.equity, "price_history": price_history}
        results = grid_search(run_crypto_backtest, backtest_kwargs, grid, min_trades=args.min_trades)
    else:
        from backtest.runner import run_backtest
        from data.market_data import fetch_price_history

        grid = DEFAULT_STOCK_GRID
        price_history = fetch_price_history(symbol, period=args.period)
        spy_history = fetch_price_history("SPY", period=args.period)
        vix_history = fetch_price_history("^VIX", period=args.period)
        backtest_kwargs = {
            "ticker": symbol,
            "starting_cash": args.equity,
            "price_history": price_history,
            "spy_history": spy_history,
            "vix_history": vix_history,
        }
        results = grid_search(run_backtest, backtest_kwargs, grid, min_trades=args.min_trades)

    total_combos = math.prod(len(values) for values in grid.values())
    if not results:
        print(
            f"None of the {total_combos} parameter combinations produced >= {args.min_trades} trades "
            f"over --period {args.period}; try a longer period or a lower --min-trades."
        )
        return

    print(
        f"=== Parameter sweep: {symbol} ({args.asset_class}, {args.period}) — "
        f"{len(results)}/{total_combos} combinations met the {args.min_trades}-trade floor, ranked by {args.rank_by} ==="
    )
    print(_format_leaderboard(results, by=args.rank_by, top_n=args.top))


if __name__ == "__main__":
    main()
