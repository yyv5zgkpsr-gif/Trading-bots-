"""Continuous crypto trading loop: runs crypto_watchlist.py's pipeline on a
fixed interval, forever, logging every cycle's decisions.

Crypto trades 24/7 and Robinhood's Pattern Day Trader rule applies only to
stocks/options, not crypto — unlike the stock pipeline there's no reason to
run this a few times a day by hand. It's meant to run under a process
supervisor (systemd, Docker's restart policy, ...) so it comes back up on
its own after a crash or a host reboot. See deploy/ for ready-made systemd
units and a Dockerfile/compose file.

Run this alongside robinhood_mcp/monitor.py whenever ROBINHOOD_MCP_MODE=live:
this script only places entries; the monitor is what actually enforces the
stop-loss/take-profit on whatever it opens (Robinhood has no bracket
orders). Neither one does the other's job, and running only this one means
every position opened is unprotected until it's closed by the next cycle's
signal, which is not the same as a stop-loss.

Usage:
    python crypto_daemon.py BTC ETH SOL
    python crypto_daemon.py --file crypto_watchlist.txt --interval-minutes 15
"""

import argparse
import signal
import threading
from collections import deque
from datetime import datetime, timezone

from dotenv import load_dotenv

from crypto_watchlist import _load_symbols, run_crypto_watchlist

DEFAULT_INTERVAL_MINUTES = 15.0

# Every log line, newest last, for dashboard/state.py to read without tailing
# stdout/journald. Bounded so a long-running daemon can't grow this forever.
RECENT_LOG: deque = deque(maxlen=500)


def _log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    RECENT_LOG.append(line)


def _run_one_cycle(symbols: list[str], account_equity: float = None) -> None:
    decisions, errors = run_crypto_watchlist(symbols, account_equity=account_equity)
    for symbol, decision in decisions.items():
        r = decision.risk
        execution_details = decision.execution.details if decision.execution else "no execution attempted"
        _log(
            f"{symbol}: action={r.action} approved={r.approved} conviction={decision.debate.conviction} "
            f"quantity={r.position_size_quantity:g} -- {execution_details}"
        )
    for symbol, message in errors.items():
        _log(f"{symbol}: cycle FAILED: {message}")


def loop_forever(
    symbols: list[str],
    interval_minutes: float,
    account_equity: float = None,
    stop_event: threading.Event = None,
) -> None:
    """Runs cycles forever until `stop_event` is set, waiting
    `interval_minutes` between them (interruptibly — a set stop_event ends
    the wait immediately instead of finishing out the interval). A cycle
    that raises is logged and skipped — one bad cycle must never take the
    whole daemon down, since nothing else is watching these positions
    while it's dead.

    Takes a `stop_event` instead of installing signal handlers itself so it
    can run anywhere, including a background thread (dashboard/state.py) —
    signal.signal only works in the main thread. `run()` below is the
    signal-wired entry point for standalone CLI use."""
    stop_event = stop_event or threading.Event()

    _log(f"Crypto trading daemon starting: {symbols}, every {interval_minutes:.1f} min.")
    while not stop_event.is_set():
        try:
            _run_one_cycle(symbols, account_equity)
        except Exception as exc:  # noqa: BLE001 - see docstring
            _log(f"Cycle failed: {exc}")

        stop_event.wait(timeout=interval_minutes * 60)
    _log("Crypto trading daemon stopped.")


def run(symbols: list[str], interval_minutes: float, account_equity: float = None) -> None:
    """CLI entry point: wires SIGINT/SIGTERM to a stop_event, then runs
    loop_forever. Ctrl+C to stop."""
    stop_event = threading.Event()

    def _handle_signal(signum, frame):
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    loop_forever(symbols, interval_minutes, account_equity, stop_event=stop_event)


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run the crypto pipeline across a watchlist forever, on a fixed interval."
    )
    parser.add_argument("symbols", nargs="*", help="Crypto tickers, e.g. BTC ETH SOL")
    parser.add_argument("--file", help="Path to a newline-separated file of extra symbols (# comments allowed)")
    parser.add_argument("--interval-minutes", type=float, default=DEFAULT_INTERVAL_MINUTES)
    parser.add_argument(
        "--equity", type=float, default=None, help="See crypto_watchlist.py's module docstring before setting this"
    )
    args = parser.parse_args()

    symbols = _load_symbols(args)
    if not symbols:
        parser.error("no symbols given: pass them as arguments, via --file, or both")

    run(symbols, args.interval_minutes, account_equity=args.equity)


if __name__ == "__main__":
    main()
