"""Thin wrapper around `robin_stocks`' crypto order functions for placing
REAL crypto orders on a real Robinhood account.

Shares the same login as the stock ``LiveBroker`` (see
``robinhood_mcp/auth.py``) — Robinhood crypto trades under the same account
session, so no separate credentials or login call are needed here.

Scope note: market orders by quantity only (same as stock LiveBroker's
default path). No bracket/stop order is placed with Robinhood directly —
robinhood_mcp/monitor.py and robinhood_mcp/risk_ledger.py are symbol-agnostic
already, so they cover crypto exit monitoring with zero changes.

Honesty about what's unverified: this talks to robin_stocks' documented
crypto API surface (order_buy_crypto_by_quantity, get_crypto_positions,
get_crypto_quote, etc.), inspected from the installed package rather than
exercised against a real account — this sandbox has no network path to
Robinhood to verify it end-to-end. The field mapping in get_positions
(``position["currency"]["code"]`` for the ticker, ``cost_basis`` as a total
dollar amount rather than a per-unit price) matches robin_stocks' documented
response shape as of this writing; verify it against your own account before
trusting it, the same way you would with live_broker.py.
"""

from robinhood_mcp.auth import ensure_login
from robinhood_mcp.errors import BrokerError

try:
    import robin_stocks.robinhood as rh
except ImportError:  # pragma: no cover - exercised only when dependency missing
    rh = None


class CryptoLiveBroker:
    def __init__(self):
        ensure_login()

    def get_account(self) -> dict:
        profile = rh.crypto.load_crypto_profile() or {}
        buying_power = profile.get("buying_power") or profile.get("crypto_buying_power")
        return {
            "mode": "live",
            "equity": None,
            "cash": None,
            "buying_power": float(buying_power) if buying_power is not None else None,
        }

    def get_positions(self) -> list:
        positions = rh.crypto.get_crypto_positions() or []
        result = []
        for position in positions:
            quantity = float(position.get("quantity", 0))
            if quantity <= 0:
                continue
            currency = position.get("currency") or {}
            symbol = currency.get("code")
            if not symbol:
                raise BrokerError(
                    f"Could not determine the ticker symbol for a crypto position: {position!r}. "
                    "robin_stocks' crypto holdings response shape may have changed."
                )
            cost_basis = float(position.get("cost_basis", 0) or 0)
            result.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "average_buy_price": (cost_basis / quantity) if quantity else 0.0,
                }
            )
        return result

    def get_quote(self, symbol: str) -> float:
        price = rh.crypto.get_crypto_quote(symbol, info="mark_price")
        if not price:
            raise BrokerError(f"Could not fetch a quote for {symbol!r}.")
        return float(price)

    def place_order(self, symbol: str, side: str, quantity: float, price: float = None) -> dict:
        quantity = float(quantity)
        if quantity <= 0:
            raise BrokerError("quantity must be positive.")

        if side == "buy":
            order = (
                rh.orders.order_buy_crypto_limit(symbol, quantity, price)
                if price
                else rh.orders.order_buy_crypto_by_quantity(symbol, quantity)
            )
        elif side == "sell":
            order = (
                rh.orders.order_sell_crypto_limit(symbol, quantity, price)
                if price
                else rh.orders.order_sell_crypto_by_quantity(symbol, quantity)
            )
        else:
            raise BrokerError(f"Unsupported side: {side!r} (expected 'buy' or 'sell').")

        if not order or "id" not in order:
            raise BrokerError(f"Robinhood rejected the crypto order: {order}")

        return {"order_id": order["id"], "state": order.get("state")}
