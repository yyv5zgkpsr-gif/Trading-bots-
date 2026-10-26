# Deploying the crypto bot for unattended operation

Two processes need to run continuously, on a machine with real network
access (not this repo's dev sandbox):

- **`crypto_daemon.py`** — places entries, on an interval, forever.
- **`robinhood_mcp.monitor`** — enforces stop-loss/take-profit on whatever
  `crypto_daemon.py` opens. Robinhood has no bracket orders, so nothing
  else does this job; running the daemon without the monitor means every
  position opened is unprotected the moment it's filled.

Both read `ROBINHOOD_MCP_MODE` from the environment and spawn their own
copy of `robinhood_mcp/server.py` as a local subprocess — there's no
separate "MCP server" process to deploy, and no networking between the
two services.

## Option A: systemd (bare VPS, no Docker)

```bash
sudo useradd -r -m trading
sudo mkdir -p /opt/trading-bots
sudo chown trading:trading /opt/trading-bots
# clone the repo into /opt/trading-bots as the `trading` user, then:
cd /opt/trading-bots
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-live.txt
cp .env.example .env   # fill in credentials and set ENABLE_LIVE_TRADING etc.

sudo cp deploy/systemd/crypto-trading-daemon.service /etc/systemd/system/
sudo cp deploy/systemd/crypto-exit-monitor.service /etc/systemd/system/
# edit the symbol list in crypto-trading-daemon.service's ExecStart first
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-trading-daemon crypto-exit-monitor
sudo journalctl -u crypto-trading-daemon -f   # tail logs
```

Both units run as the same `User=`, so they naturally share `~/.tokens`
(where `robin_stocks` caches its login session and device token) and
`robinhood_mcp/risk_levels.json` — no extra configuration needed here.
`Restart=on-failure` brings either one back up if it crashes or the host
reboots.

## Option B: Docker Compose

```bash
cp .env.example .env   # fill in credentials and set ENABLE_LIVE_TRADING etc.
# edit the symbol list in docker-compose.yml's trading-daemon command first
docker compose up -d
docker compose logs -f trading-daemon
```

Unlike systemd, each container normally gets its own isolated filesystem —
so `docker-compose.yml` explicitly mounts a **shared** `robinhood_session`
volume at `/root/.tokens` in both services. Without it, each container
would log in to Robinhood as a separate "new device," and Robinhood may
challenge each one independently with its own email/SMS verification.
`robinhood_state` persists `robinhood_mcp/paper_state.json`,
`crypto_paper_state.json`, and `risk_levels.json` across container
restarts (they'd otherwise reset every redeploy).

## Before enabling either one for real

1. Run `python -m backtest.crypto_runner <symbol>` and
   `python -m backtest.optimize <symbol> --asset-class crypto` on a machine
   with real network access, and set `MIN_CONVICTION` /
   `CRYPTO_STOP_LOSS_PCT` / `CRYPTO_TAKE_PROFIT_PCT` / `MAX_POSITION_PCT`
   in `.env` from that, not the untuned defaults.
2. Start with `ROBINHOOD_MCP_MODE=paper` — both services run their exact
   real code path (MCP server, monitor, order placement) against the
   bundled paper ledger, zero real-money risk. Confirm orders fill,
   `get_risk_levels` populates, and the monitor exits a position on a
   breach, before touching `ROBINHOOD_MCP_MODE=live`.
3. Switch to `live` with a small `MAX_POSITION_PCT` and a short symbol
   list first. Review `robinhood_mcp/crypto_live_broker.py` yourself
   first — it's built from `robin_stocks`'s documented API but has not
   been exercised against a real account (see the README's **Crypto**
   section).
