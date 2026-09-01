"""Execution agent. Robinhood MCP is the ONLY execution path — there is no direct
brokerage API call anywhere in this codebase, by design.

Safety default: unless both ``ENABLE_LIVE_TRADING=true`` and
``ROBINHOOD_MCP_COMMAND`` (the shell command that launches your own Robinhood MCP
server) are set, every order is a dry run: it is logged and returned, never sent
anywhere. This code does not ship or bundle a Robinhood MCP server implementation;
point ROBINHOOD_MCP_COMMAND at one you run and trust.
"""

import asyncio
import json
import os
import shlex
from typing import Optional

from models.schemas import ExecutionResult, RiskDecision

from agents.base import Agent

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # pragma: no cover - exercised only when dependency missing
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None


class ExecutionAgent(Agent):
    name = "execution"

    def __init__(self):
        self.enable_live = os.environ.get("ENABLE_LIVE_TRADING", "false").lower() == "true"
        self.mcp_command = os.environ.get("ROBINHOOD_MCP_COMMAND")

    def run(self, ticker: str, risk: RiskDecision) -> ExecutionResult:
        if not risk.approved:
            return ExecutionResult(
                executed=False, dry_run=True, order_id=None, details="Risk manager did not approve a trade."
            )

        if not self.enable_live or not self.mcp_command or ClientSession is None:
            details = (
                f"[DRY RUN] Would submit {risk.action} order for {risk.position_size_shares} shares of "
                f"{ticker} with stop {risk.stop_loss_price} / target {risk.take_profit_price}. "
                "Set ENABLE_LIVE_TRADING=true and ROBINHOOD_MCP_COMMAND to a Robinhood MCP server "
                "to place live orders."
            )
            return ExecutionResult(executed=False, dry_run=True, order_id=None, details=details)

        try:
            order_id = asyncio.run(self._place_order_via_mcp(ticker, risk))
        except Exception as exc:
            return ExecutionResult(executed=False, dry_run=False, order_id=None, details=f"Execution failed: {exc}")

        return ExecutionResult(
            executed=True,
            dry_run=False,
            order_id=order_id,
            details=f"Submitted {risk.action} order for {risk.position_size_shares} shares of {ticker} via Robinhood MCP.",
        )

    async def _place_order_via_mcp(self, ticker: str, risk: RiskDecision) -> Optional[str]:
        command_parts = shlex.split(self.mcp_command)
        server_params = StdioServerParameters(command=command_parts[0], args=command_parts[1:])
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "place_order",
                    arguments={
                        "symbol": ticker,
                        "side": risk.action.lower(),
                        "quantity": risk.position_size_shares,
                        "order_type": "market",
                        "stop_loss": risk.stop_loss_price,
                        "take_profit": risk.take_profit_price,
                    },
                )
                for block in result.content:
                    if getattr(block, "type", "") == "text":
                        try:
                            return json.loads(block.text).get("order_id")
                        except (json.JSONDecodeError, AttributeError):
                            return block.text
                return None
