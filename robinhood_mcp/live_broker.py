"""Thin wrapper around the unofficial `robin_stocks` client for placing REAL
orders on a real Robinhood account.

This is only used when ``ROBINHOOD_MCP_MODE=live``. Login happens once, at
process startup, using ``ROBINHOOD_USERNAME`` / ``ROBINHOOD_PASSWORD`` (and
``ROBINHOOD_MFA_CODE`` if your account requires a one-time TOTP code). If
login fails for any reason, the server refuses to start rather than silently
falling back to paper mode.

Scope note: stop_loss/take_profit are accepted and echoed back for the
caller's own record-keeping, but this module does not place a separate
bracket/stop order — Robinhood's API does not expose one-shot OCO orders, and
half-implementing that risk control would be worse than not implementing it.
Manage exits yourself (e.g. a monitoring loop that re-invokes place_order).
"""

import os

from robinhood_mcp.errors import BrokerError

try:
    import robin_stocks.robinhood as rh
except ImportError:  # pragma: no cover - exercised only when dependency missing
    rh = None


class LiveBroker:
    def __init__(self):
        if rh is None:
            raise BrokerError(
                "robin_stocks is not installed. Run `pip install robin_stocks` to use ROBINHOOD_MCP_MODE=live."
            )

        username = os.environ.get("ROBINHOOD_USERNAME")
        password = os.environ.get("ROBINHOOD_PASSWORD")
        mfa_code = os.environ.get("ROBINHOOD_MFA_CODE")
        if not username or not password:
            raise BrokerError("ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD must be set to use ROBINHOOD_MCP_MODE=live.")

        login_kwargs = {"username": username, "password": password, "store_session": True}
        if mfa_code:
            login_kwargs["mfa_code"] = mfa_code

        try:
            login_result = rh.login(**login_kwargs)
        except Exception as exc:
            raise BrokerError(f"Robinhood login failed: {exc}") from exc
        if not login_result or not login_result.get("access_token"):
            raise BrokerError("Robinhood login failed: no access token returned. Check credentials/MFA.")

    def get_account(self) -> dict:
        portfolio = rh.profiles.load_portfolio_profile() or {}
        account = rh.profiles.load_account_profile() or {}
        equity = portfolio.get("equity")
        cash = account.get("portfolio_cash") or account.get("cash")
        buying_power = account.get("buying_power") or account.get("cash_available_for_withdrawal")
        return {
            "mode": "live",
            "equity": float(equity) if equity is not None else None,
            "cash": float(cash) if cash is not None else None,
            "buying_power": float(buying_power) if buying_power is not None else None,
        }

    def get_positions(self) -> list:
        positions = rh.account.get_open_stock_positions() or []
        result = []
        for position in positions:
            quantity = float(position.get("quantity", 0))
            if quantity == 0:
                continue
            symbol = rh.stocks.get_symbol_by_url(position["instrument"])
            result.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "average_buy_price": float(position.get("average_buy_price", 0)),
                }
            )
        return result

    def place_order(
        self, symbol: str, side: str, quantity: int, order_type: str = "market", price: float = None
    ) -> dict:
        if quantity <= 0:
            raise BrokerError("quantity must be positive.")

        if side == "buy":
            order = (
                rh.orders.order_buy_limit(symbol, quantity, price)
                if order_type == "limit" and price
                else rh.orders.order_buy_market(symbol, quantity)
            )
        elif side == "sell":
            order = (
                rh.orders.order_sell_limit(symbol, quantity, price)
                if order_type == "limit" and price
                else rh.orders.order_sell_market(symbol, quantity)
            )
        else:
            raise BrokerError(f"Unsupported side: {side!r} (expected 'buy' or 'sell').")

        if not order or "id" not in order:
            raise BrokerError(f"Robinhood rejected the order: {order}")

        return {"order_id": order["id"], "state": order.get("state")}
