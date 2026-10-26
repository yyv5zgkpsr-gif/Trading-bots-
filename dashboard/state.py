"""Owns the trading daemon's and exit monitor's lifecycle inside this
single process, so dashboard/app.py's start/stop endpoints can control
both without shelling out to systemctl or managing separate processes.

The trading loop (crypto_daemon.loop_forever, which calls
agents.crypto_orchestrator.CryptoOrchestrator.run) makes blocking network
calls, so it runs in its own background thread — running it directly on
the FastAPI event loop would freeze every HTTP request while a cycle is
in flight. The exit monitor (robinhood_mcp.monitor.loop_forever) is
natively async and already yields control via await, so it runs as a
plain asyncio task on the same event loop FastAPI itself is running on —
no second thread needed for it.
"""

import asyncio
import threading
from dataclasses import dataclass, field

import crypto_daemon
from robinhood_mcp import monitor as exit_monitor


@dataclass
class TradingStatus:
    running: bool
    symbols: list = field(default_factory=list)
    interval_minutes: float = None
    recent_log: list = field(default_factory=list)


@dataclass
class MonitorStatus:
    running: bool
    recent_log: list = field(default_factory=list)


class DashboardState:
    def __init__(self):
        self._trading_thread: threading.Thread = None
        self._trading_stop_event: threading.Event = None
        self._trading_symbols: list = []
        self._trading_interval: float = None

        self._monitor_task: asyncio.Task = None
        self._monitor_stop_event: asyncio.Event = None

    # --- trading daemon (background thread) ---

    def start_trading(self, symbols: list, interval_minutes: float, account_equity: float = None) -> None:
        if self._trading_thread is not None and self._trading_thread.is_alive():
            raise RuntimeError("trading daemon is already running; stop it first")
        self._trading_stop_event = threading.Event()
        self._trading_symbols = symbols
        self._trading_interval = interval_minutes
        self._trading_thread = threading.Thread(
            target=crypto_daemon.loop_forever,
            args=(symbols, interval_minutes, account_equity, self._trading_stop_event),
            daemon=True,
        )
        self._trading_thread.start()

    def stop_trading(self) -> None:
        if self._trading_stop_event is not None:
            self._trading_stop_event.set()
        if self._trading_thread is not None:
            self._trading_thread.join(timeout=10)

    def trading_status(self) -> TradingStatus:
        running = self._trading_thread is not None and self._trading_thread.is_alive()
        return TradingStatus(
            running=running,
            symbols=self._trading_symbols if running else [],
            interval_minutes=self._trading_interval if running else None,
            recent_log=list(crypto_daemon.RECENT_LOG)[-50:],
        )

    # --- exit monitor (asyncio task on the dashboard's own event loop) ---

    def start_monitor(self) -> None:
        if self._monitor_task is not None and not self._monitor_task.done():
            raise RuntimeError("exit monitor is already running; stop it first")
        self._monitor_stop_event = asyncio.Event()
        self._monitor_task = asyncio.create_task(exit_monitor.loop_forever(self._monitor_stop_event))

    async def stop_monitor(self) -> None:
        if self._monitor_stop_event is not None:
            self._monitor_stop_event.set()
        if self._monitor_task is not None:
            try:
                await asyncio.wait_for(self._monitor_task, timeout=10)
            except asyncio.TimeoutError:
                pass

    def monitor_status(self) -> MonitorStatus:
        running = self._monitor_task is not None and not self._monitor_task.done()
        return MonitorStatus(running=running, recent_log=list(exit_monitor.RECENT_LOG)[-50:])
