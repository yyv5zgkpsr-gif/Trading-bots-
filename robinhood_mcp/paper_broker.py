"""A minimal, file-backed paper-trading ledger.

Not connected to Robinhood or any live market — orders fill instantly at the
caller-supplied ``price``. This is the default broker backend
(``ROBINHOOD_MCP_MODE=paper``, the default) so the trading pipeline can be
exercised end to end, with no real money and no brokerage credentials.
"""

import json
import os
import uuid
from pathlib import Path
from threading import Lock

from robinhood_mcp.errors import BrokerError

DEFAULT_STATE_PATH = Path(__file__).parent / "paper_state.json"
DEFAULT_STARTING_CASH = 10_000.0


class PaperBroker:
    def __init__(self, state_path: str = None):
        self.state_path = Path(state_path or os.environ.get("PAPER_STATE_PATH", str(DEFAULT_STATE_PATH)))
        self._lock = Lock()
        self._load()

    def _load(self):
        if self.state_path.exists():
            with open(self.state_path) as f:
                self.state = json.load(f)
        else:
            self.state = {
                "cash": float(os.environ.get("PAPER_STARTING_CASH", DEFAULT_STARTING_CASH)),
                "positions": {},  # symbol -> {"quantity": int, "average_buy_price": float}
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
            return [{"symbol": symbol, **pos} for symbol, pos in self.state["positions"].items() if pos["quantity"] != 0]

    def place_order(
        self, symbol: str, side: str, quantity: int, order_type: str = "market", price: float = None
    ) -> dict:
        if quantity <= 0:
            raise BrokerError("quantity must be positive.")
        if price is None or price <= 0:
            raise BrokerError("A positive `price` is required to fill a paper order.")

        with self._lock:
            position = self.state["positions"].setdefault(symbol, {"quantity": 0, "average_buy_price": 0.0})

            if side == "buy":
                cost = quantity * price
                if cost > self.state["cash"]:
                    raise BrokerError(f"Insufficient paper cash: need ${cost:,.2f}, have ${self.state['cash']:,.2f}.")
                total_cost = position["quantity"] * position["average_buy_price"] + cost
                position["quantity"] += quantity
                position["average_buy_price"] = total_cost / position["quantity"]
                self.state["cash"] -= cost
            elif side == "sell":
                if quantity > position["quantity"]:
                    raise BrokerError(f"Cannot sell {quantity} shares of {symbol}; only {position['quantity']} held.")
                position["quantity"] -= quantity
                self.state["cash"] += quantity * price
                if position["quantity"] == 0:
                    position["average_buy_price"] = 0.0
            else:
                raise BrokerError(f"Unsupported side: {side!r} (expected 'buy' or 'sell').")

            order_id = f"paper-{uuid.uuid4().hex[:12]}"
            self.state["orders"].append(
                {
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "order_type": order_type,
                    "fill_price": price,
                }
            )
            self._save()
            return {"order_id": order_id, "state": "filled", "fill_price": price}
