from types import SimpleNamespace

import watchlist


class _FakeOrchestrator:
    """Stands in for agents.orchestrator.Orchestrator: records every call and
    returns a canned result or raises, per symbol, without touching any
    agent, network call, or the real Orchestrator at all."""

    def __init__(self, results: dict):
        self.results = results
        self.calls = []

    def run(self, symbol, account_equity=None):
        self.calls.append((symbol, account_equity))
        result = self.results[symbol]
        if isinstance(result, Exception):
            raise result
        return result


def test_run_watchlist_runs_every_symbol_and_collects_decisions(monkeypatch):
    fake = _FakeOrchestrator({"AAPL": "decision-aapl", "MSFT": "decision-msft"})
    monkeypatch.setattr(watchlist, "Orchestrator", lambda: fake)

    decisions, errors = watchlist.run_watchlist(["AAPL", "MSFT"], account_equity=10_000)

    assert decisions == {"AAPL": "decision-aapl", "MSFT": "decision-msft"}
    assert errors == {}
    assert fake.calls == [("AAPL", 10_000), ("MSFT", 10_000)]


def test_run_watchlist_continues_past_a_failing_symbol(monkeypatch):
    fake = _FakeOrchestrator(
        {"AAPL": "decision-aapl", "BADTICKER": ValueError("no data for BADTICKER"), "MSFT": "decision-msft"}
    )
    monkeypatch.setattr(watchlist, "Orchestrator", lambda: fake)

    decisions, errors = watchlist.run_watchlist(["AAPL", "BADTICKER", "MSFT"])

    assert decisions == {"AAPL": "decision-aapl", "MSFT": "decision-msft"}
    assert errors == {"BADTICKER": "no data for BADTICKER"}
    # the failure didn't stop MSFT from running
    assert [c[0] for c in fake.calls] == ["AAPL", "BADTICKER", "MSFT"]


def test_load_symbols_merges_positional_and_file_and_dedupes(tmp_path):
    watchlist_file = tmp_path / "watchlist.txt"
    watchlist_file.write_text("MSFT\n# a comment\nNVDA\nAAPL\n")

    args = SimpleNamespace(tickers=["aapl", "nvda"], file=str(watchlist_file))
    symbols = watchlist._load_symbols(args)

    assert symbols == ["AAPL", "NVDA", "MSFT"]  # positional first, then file, duplicates dropped


def test_format_summary_reports_decisions_and_failures():
    decision = SimpleNamespace(
        debate=SimpleNamespace(conviction=0.42),
        risk=SimpleNamespace(action="BUY", approved=True, position_size_shares=10, reasoning="strong uptrend"),
    )

    output = watchlist._format_summary({"AAPL": decision}, {"BADTICKER": "no data"})

    assert "AAPL" in output
    assert "BUY" in output
    assert "10 sh" in output
    assert "BADTICKER" in output
    assert "FAILED" in output
    assert "no data" in output
