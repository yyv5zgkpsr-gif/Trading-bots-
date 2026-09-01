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
  launches *your own* trusted Robinhood MCP server, exposing a `place_order`
  tool) are set. This repository does not include a Robinhood MCP server
  implementation — bring your own and point the env var at it. Without that
  configuration, every run only logs what it *would* have submitted.

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

## Tests

```bash
pytest
```

Tests mock all network calls (`yfinance`, news, LLM, MCP) so they run offline
and deterministically.

## Disclaimer

This is research/education tooling, not financial advice. Trading involves
risk of loss. Review and understand every agent's logic — especially
`risk_manager.py` and `execution.py` — before ever setting `ENABLE_LIVE_TRADING=true`
against a real brokerage account.
