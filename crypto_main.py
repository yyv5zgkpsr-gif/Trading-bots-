"""CLI entry point for the crypto trading pipeline.

Example:
    python crypto_main.py BTC
    python crypto_main.py ETH --equity 5000 --json

Safe by default: dry-run unless ENABLE_LIVE_TRADING=true and
ROBINHOOD_MCP_COMMAND are both set (same flags agents/execution.py uses for
stocks — see main.py and README.md).
"""

import argparse
import json
from dataclasses import asdict

from dotenv import load_dotenv

from agents.crypto_orchestrator import CryptoOrchestrator


def _json_default(obj):
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Crypto trading pipeline (dry-run / paper-safe by default).")
    parser.add_argument("symbol", help="Crypto ticker to analyze, e.g. BTC, ETH, DOGE")
    parser.add_argument("--equity", type=float, default=None, help="Account equity used for position sizing")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted summary")
    args = parser.parse_args()

    orchestrator = CryptoOrchestrator()
    decision = orchestrator.run(args.symbol.upper(), account_equity=args.equity)

    if args.json:
        print(json.dumps(asdict(decision), indent=2, default=_json_default))
        return

    print(f"\n=== Crypto Trade Decision: {decision.symbol} ===")
    print(f"Technical    : {decision.technical.summary}")
    print(f"Conviction   : {decision.debate.conviction} -> {decision.debate.recommendation.value}")
    print("\n--- Risk Manager ---")
    print(decision.risk.reasoning)
    print("\n--- Execution ---")
    print(decision.execution.details)


if __name__ == "__main__":
    main()
