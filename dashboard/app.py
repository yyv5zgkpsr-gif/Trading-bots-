"""Mobile-friendly status/control page for the crypto trading daemon and
exit monitor, run as a single FastAPI service — so both can be started,
stopped, and watched from your phone instead of SSHing in.

Requires DASHBOARD_TOKEN to be set: every /api/* route checks it as a
bearer token, since start/stop here controls real trading, and the app
refuses to start at all without one (see require_token()). Reaching this
from your phone over the internet still needs HTTPS in front of it (a
reverse proxy) or, simpler and more private, a Tailscale/VPN connection
between your phone and the server — see deploy/README.md. Without either,
that token travels in the clear.

Run with:
    uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dashboard.state import DashboardState

load_dotenv()

DASHBOARD_TOKEN = os.environ.get("DASHBOARD_TOKEN")
if not DASHBOARD_TOKEN:
    raise RuntimeError(
        "DASHBOARD_TOKEN is not set. This dashboard's /api/* routes control real trading "
        "(start/stop), so it refuses to start without a token to gate them. Set DASHBOARD_TOKEN "
        "in .env to any long random string before running this."
    )

STATIC_DIR = Path(__file__).parent / "static"

state = DashboardState()


def _symbols_from_env() -> list[str]:
    raw = os.environ.get("DASHBOARD_SYMBOLS", "")
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """AUTO_START_MONITOR/AUTO_START_TRADING let this come back up already
    running after a reboot or crash, instead of needing a tap from your
    phone every time — the phone controls stay available as a kill switch
    and for manual restarts regardless."""
    if os.environ.get("AUTO_START_MONITOR", "false").lower() == "true":
        state.start_monitor()
    if os.environ.get("AUTO_START_TRADING", "false").lower() == "true":
        symbols = _symbols_from_env()
        if symbols:
            interval = float(os.environ.get("DASHBOARD_INTERVAL_MINUTES", "15"))
            state.start_trading(symbols, interval)
    yield


app = FastAPI(title="Crypto Trading Dashboard", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def require_token(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    token = auth[len("Bearer ") :].strip() if auth.startswith("Bearer ") else ""
    if token != DASHBOARD_TOKEN:
        raise HTTPException(status_code=401, detail="missing or invalid token")


class StartTradingRequest(BaseModel):
    symbols: list[str]
    interval_minutes: float = 15.0
    equity: Optional[float] = None


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def get_status(_: None = Depends(require_token)):
    return {
        "trading": vars(state.trading_status()),
        "monitor": vars(state.monitor_status()),
    }


@app.post("/api/trading/start")
def start_trading(body: StartTradingRequest, _: None = Depends(require_token)):
    symbols = [s.upper() for s in body.symbols]
    if not symbols:
        raise HTTPException(status_code=400, detail="no symbols given")
    try:
        state.start_trading(symbols, body.interval_minutes, account_equity=body.equity)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@app.post("/api/trading/stop")
def stop_trading(_: None = Depends(require_token)):
    state.stop_trading()
    return {"ok": True}


@app.post("/api/monitor/start")
async def start_monitor(_: None = Depends(require_token)):
    # Must be async: state.start_monitor() calls asyncio.create_task(), which
    # needs a running event loop. FastAPI runs a sync `def` route in a worker
    # thread (no event loop there) but an `async def` one directly on its
    # own event loop thread, which is what create_task() needs here.
    try:
        state.start_monitor()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@app.post("/api/monitor/stop")
async def stop_monitor(_: None = Depends(require_token)):
    await state.stop_monitor()
    return {"ok": True}
