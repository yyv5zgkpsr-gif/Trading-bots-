"""Performance metrics computed from a finished backtest.Portfolio."""

import math
from dataclasses import dataclass

from backtest.engine import Portfolio


@dataclass
class BacktestMetrics:
    starting_cash: float
    ending_equity: float
    total_return_pct: float
    num_trades: int  # round trips (a BUY followed by the SELL(s) that close it)
    num_wins: int
    num_losses: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float  # gross profit / gross loss; None-safe as inf when no losses
    max_drawdown_pct: float
    sharpe: float  # annualized, using daily equity-curve returns, 0% risk-free


def _round_trips(portfolio: Portfolio) -> list[float]:
    """Pairs up BUYs with the SELL volume that closes them (FIFO) and returns
    each round trip's return, as a fraction (0.05 == +5%). A long-only
    position can be built from several BUYs and unwound by several SELLs;
    this walks both queues together rather than assuming one-for-one."""
    open_lots = []  # list of [quantity_remaining, buy_price]
    round_trip_returns = []

    for trade in portfolio.trades:
        if trade.action == "BUY":
            open_lots.append([trade.quantity, trade.price])
            continue

        remaining_to_sell = trade.quantity
        while remaining_to_sell > 0 and open_lots:
            lot_quantity, lot_price = open_lots[0]
            matched = min(lot_quantity, remaining_to_sell)
            round_trip_returns.append((trade.price - lot_price) / lot_price)
            open_lots[0][0] -= matched
            remaining_to_sell -= matched
            if open_lots[0][0] == 0:
                open_lots.pop(0)

    return round_trip_returns


def _max_drawdown_pct(equity_values: list[float]) -> float:
    if not equity_values:
        return 0.0
    peak = equity_values[0]
    worst = 0.0
    for value in equity_values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value - peak) / peak)
    return worst * 100


def _sharpe(equity_values: list[float], periods_per_year: int = 252) -> float:
    if len(equity_values) < 3:
        return 0.0
    returns = [
        (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
        for i in range(1, len(equity_values))
        if equity_values[i - 1] > 0
    ]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def compute_metrics(portfolio: Portfolio) -> BacktestMetrics:
    equity_values = [point.equity for point in portfolio.equity_curve]
    ending_equity = equity_values[-1] if equity_values else portfolio.starting_cash

    round_trips = _round_trips(portfolio)
    wins = [r for r in round_trips if r > 0]
    losses = [r for r in round_trips if r <= 0]

    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    if not round_trips:
        profit_factor = 0.0  # nothing traded; inf would overstate "no losses" as a result
    elif gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = math.inf

    return BacktestMetrics(
        starting_cash=portfolio.starting_cash,
        ending_equity=round(ending_equity, 2),
        total_return_pct=round((ending_equity / portfolio.starting_cash - 1) * 100, 2),
        num_trades=len(round_trips),
        num_wins=len(wins),
        num_losses=len(losses),
        win_rate_pct=round(len(wins) / len(round_trips) * 100, 2) if round_trips else 0.0,
        avg_win_pct=round((sum(wins) / len(wins)) * 100, 2) if wins else 0.0,
        avg_loss_pct=round((sum(losses) / len(losses)) * 100, 2) if losses else 0.0,
        profit_factor=round(profit_factor, 2) if math.isfinite(profit_factor) else profit_factor,
        max_drawdown_pct=round(_max_drawdown_pct(equity_values), 2),
        sharpe=round(_sharpe(equity_values), 2),
    )
