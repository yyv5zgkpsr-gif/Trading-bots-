"""Crypto execution agent. Talks to the exact same Robinhood MCP server as
agents/execution.py (same ROBINHOOD_MCP_COMMAND, same account) via the
place_crypto_order/get_crypto_account tools. Mirrors execution.py's safety
pattern exactly: every order is a dry run unless both
``ENABLE_LIVE_TRADING=true`` and ``ROBINHOOD_MCP_COMMAND`` are set.
"""

import asyncio
import json
import os
import shlex
from typing import Optional

from models.schemas import CryptoRiskDecision, ExecutionResult

from agents.base import Agent
from agents.execution import _innermost_exception_message

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # pragma: no cover - exercised only when dependency missing
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None


def _extract_order_id(blocks: list):
    payload = blocks[0] if blocks else {}
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload.get("order_id")


class CryptoExecutionAgent(Agent):
    name = "crypto_execution"

    def __init__(self):
        self.enable_live = os.environ.get("ENABLE_LIVE_TRADING", "false").lower() == "true"
        self.mcp_command = os.environ.get("ROBINHOOD_MCP_COMMAND")

    def run(self, symbol: str, risk: CryptoRiskDecision) -> ExecutionResult:
        if not risk.approved:
            return ExecutionResult(
                executed=False, dry_run=True, order_id=None, details="Risk manager did not approve a trade."
            )

        if not self.enable_live or not self.mcp_command or ClientSession is None:
            details = (
                f"[DRY RUN] Would submit {risk.action} order for {risk.position_size_quantity} {symbol} "
                f"with stop {risk.stop_loss_price} / target {risk.take_profit_price}. "
                "Set ENABLE_LIVE_TRADING=true and ROBINHOOD_MCP_COMMAND to a Robinhood MCP server "
                "to place live orders."
            )
            return ExecutionResult(executed=False, dry_run=True, order_id=None, details=details)

        try:
            order_id = asyncio.run(
                self._call_tool(
                    "place_crypto_order",
                    {
                        "symbol": symbol,
                        "side": risk.action.lower(),
                        "quantity": risk.position_size_quantity,
                        "price": risk.entry_price,
                        "stop_loss": risk.stop_loss_price,
                        "take_profit": risk.take_profit_price,
                    },
                    _extract_order_id,
                )
            )
        except Exception as exc:
            message = _innermost_exception_message(exc)
            return ExecutionResult(executed=False, dry_run=False, order_id=None, details=f"Execution failed: {message}")

        return ExecutionResult(
            executed=True,
            dry_run=False,
            order_id=order_id,
            details=f"Submitted {risk.action} order for {risk.position_size_quantity} {symbol} via Robinhood MCP (crypto).",
        )

    def get_account_balance(self) -> Optional[float]:
        """Live crypto buying power from the MCP server's get_crypto_account
        tool. Returns None (never raises) when live trading isn't configured
        or the call fails — callers fall back to a configured default."""
        if not self.enable_live or not self.mcp_command or ClientSession is None:
            return None

        def _extract_balance(blocks: list):
            payload = blocks[0] if blocks else {}
            for key in ("buying_power", "equity", "cash"):
                if payload.get(key) is not None:
                    try:
                        return float(payload[key])
                    except (TypeError, ValueError):
                        continue
            return None

        try:
            return asyncio.run(self._call_tool("get_crypto_account", {}, _extract_balance))
        except Exception:
            return None

    def get_positions(self) -> Optional[list]:
        """Live crypto positions from the MCP server's get_crypto_positions
        tool: a list of {symbol, quantity, average buy price} dicts. Returns
        None (never raises) when live trading isn't configured or the call
        fails, same contract as get_account_balance()."""
        if not self.enable_live or not self.mcp_command or ClientSession is None:
            return None

        try:
            return asyncio.run(self._call_tool("get_crypto_positions", {}, lambda blocks: blocks))
        except Exception:
            return None

    async def _call_tool(self, tool_name: str, arguments: dict, extract):
        """Opens an MCP session, calls `tool_name`, and applies `extract` to
        every parseable JSON text block of the response (as a list — a
        dict-returning tool sends exactly one block, but a list-returning
        tool sends one block PER ITEM over this MCP version's stdio
        transport, not a single JSON array; see robinhood_mcp/monitor.py's
        _parse_blocks for where this was first verified against the real
        transport). Forwards the full environment to the spawned server —
        see agents/execution.py for why that matters."""
        command_parts = shlex.split(self.mcp_command)
        server_params = StdioServerParameters(
            command=command_parts[0], args=command_parts[1:], env=dict(os.environ)
        )
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                blocks = []
                for block in result.content:
                    if getattr(block, "type", "") == "text":
                        try:
                            blocks.append(json.loads(block.text))
                        except json.JSONDecodeError:
                            blocks.append(block.text)
                return extract(blocks)
                return None
