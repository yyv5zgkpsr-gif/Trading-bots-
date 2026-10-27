"""File-backed ledger of per-symbol stop-loss/take-profit levels.

Neither Robinhood's API nor our brokers track "close this if the price moves
against me" anywhere themselves — `place_order`'s stop_loss/take_profit
arguments are otherwise just echoed back and forgotten (see
`robinhood_mcp/live_broker.py`). This ledger is what makes that risk intent
durable so `robinhood_mcp/monitor.py` has something to check positions
against, even if the monitor process restarts.
"""

import json
import os
from pathlib import Path
from threading import Lock

DEFAULT_LEDGER_PATH = Path(__file__).parent / "risk_levels.json"


class RiskLedger:
    def __init__(self, path: str = None):
        self.path = Path(path or os.environ.get("RISK_LEDGER_PATH", str(DEFAULT_LEDGER_PATH)))
        self._lock = Lock()
        self._load()

    def _load(self):
        if self.path.exists():
            with open(self.path) as f:
                self.levels = json.load(f)
        else:
            self.levels = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.levels, f, indent=2)

    def record(self, symbol: str, side: str, stop_loss: float = None, take_profit: float = None):
        if stop_loss is None and take_profit is None:
            return
        with self._lock:
            self.levels[symbol] = {"side": side, "stop_loss": stop_loss, "take_profit": take_profit}
            self._save()

    def clear(self, symbol: str):
        with self._lock:
            if symbol in self.levels:
                del self.levels[symbol]
                self._save()

    def all(self) -> dict:
        with self._lock:
            return dict(self.levels)
