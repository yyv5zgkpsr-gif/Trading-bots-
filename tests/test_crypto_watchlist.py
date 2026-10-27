from types import SimpleNamespace

import crypto_watchlist


class _FakeCryptoOrchestrator:
    """Stands in for agents.crypto_orchestrator.CryptoOrchestrator: records
    every call and returns a canned result or raises, per symbol, without
    touching any agent, network call, or the real orchestrator at all."""

    def __init__(self, results: dict):
        self.results = results
        self.calls = []

    def run(self, symbol, account_equity=None):
        self.calls.append((symbol, account_equity))
        result = self.results[symbol]
        if isinstance(result, Exception):
            raise result
        return result


def test_run_crypto_watchlist_runs_every_symbol_and_collects_decisions(monkeypatch):
    fake = _FakeCryptoOrchestrator({"BTC": "decision-btc", "ETH": "decision-eth"})
    monkeypatch.setattr(crypto_watchlist, "CryptoOrchestrator", lambda: fake)

    decisions, errors = crypto_watchlist.run_crypto_watchlist(["BTC", "ETH"], account_equity=10_000)

    assert decisions == {"BTC": "decision-btc", "ETH": "decision-eth"}
    assert errors == {}
    assert fake.calls == [("BTC", 10_000), ("ETH", 10_000)]


def test_run_crypto_watchlist_continues_past_a_failing_symbol(monkeypatch):
    fake = _FakeCryptoOrchestrator(
        {"BTC": "decision-btc", "FAKECOIN": ValueError("no data for FAKECOIN"), "ETH": "decision-eth"}
    )
    monkeypatch.setattr(crypto_watchlist, "CryptoOrchestrator", lambda: fake)

    decisions, errors = crypto_watchlist.run_crypto_watchlist(["BTC", "FAKECOIN", "ETH"])

    assert decisions == {"BTC": "decision-btc", "ETH": "decision-eth"}
    assert errors == {"FAKECOIN": "no data for FAKECOIN"}
    assert [c[0] for c in fake.calls] == ["BTC", "FAKECOIN", "ETH"]


def test_load_symbols_merges_positional_and_file_and_dedupes(tmp_path):
    watchlist_file = tmp_path / "crypto_watchlist.txt"
    watchlist_file.write_text("ETH\n# a comment\nSOL\nBTC\n")

    args = SimpleNamespace(symbols=["btc", "sol"], file=str(watchlist_file))
    symbols = crypto_watchlist._load_symbols(args)

    assert symbols == ["BTC", "SOL", "ETH"]


def test_format_summary_reports_decisions_and_failures():
    decision = SimpleNamespace(
        debate=SimpleNamespace(conviction=0.42),
        risk=SimpleNamespace(action="BUY", approved=True, position_size_quantity=0.015, reasoning="strong uptrend"),
    )

    output = crypto_watchlist._format_summary({"BTC": decision}, {"FAKECOIN": "no data"})

    assert "BTC" in output
    assert "BUY" in output
    assert "0.015" in output
    assert "FAKECOIN" in output
    assert "FAILED" in output
    assert "no data" in output
