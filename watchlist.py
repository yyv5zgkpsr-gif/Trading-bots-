"""Run the full stock pipeline across several tickers in one process.

Example:
    python watchlist.py AAPL MSFT NVDA
    python watchlist.py --file watchlist.txt --json

Each ticker gets its own full Orchestrator.run() call, one after another
(not in parallel — see the --equity note below). A ticker whose pipeline
raises (bad symbol, a flaky data fetch, ...) is reported as failed and
does not stop the rest of the watchlist from running.
"""

import argparse
import json
import sys
from dataclasses import asdict

from dotenv import load_dotenv

from agents.orchestrator import Orchestrator


def _json_default(obj):
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def _load_symbols(args) -> list[str]:
    symbols = [s.upper() for s in args.tickers]
    if args.file:
        with open(args.file) as f:
            symbols += [line.strip().upper() for line in f if line.strip() and not line.strip().startswith("#")]
    # de-duplicate, keep first-seen order
    seen = set()
    ordered = []
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ordered


def run_watchlist(symbols: list[str], account_equity: float = None) -> tuple[dict, dict]:
    """Returns (decisions, errors), both keyed by ticker.

    account_equity is passed straight through to every call. Leave it as
    None (the default) unless you have a specific reason not to: Orchestrator
    then re-queries live/paper equity before every ticker, so sizing on the
    3rd ticker reflects cash already committed to the first two. A fixed
    --equity is reused unchanged for every ticker and does NOT account for
    that — only pass it if you're sizing against a budget smaller than your
    real account on purpose (e.g. testing), never to size a real multi-
    ticker live run.
    """
    orchestrator = Orchestrator()
    decisions = {}
    errors = {}
    for symbol in symbols:
        try:
            decisions[symbol] = orchestrator.run(symbol, account_equity=account_equity)
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not kill the watchlist
            errors[symbol] = str(exc)
    return decisions, errors


def _format_summary(decisions: dict, errors: dict) -> str:
    header = f"{'ticker':<8} {'action':<6} {'approved':<9} {'conviction':<11} {'size':<12} reasoning"
    lines = [header]
    for symbol, decision in decisions.items():
        r = decision.risk
        size = f"{r.position_size_shares} sh" if r.position_size_shares else "-"
        reasoning = r.reasoning[:70] + ("..." if len(r.reasoning) > 70 else "")
        lines.append(
            f"{symbol:<8} {r.action:<6} {str(r.approved):<9} "
            f"{decision.debate.conviction:<11} {size:<12} {reasoning}"
        )
    for symbol, message in errors.items():
        lines.append(f"{symbol:<8} FAILED : {message}")
    return "\n".join(lines)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the stock pipeline across a watchlist of tickers.")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. AAPL MSFT NVDA")
    parser.add_argument("--file", help="Path to a newline-separated file of extra tickers (# comments allowed)")
    parser.add_argument(
        "--equity", type=float, default=None, help="See run_watchlist()'s docstring before setting this"
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted summary")
    args = parser.parse_args()

    symbols = _load_symbols(args)
    if not symbols:
        parser.error("no tickers given: pass them as arguments, via --file, or both")

    if args.equity is not None:
        print(
            f"NOTE: --equity {args.equity} will be reused unchanged for all {len(symbols)} tickers "
            "without accounting for cash already committed earlier in this run. See watchlist.py's "
            "run_watchlist() docstring. Omit --equity to size each ticker against live/paper equity "
            "that already reflects prior fills.",
            file=sys.stderr,
        )

    decisions, errors = run_watchlist(symbols, account_equity=args.equity)

    if args.json:
        print(
            json.dumps(
                {symbol: asdict(decision) for symbol, decision in decisions.items()} | {"_errors": errors},
                indent=2,
                default=_json_default,
            )
        )
        return

    print(f"\n=== Watchlist: {len(decisions)}/{len(symbols)} succeeded ===")
    print(_format_summary(decisions, errors))


if __name__ == "__main__":
    main()
