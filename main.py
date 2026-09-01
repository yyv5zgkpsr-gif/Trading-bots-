"""CLI entry point for the multi-agent trading orchestrator.

Example:
    python main.py AAPL
    python main.py AAPL --equity 25000 --json
"""

import argparse
import json
from dataclasses import asdict

from dotenv import load_dotenv

from agents.orchestrator import Orchestrator


def _json_default(obj):
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Multi-agent trading orchestrator (dry-run / paper-safe by default)."
    )
    parser.add_argument("ticker", help="Ticker symbol to analyze, e.g. AAPL")
    parser.add_argument("--equity", type=float, default=None, help="Account equity used for position sizing")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted summary")
    args = parser.parse_args()

    orchestrator = Orchestrator()
    decision = orchestrator.run(args.ticker.upper(), account_equity=args.equity)

    if args.json:
        print(json.dumps(asdict(decision), indent=2, default=_json_default))
        return

    print(f"\n=== Trade Decision: {decision.ticker} ===")
    print(f"News/Catalyst  : {decision.news.summary}")
    print(f"Technical      : {decision.technical.summary}")
    print(f"Fundamental    : {decision.fundamental.summary}")
    print(f"Sentiment      : {decision.sentiment.summary}")
    print(f"Market Regime  : {decision.regime.summary}")
    print("\n--- Debate ---")
    print(f"Bull: {decision.debate.bull_thesis}")
    print(f"Bear: {decision.debate.bear_thesis}")
    print(f"Conviction: {decision.debate.conviction} -> {decision.debate.recommendation.value}")
    print("\n--- Risk Manager ---")
    print(decision.risk.reasoning)
    print("\n--- Execution ---")
    print(decision.execution.details)


if __name__ == "__main__":
    main()
