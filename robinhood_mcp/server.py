"""Robinhood MCP server: the ONLY execution surface `agents/execution.py` talks to.

Run it directly (``python -m robinhood_mcp.server``) and point
``ROBINHOOD_MCP_COMMAND`` at that command. Defaults to a local paper-trading
ledger (``ROBINHOOD_MCP_MODE=paper``, the default) with no real money or
brokerage account involved. Set ``ROBINHOOD_MCP_MODE=live`` plus
``ROBINHOOD_USERNAME``/``ROBINHOOD_PASSWORD`` (and ``ROBINHOOD_MFA_CODE`` if
needed) to place real orders via `robin_stocks` — the server refuses to start
in live mode if login fails, rather than silently falling back to paper.
"""

import os

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from robinhood_mcp.crypto_paper_broker import CryptoPaperBroker
from robinhood_mcp.errors import BrokerError
from robinhood_mcp.paper_broker import PaperBroker
from robinhood_mcp.risk_ledger import RiskLedger

load_dotenv()  # so `python -m robinhood_mcp.server` also works standalone, outside main.py

MODE = os.environ.get("ROBINHOOD_MCP_MODE", "paper").lower()

if MODE == "live":
    from robinhood_mcp.crypto_live_broker import CryptoLiveBroker
    from robinhood_mcp.live_broker import LiveBroker

    try:
        broker = LiveBroker()
        crypto_broker = CryptoLiveBroker()
    except BrokerError as exc:
        raise SystemExit(f"[robinhood-mcp] refusing to start in live mode: {exc}")
elif MODE == "paper":
    broker = PaperBroker()
    crypto_broker = CryptoPaperBroker()
else:
    raise SystemExit(f"[robinhood-mcp] unknown ROBINHOOD_MCP_MODE={MODE!r}; expected 'paper' or 'live'.")

server = MCPServer("robinhood-mcp")
risk_ledger = RiskLedger()


@server.tool()
def get_account() -> dict:
    """Return current account equity, cash, and buying power."""
    return broker.get_account()


@server.tool()
def get_positions() -> list:
    """Return currently held positions: symbol, quantity, average buy price."""
    return broker.get_positions()


@server.tool()
def place_order(
    symbol: str,
    side: str,
    quantity: int,
    order_type: str = "market",
    price: float = None,
    stop_loss: float = None,
    take_profit: float = None,
) -> dict:
    """Place a buy/sell order.

    In paper mode (default) this fills instantly against a local simulated
    ledger at `price` — no real money or brokerage account is involved. In
    live mode this places a REAL order on your Robinhood account; stop_loss
    and take_profit are recorded in the response for your own reference only
    and are not placed as separate bracket orders.
    """
    side_lower = side.lower()
    try:
        result = broker.place_order(symbol, side_lower, int(quantity), order_type, price)
    except BrokerError as exc:
        return {"error": str(exc)}
    result["stop_loss"] = stop_loss
    result["take_profit"] = take_profit

    # Record risk intent so robinhood_mcp/monitor.py has something to check
    # positions against later — Robinhood's API has no bracket order, so this
    # is the only place that remembers a stop_loss/take_profit was asked for.
    if side_lower == "buy" and (stop_loss is not None or take_profit is not None):
        risk_ledger.record(symbol, side_lower, stop_loss, take_profit)
    elif side_lower == "sell":
        risk_ledger.clear(symbol)

    return result


@server.tool()
def get_risk_levels() -> dict:
    """Return the stop_loss/take_profit recorded for each symbol's open buy order."""
    return risk_ledger.all()


@server.tool()
def get_quote(symbol: str) -> dict:
    """Return the latest market price for `symbol`. Live mode only — paper
    mode has no real market data feed and returns an error."""
    try:
        price = broker.get_quote(symbol)
    except BrokerError as exc:
        return {"error": str(exc)}
    return {"symbol": symbol, "price": price}


@server.tool()
def get_crypto_account() -> dict:
    """Return current crypto buying power. Separate from get_account — on a
    real Robinhood account, crypto and stocks have their own buying power."""
    return crypto_broker.get_account()


@server.tool()
def get_crypto_positions() -> list:
    """Return currently held crypto positions: symbol, quantity (fractional), average buy price."""
    return crypto_broker.get_positions()


@server.tool()
def get_crypto_quote(symbol: str) -> dict:
    """Return the latest market price for a crypto symbol (e.g. "BTC", "ETH").
    Live mode only — paper mode has no real market data feed and returns an error."""
    try:
        price = crypto_broker.get_quote(symbol)
    except BrokerError as exc:
        return {"error": str(exc)}
    return {"symbol": symbol, "price": price}


@server.tool()
def place_crypto_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float = None,
    stop_loss: float = None,
    take_profit: float = None,
) -> dict:
    """Place a crypto buy/sell order by quantity (fractional coins allowed).

    In paper mode (default) this fills instantly against a local simulated
    ledger at `price` — no real money or brokerage account is involved. In
    live mode this places a REAL market order on your Robinhood account via
    robin_stocks; stop_loss/take_profit are recorded for your own reference
    only (see get_risk_levels / robinhood_mcp/monitor.py), not placed as a
    bracket order.
    """
    side_lower = side.lower()
    try:
        result = crypto_broker.place_order(symbol, side_lower, float(quantity), price)
    except BrokerError as exc:
        return {"error": str(exc)}
    result["stop_loss"] = stop_loss
    result["take_profit"] = take_profit

    # Same risk ledger the stock side uses — it's symbol-agnostic, so
    # robinhood_mcp/monitor.py covers crypto positions with no changes.
    if side_lower == "buy" and (stop_loss is not None or take_profit is not None):
        risk_ledger.record(symbol, side_lower, stop_loss, take_profit)
    elif side_lower == "sell":
        risk_ledger.clear(symbol)

    return result


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
