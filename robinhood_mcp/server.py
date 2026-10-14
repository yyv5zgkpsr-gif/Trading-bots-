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

from robinhood_mcp.errors import BrokerError
from robinhood_mcp.paper_broker import PaperBroker

load_dotenv()  # so `python -m robinhood_mcp.server` also works standalone, outside main.py

MODE = os.environ.get("ROBINHOOD_MCP_MODE", "paper").lower()

if MODE == "live":
    from robinhood_mcp.live_broker import LiveBroker

    try:
        broker = LiveBroker()
    except BrokerError as exc:
        raise SystemExit(f"[robinhood-mcp] refusing to start in live mode: {exc}")
elif MODE == "paper":
    broker = PaperBroker()
else:
    raise SystemExit(f"[robinhood-mcp] unknown ROBINHOOD_MCP_MODE={MODE!r}; expected 'paper' or 'live'.")

server = MCPServer("robinhood-mcp")


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
    try:
        result = broker.place_order(symbol, side.lower(), int(quantity), order_type, price)
    except BrokerError as exc:
        return {"error": str(exc)}
    result["stop_loss"] = stop_loss
    result["take_profit"] = take_profit
    return result


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
