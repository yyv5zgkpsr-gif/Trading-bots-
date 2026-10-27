"""Run the crypto pipeline across several symbols in one process.

Example:
    python crypto_watchlist.py BTC ETH SOL
    python crypto_watchlist.py --file crypto_watchlist.txt --json

Mirrors watchlist.py exactly (see its docstring for the --equity caveat
and the per-symbol error handling), swapped to CryptoOrchestrator and
fractional quantities.
"""

import argparse
import json
import sys
from dataclasses import asdict

from dotenv import load_dotenv

from agents.crypto_orchestrator import CryptoOrchestrator


def _json_default(obj):
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


def _load_symbols(args) -> list[str]:
    symbols = [s.upper() for s in args.symbols]
    if args.file:
        with open(args.file) as f:
            symbols += [line.strip().upper() for line in f if line.strip() and not line.strip().startswith("#")]
    seen = set()
    ordered = []
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ordered


def run_crypto_watchlist(symbols: list[str], account_equity: float = None) -> tuple[dict, dict]:
    """Returns (decisions, errors), both keyed by symbol. See
    watchlist.py's run_watchlist() for the --equity caveat — it applies
    identically here."""
    orchestrator = CryptoOrchestrator()
    decisions = {}
    errors = {}
    for symbol in symbols:
        try:
            decisions[symbol] = orchestrator.run(symbol, account_equity=account_equity)
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the watchlist
            errors[symbol] = str(exc)
    return decisions, errors


def _format_summary(decisions: dict, errors: dict) -> str:
    header = f"{'symbol':<8} {'action':<6} {'approved':<9} {'conviction':<11} {'quantity':<14} reasoning"
    lines = [header]
    for symbol, decision in decisions.items():
        r = decision.risk
        quantity = f"{r.position_size_quantity:g}" if r.position_size_quantity else "-"
        reasoning = r.reasoning[:70] + ("..." if len(r.reasoning) > 70 else "")
        lines.append(
            f"{symbol:<8} {r.action:<6} {str(r.approved):<9} "
            f"{decision.debate.conviction:<11} {quantity:<14} {reasoning}"
        )
    for symbol, message in errors.items():
        lines.append(f"{symbol:<8} FAILED : {message}")
    return "\n".join(lines)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run the crypto pipeline across a watchlist of symbols.")
    parser.add_argument("symbols", nargs="*", help="Crypto tickers, e.g. BTC ETH SOL")
    parser.add_argument("--file", help="Path to a newline-separated file of extra symbols (# comments allowed)")
    parser.add_argument(
        "--equity", type=float, default=None, help="See crypto_watchlist.py module docstring before setting this"
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted summary")
    args = parser.parse_args()

    symbols = _load_symbols(args)
    if not symbols:
        parser.error("no symbols given: pass them as arguments, via --file, or both")

    if args.equity is not None:
        print(
            f"NOTE: --equity {args.equity} will be reused unchanged for all {len(symbols)} symbols "
            "without accounting for cash already committed earlier in this run. Omit --equity to size "
            "each symbol against live/paper equity that already reflects prior fills.",
            file=sys.stderr,
        )

    decisions, errors = run_crypto_watchlist(symbols, account_equity=args.equity)

    if args.json:
        print(
            json.dumps(
                {symbol: asdict(decision) for symbol, decision in decisions.items()} | {"_errors": errors},
                indent=2,
                default=_json_default,
            )
        )
        return

    print(f"\n=== Crypto Watchlist: {len(decisions)}/{len(symbols)} succeeded ===")
    print(_format_summary(decisions, errors))


if __name__ == "__main__":
    main()
