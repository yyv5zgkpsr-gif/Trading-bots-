"""Portfolio bookkeeping for the crypto backtest: cash, one fractional
position, a trade log, and a daily equity curve.

Separate from backtest/engine.py's Portfolio because crypto trades in
fractional quantities — routing it through code that floors purchases to
whole shares would silently round away most of a crypto position. Reuses
the same Trade/EquityPoint dataclasses (quantity is just a float here
instead of a whole number), so backtest/metrics.py's compute_metrics()
works unchanged.
"""

from backtest.engine import EquityPoint, Trade

__all__ = ["CryptoPortfolio", "Trade", "EquityPoint"]


class CryptoPortfolio:
    def __init__(self, starting_cash: float):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.quantity = 0.0
        self.avg_price = 0.0
        self.trades: list[Trade] = []
        self.equity_curve: list[EquityPoint] = []

    def equity(self, price: float) -> float:
        return self.cash + self.quantity * price

    def mark(self, date, price: float) -> None:
        self.equity_curve.append(EquityPoint(date, self.equity(price)))

    def buy(self, date, quantity: float, price: float, reason: str = "signal") -> None:
        if price <= 0:
            return
        quantity = min(quantity, self.cash / price)  # cap by affordable amount, no flooring to a whole unit
        if quantity <= 0:
            return
        cost = quantity * price
        total_cost = self.quantity * self.avg_price + cost
        self.quantity += quantity
        self.avg_price = total_cost / self.quantity
        self.cash -= cost
        self.trades.append(Trade(date, "BUY", reason, quantity, price, self.cash, self.equity(price)))

    def sell(self, date, quantity: float, price: float, reason: str = "signal") -> None:
        quantity = min(quantity, self.quantity)  # long-only: can never sell more than held
        if quantity <= 0:
            return
        self.cash += quantity * price
        self.quantity -= quantity
        if self.quantity <= 1e-9:
            self.quantity = 0.0
            self.avg_price = 0.0
        self.trades.append(Trade(date, "SELL", reason, quantity, price, self.cash, self.equity(price)))

    def apply_decision(self, date, decision, fill_price: float) -> None:
        if not decision.approved or decision.action == "HOLD":
            return
        if decision.action == "BUY":
            self.buy(date, decision.position_size_quantity, fill_price, reason="signal")
        elif decision.action == "SELL":
            self.sell(date, decision.position_size_quantity, fill_price, reason="signal")
