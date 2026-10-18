"""Portfolio bookkeeping for the backtest: cash, a single long position, a
trade log, and a daily equity curve. Long-only, one symbol — this mirrors
what robinhood_mcp/paper_broker.py actually allows (it rejects a sell beyond
what you hold, so initiating a short is not something this pipeline can
really do against either broker today).
"""

from dataclasses import dataclass

from models.schemas import RiskDecision


@dataclass
class Trade:
    date: object  # pandas.Timestamp
    action: str  # BUY / SELL
    reason: str  # "signal", "stop_loss", or "take_profit"
    shares: int
    price: float
    cash_after: float
    equity_after: float


@dataclass
class EquityPoint:
    date: object
    equity: float


class Portfolio:
    def __init__(self, starting_cash: float):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.shares = 0
        self.avg_price = 0.0
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []

    def equity(self, price: float) -> float:
        return self.cash + self.shares * price

    def mark(self, date, price: float) -> None:
        self.equity_curve.append(EquityPoint(date, self.equity(price)))

    def buy(self, date, shares: int, price: float, reason: str = "signal") -> None:
        shares = min(shares, int(self.cash // price)) if price > 0 else 0
        if shares <= 0:
            return
        cost = shares * price
        total_cost = self.shares * self.avg_price + cost
        self.shares += shares
        self.avg_price = total_cost / self.shares
        self.cash -= cost
        self.trades.append(Trade(date, "BUY", reason, shares, price, self.cash, self.equity(price)))

    def sell(self, date, shares: int, price: float, reason: str = "signal") -> None:
        shares = min(shares, self.shares)  # long-only: can never sell more than held
        if shares <= 0:
            return
        self.cash += shares * price
        self.shares -= shares
        if self.shares == 0:
            self.avg_price = 0.0
        self.trades.append(Trade(date, "SELL", reason, shares, price, self.cash, self.equity(price)))

    def apply_decision(self, date, decision: RiskDecision, fill_price: float) -> None:
        if not decision.approved or decision.action == "HOLD":
            return
        if decision.action == "BUY":
            self.buy(date, decision.position_size_shares, fill_price, reason="signal")
        elif decision.action == "SELL":
            self.sell(date, decision.position_size_shares, fill_price, reason="signal")
