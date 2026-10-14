"""Exit-monitoring loop for live-mode positions.

ROBINHOOD_MCP_MODE=live places orders with no automatic stop-loss/take-profit
enforcement (see robinhood_mcp/live_broker.py) — Robinhood's API has no atomic
bracket order. This script is the promised alternative: it polls recorded risk
levels (robinhood_mcp/risk_ledger.py, populated automatically whenever
place_order is called with stop_loss/take_profit) against live quotes, and
closes a position with a market sell the moment its level is breached.

Run it as its own long-lived process alongside anything that places live
orders:

    python -m robinhood_mcp.monitor

It talks to the SAME Robinhood MCP server your ExecutionAgent uses — set
ROBINHOOD_MCP_COMMAND exactly as you would for main.py. Requires
ROBINHOOD_MCP_MODE=live; there is nothing to monitor in paper mode (no real
market data feed — see PaperBroker.get_quote).

Limitations, deliberately not papered over:
  - Polling-based, not a live price stream: a fast-moving breach between polls
    can fill worse than the recorded stop_loss/take_profit.
  - Exits the entire position at market; it does not support partial exits
    or limit-priced exits.
  - A crashed or stopped monitor process leaves positions unprotected again,
    same as not running it at all. Run it under something that restarts it
    (e.g. a systemd unit, a supervisor process) for real unattended use.
"""

import asyncio
import json
import os
import shlex
import signal
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("The `mcp` package is required to run the exit monitor.", file=sys.stderr)
    raise

load_dotenv()

POLL_SECONDS = float(os.environ.get("MONITOR_POLL_SECONDS", "30"))


def _log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{timestamp}] {message}", flush=True)


def _parse_blocks(result) -> list:
    """Each text content block is one JSON value. A dict-returning tool sends
    exactly one block; a list-returning tool sends one block per item (zero
    blocks for an empty list) — this MCP version does not wrap list results
    in a single JSON array, so every block must be collected and parsed."""
    return [json.loads(block.text) for block in result.content if getattr(block, "type", "") == "text"]


async def _call_dict(session: ClientSession, tool_name: str, arguments: dict = None) -> dict:
    blocks = _parse_blocks(await session.call_tool(tool_name, arguments=arguments or {}))
    return blocks[0] if blocks else {}


async def _call_list(session: ClientSession, tool_name: str, arguments: dict = None) -> list:
    return _parse_blocks(await session.call_tool(tool_name, arguments=arguments or {}))


async def _check_once(session: ClientSession) -> None:
    positions = await _call_list(session, "get_positions")
    levels = await _call_dict(session, "get_risk_levels")

    positions_by_symbol = {p["symbol"]: p for p in positions if p.get("quantity", 0) > 0}

    for symbol, level in levels.items():
        position = positions_by_symbol.get(symbol)
        if position is None:
            continue  # position already closed some other way; ledger entry is stale

        quote = await _call_dict(session, "get_quote", {"symbol": symbol})
        if "error" in quote:
            _log(f"{symbol}: could not fetch a quote ({quote['error']}); skipping this cycle.")
            continue

        price = quote["price"]
        stop_loss = level.get("stop_loss")
        take_profit = level.get("take_profit")

        breached = None
        if stop_loss is not None and price <= stop_loss:
            breached = f"stop-loss ({price} <= {stop_loss})"
        elif take_profit is not None and price >= take_profit:
            breached = f"take-profit ({price} >= {take_profit})"

        if breached is None:
            continue

        quantity = int(position["quantity"])
        _log(f"{symbol}: {breached} breached on {quantity} shares — submitting market sell.")

        order = await _call_dict(
            session,
            "place_order",
            {"symbol": symbol, "side": "sell", "quantity": quantity, "order_type": "market", "price": price},
        )
        if "error" in order:
            _log(f"{symbol}: exit order FAILED: {order['error']}")
        else:
            _log(f"{symbol}: exit order submitted, order_id={order.get('order_id')}")


async def run() -> None:
    if os.environ.get("ROBINHOOD_MCP_MODE", "paper").lower() != "live":
        _log("ROBINHOOD_MCP_MODE is not 'live' — nothing to monitor (paper mode has no market data feed).")
        return

    mcp_command = os.environ.get("ROBINHOOD_MCP_COMMAND")
    if not mcp_command:
        _log("ROBINHOOD_MCP_COMMAND is not set; nothing to connect to.")
        return

    command_parts = shlex.split(mcp_command)
    server_params = StdioServerParameters(command=command_parts[0], args=command_parts[1:], env=dict(os.environ))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    _log(f"Exit monitor starting (polling every {POLL_SECONDS:.0f}s). Ctrl+C to stop.")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            while not stop.is_set():
                try:
                    await _check_once(session)
                except Exception as exc:
                    _log(f"Monitoring cycle failed: {exc}")
                try:
                    await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
                except asyncio.TimeoutError:
                    pass
    _log("Exit monitor stopped.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
