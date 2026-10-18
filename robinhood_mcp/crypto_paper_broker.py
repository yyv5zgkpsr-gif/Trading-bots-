"""A minimal, file-backed paper-trading ledger for crypto.

Separate from ``paper_broker.PaperBroker`` on purpose: crypto trades in
fractional quantities (not whole shares), and on a real Robinhood account
crypto buying power is its own balance, segregated from stock buying power.
Mirrors PaperBroker's design (no real money, no brokerage account, fills
instantly at the caller-supplied price) with its own cash pool and state
file so crypto and stock paper trading never share balances or clobber each
other's state.
"""

import json
import os
import uuid
from pathlib import Path
from threading import Lock

from robinhood_mcp.errors import BrokerError

DEFAULT_STATE_PATH = Path(__file__).parent / "crypto_paper_state.json"
DEFAULT_STARTING_CASH = 10_000.0
QUANTITY_EPSILON = 1e-9  # crypto quantities are floats; tolerate rounding dust


class CryptoPaperBroker:
    def __init__(self, state_path: str = None):
        self.state_path = Path(state_path or os.environ.get("CRYPTO_PAPER_STATE_PATH", str(DEFAULT_STATE_PATH)))
        self._lock = Lock()
        self._load()

    def _load(self):
        if self.state_path.exists():
            with open(self.state_path) as f:
                self.state = json.load(f)
        else:
            self.state = {
                "cash": float(os.environ.get("CRYPTO_PAPER_STARTING_CASH", DEFAULT_STARTING_CASH)),
                "positions": {},  # symbol -> {"quantity": float, "average_buy_price": float}
                "orders": [],
            }
            self._save()

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(self.state, f, indent=2)

    def get_account(self) -> dict:
        with self._lock:
            positions_value = sum(p["quantity"] * p["average_buy_price"] for p in self.state["positions"].values())
            equity = self.state["cash"] + positions_value
            return {
                "mode": "paper",
                "cash": round(self.state["cash"], 2),
                "equity": round(equity, 2),
                "buying_power": round(self.state["cash"], 2),
            }

    def get_positions(self) -> list:
        with self._lock:
            return [
                {"symbol": symbol, **pos}
                for symbol, pos in self.state["positions"].items()
                if pos["quantity"] > QUANTITY_EPSILON
            ]

    def get_quote(self, symbol: str) -> float:
        raise BrokerError(
            "get_crypto_quote is not supported in paper mode; there is no real market data feed. "
            "Exit monitoring (robinhood_mcp/monitor.py) only works in ROBINHOOD_MCP_MODE=live."
        )

    def place_order(self, symbol: str, side: str, quantity: float, price: float = None) -> dict:
        quantity = float(quantity)
        if quantity <= 0:
            raise BrokerError("quantity must be positive.")
        if price is None or price <= 0:
            raise BrokerError("A positive `price` is required to fill a paper crypto order.")

        with self._lock:
            position = self.state["positions"].setdefault(symbol, {"quantity": 0.0, "average_buy_price": 0.0})

            if side == "buy":
                cost = quantity * price
                if cost > self.state["cash"]:
                    raise BrokerError(f"Insufficient paper cash: need ${cost:,.2f}, have ${self.state['cash']:,.2f}.")
                total_cost = position["quantity"] * position["average_buy_price"] + cost
                position["quantity"] += quantity
                position["average_buy_price"] = total_cost / position["quantity"]
                self.state["cash"] -= cost
            elif side == "sell":
                if quantity > position["quantity"] + QUANTITY_EPSILON:
                    raise BrokerError(f"Cannot sell {quantity} {symbol}; only {position['quantity']} held.")
                quantity = min(quantity, position["quantity"])
                position["quantity"] -= quantity
                self.state["cash"] += quantity * price
                if position["quantity"] <= QUANTITY_EPSILON:
                    position["quantity"] = 0.0
                    position["average_buy_price"] = 0.0
            else:
                raise BrokerError(f"Unsupported side: {side!r} (expected 'buy' or 'sell').")

            order_id = f"crypto-paper-{uuid.uuid4().hex[:12]}"
            self.state["orders"].append(
                {"order_id": order_id, "symbol": symbol, "side": side, "quantity": quantity, "fill_price": price}
            )
            self._save()
            return {"order_id": order_id, "state": "filled", "fill_price": price, "quantity": quantity}
