# Trading Bots — Multi-Agent Trading Orchestrator

A pipeline of specialized agents that research a ticker from several angles, debate
it, size a risk-bounded trade, and (optionally) execute it — with real order
placement gated behind an explicit opt-in and routed exclusively through a
Robinhood MCP server.

```
                    ORCHESTRATOR AGENT
                    decides what to study
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                 ▼
   NEWS / CATALYST     TECHNICAL AGENT   FUNDAMENTAL AGENT
          │                 │                 │
          └────────────┬────┴─────┬───────────┘
                        ▼          ▼
                 SENTIMENT     MARKET REGIME
                 AGENT         AGENT
                        │          │
                        └────┬─────┘
                             ▼
                     DEBATE AGENTS
                    BULL vs BEAR thesis
                             ▼
                    RISK MANAGER AGENT
                position / stop / exposure
                             ▼
                    EXECUTION AGENT
                   Robinhood MCP only
                             ▼
                        ROBINHOOD
```

## Layout

| Path | Purpose |
| --- | --- |
| `agents/orchestrator.py` | Wires the whole pipeline together. |
| `agents/news_catalyst.py` | Google News RSS headlines + SEC EDGAR 8-K filings → catalyst score. |
| `agents/technical.py` | RSI, MACD, trend vs. moving averages, support/resistance. |
| `agents/fundamental.py` | P/E, PEG, debt/equity, revenue growth, margins. |
| `agents/sentiment.py` | Price momentum blended with news tone. |
| `agents/market_regime.py` | SPY trend, VIX volatility regime, 10Y yield. |
| `agents/debate.py` | LLM-driven bull vs. bear theses, netted into one conviction score. |
| `agents/risk_manager.py` | Fixed-fractional position sizing, stop-loss/take-profit, approve/HOLD. |
| `agents/execution.py` | Places (or dry-runs) the order via a Robinhood MCP server. |
| `data/` | Data access: yfinance wrappers, news/filing fetchers. |
| `models/schemas.py` | Dataclasses passed between agents. |
| `main.py` | CLI: `python main.py AAPL`. |
| `robinhood_mcp/` | The bundled Robinhood MCP server (paper-trading by default; optional live mode). |
| `robinhood_mcp/monitor.py` | Standalone exit-monitoring loop for live-mode stop-loss/take-profit (stocks and crypto). |
| `backtest/` | Backtests the technical+regime+risk-manager slice of the strategy against historical data. |
| `agents/crypto_*.py`, `crypto_main.py` | The parallel crypto pipeline — see **Crypto** below. |

## Design notes

- **LLM use is optional.** Agents that reason qualitatively (news, fundamentals,
  debate) call `ANTHROPIC_API_KEY` via the `anthropic` SDK when configured, and
  fall back to deterministic, rule-based scoring otherwise. The pipeline runs
  end-to-end either way.
- **No paid data APIs required.** News comes from Google News RSS; SEC filings
  from the free EDGAR full-text search API; prices/fundamentals from `yfinance`.
- **Execution is Robinhood-MCP-only, dry-run by default.** `ExecutionAgent`
  never calls a brokerage API directly. It only places a live order when both
  `ENABLE_LIVE_TRADING=true` and `ROBINHOOD_MCP_COMMAND` (the command that
  launches an MCP server exposing `place_order`/`get_account`/`get_positions`
  tools) are set. Without that configuration, every run only logs what it
  *would* have submitted.
- **A Robinhood MCP server ships in `robinhood_mcp/`** (run it with
  `ROBINHOOD_MCP_COMMAND=python -m robinhood_mcp.server`). It has two modes,
  selected by `ROBINHOOD_MCP_MODE`:
  - `paper` (default): a local, file-backed simulated ledger
    (`robinhood_mcp/paper_state.json`, path configurable via
    `PAPER_STATE_PATH`) seeded with `PAPER_STARTING_CASH`. No brokerage
    account or credentials involved — orders fill instantly at the price the
    risk manager computed.
  - `live`: places **real** orders on a **real** Robinhood account via the
    unofficial `robin_stocks` library (`pip install -r requirements-live.txt`).
    Requires `ROBINHOOD_USERNAME`/`ROBINHOOD_PASSWORD` (and `ROBINHOOD_MFA_CODE`
    if your account needs a TOTP code); the server refuses to start if login
    fails rather than silently falling back to paper mode. Stop-loss/take-profit
    are recorded in the order response for your own reference only — Robinhood's
    API has no atomic bracket order, so no separate stop order is placed for you.
    See **Exit monitoring** below for the alternative this repo actually ships.
- **Exit monitoring for live-mode stops (`robinhood_mcp/monitor.py`).** Every
  `place_order` call with a `stop_loss`/`take_profit` is recorded in a small
  file-backed ledger (`robinhood_mcp/risk_ledger.py`); a `sell` clears it.
  `python -m robinhood_mcp.monitor` is a separate long-lived process that polls
  that ledger against live quotes (`get_quote`, live mode only) every
  `MONITOR_POLL_SECONDS` (default 30s) and submits a market sell the instant a
  level is breached. It talks to the exact same MCP server as everything
  else — same `ROBINHOOD_MCP_COMMAND`. It is polling-based (not a live price
  stream), always exits the full position at market, and protects nothing
  while it isn't running — run it under something that restarts it (systemd,
  a supervisor) for real unattended use. There is nothing to monitor in paper
  mode: `get_quote` has no real market data feed there and errors on purpose.
- **Account equity for position sizing** is resolved in order: an explicit
  `--equity` CLI flag, then live equity from the Robinhood MCP server's
  `get_account` tool (only queried when live trading is configured), then the
  `DEFAULT_ACCOUNT_EQUITY` env var.

## Crypto

```bash
python crypto_main.py BTC
python crypto_main.py ETH --equity 5000 --json
```

Same safety pattern as stocks: dry-run unless `ENABLE_LIVE_TRADING=true` and
`ROBINHOOD_MCP_COMMAND` are both set, and that command still defaults to
`ROBINHOOD_MCP_MODE=paper` (no real money). Crypto trades under the *same*
Robinhood login as stocks — `robinhood_mcp/auth.py` logs in once and both
`LiveBroker` and `CryptoLiveBroker` share it — but with its own buying-power
balance, its own paper cash pool (`CRYPTO_PAPER_STARTING_CASH`, separate
from `PAPER_STARTING_CASH`), and fractional quantities instead of whole
shares.

**The crypto pipeline is deliberately narrower than the stock one:**
`agents/crypto_orchestrator.py` is Technical → Debate → Risk Manager →
Execution, with no news/fundamental/sentiment agent and no market-regime
check (SPY/VIX don't mean anything for an asset that trades 24/7) — so
`agents/crypto_debate.py`'s conviction is the technical score alone. That's
a smaller pipeline on purpose, not a degraded one; extend it the same way
the stock side extended from technical-only before fundamentals/sentiment
existed, if you want more signal.

**Exit monitoring and the backtester both already cover crypto with no
changes**, because they're symbol-agnostic: `robinhood_mcp/risk_ledger.py`
and `robinhood_mcp/monitor.py` don't care whether a symbol is a stock or
`BTC`, and `backtest/runner.py`'s technical+risk-manager loop works on any
OHLC history you hand it — fetch crypto history via `yfinance`'s
`BTC-USD`/`ETH-USD` convention (see `agents/crypto_technical.py` for the
symbol mapping Robinhood's bare-ticker API needs vs. yfinance's) and pass
it to `backtest.runner.run_backtest` the same way.

**Unverified against a real account, same honesty as live_broker.py:**
`robinhood_mcp/crypto_live_broker.py` is built from `robin_stocks`'
documented crypto API (inspected from the installed package, not exercised
against a real login — this environment has no network path to Robinhood).
Review it, especially the position-field mapping, before trusting it with
real money.

## Backtesting before you tune for trade frequency

Before loosening `MIN_CONVICTION` or scanning more tickers to get *more*
trades, find out whether the strategy you already have is actually
profitable — more trades is not the same axis as more profit, and on a
Robinhood account under $25k the Pattern Day Trader rule caps you at 3 day
trades per rolling 5 business days regardless of what the code does.

```bash
python -m backtest.runner AAPL --period 2y
python -m backtest.runner AAPL --period 5y --equity 25000
```

This replays `agents/technical.py` + `agents/market_regime.py` +
`agents/risk_manager.py` day by day against historical daily bars, deciding
with data only through each day's close and executing at the next day's
open (no lookahead), checking the recorded stop-loss/take-profit against
each day's High/Low. It reports total return, number of round-trip trades,
win rate, average win/loss, profit factor, max drawdown, and an annualized
Sharpe ratio.

**What it does *not* validate:** `agents/news_catalyst.py`,
`agents/fundamental.py`, `agents/sentiment.py`, and the LLM-driven bull/bear
debate in `agents/debate.py` are excluded — today's headlines aren't
reproducible as of a past date, and nobody wants one LLM call per symbol per
historical day. So a backtest result describes the technical+regime+
risk-manager slice of the strategy, not the full live pipeline; live
performance will differ, in either direction. Use it to sanity-check
`MAX_POSITION_PCT`, `MIN_CONVICTION`, `DEFAULT_STOP_LOSS_PCT`, and
`DEFAULT_TAKE_PROFIT_PCT` against real numbers before changing them, not as
a guarantee of live results.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY / risk knobs as desired
```

## Usage

```bash
python main.py AAPL
python main.py AAPL --equity 25000 --json
```

## Trying the full pipeline against the bundled paper broker

```bash
export ENABLE_LIVE_TRADING=true
export ROBINHOOD_MCP_COMMAND="python -m robinhood_mcp.server"
python main.py AAPL
```

This still involves no real money: `ROBINHOOD_MCP_MODE` defaults to `paper`,
so orders fill against the local simulated ledger. `main.py` itself never
knows the difference — it always talks to `ExecutionAgent`, which always talks
to whatever `ROBINHOOD_MCP_COMMAND` points at.

## Tests

```bash
pytest
```

Tests mock all network calls (`yfinance`, news, LLM) so they run offline and
deterministically. The `robinhood_mcp` paper brokers (stock and crypto) and
MCP tool wiring are exercised directly (no network), `agents/execution.py`
and `agents/crypto_execution.py` are additionally covered by driving the
real MCP server over stdio end to end, and `backtest/` is covered against
synthetic OHLC data (its `run_backtest` accepts pre-built DataFrames for
exactly this).

## Disclaimer

This is research/education tooling, not financial advice. Trading involves
risk of loss. Review and understand every agent's logic — especially
`risk_manager.py`/`crypto_risk_manager.py`, `agents/execution.py`/
`agents/crypto_execution.py`, and `robinhood_mcp/live_broker.py`/
`robinhood_mcp/crypto_live_broker.py` — before ever setting
`ROBINHOOD_MCP_MODE=live` against a real brokerage account. The crypto
live broker in particular has not been exercised against a real account
(see **Crypto** above).
