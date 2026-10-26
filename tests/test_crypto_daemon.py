import signal
from types import SimpleNamespace
from unittest.mock import MagicMock

import crypto_daemon


class _FakeDecision:
    def __init__(self, action, approved, conviction, quantity, details):
        self.risk = SimpleNamespace(action=action, approved=approved, position_size_quantity=quantity)
        self.debate = SimpleNamespace(conviction=conviction)
        self.execution = SimpleNamespace(details=details)


def test_run_one_cycle_logs_each_decision_and_each_error(monkeypatch, capsys):
    decision = _FakeDecision("BUY", True, 0.3, 0.01, "[DRY RUN] would buy")
    monkeypatch.setattr(
        crypto_daemon,
        "run_crypto_watchlist",
        lambda symbols, account_equity=None: ({"BTC": decision}, {"FAKECOIN": "boom"}),
    )

    crypto_daemon._run_one_cycle(["BTC", "FAKECOIN"])

    out = capsys.readouterr().out
    assert "BTC: action=BUY approved=True conviction=0.3 quantity=0.01" in out
    assert "[DRY RUN] would buy" in out
    assert "FAKECOIN: cycle FAILED: boom" in out


def test_run_exits_immediately_if_already_signaled_before_the_first_cycle(monkeypatch):
    def fake_signal(sig, handler):
        if sig == signal.SIGINT:
            handler(sig, None)  # simulate Ctrl+C having already arrived the instant it's registered

    monkeypatch.setattr(crypto_daemon.signal, "signal", fake_signal)
    cycle_mock = MagicMock()
    monkeypatch.setattr(crypto_daemon, "_run_one_cycle", cycle_mock)

    crypto_daemon.run(["BTC"], interval_minutes=0.001)

    cycle_mock.assert_not_called()


def test_run_survives_a_failing_cycle_and_stops_cleanly_once_signaled(monkeypatch):
    handlers = {}
    monkeypatch.setattr(crypto_daemon.signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))
    monkeypatch.setattr(crypto_daemon.time, "sleep", lambda seconds: None)

    calls = []

    def fake_cycle(symbols, account_equity=None):
        calls.append(symbols)
        if len(calls) == 1:
            raise RuntimeError("first cycle blew up")
        if len(calls) == 2:
            handlers[signal.SIGINT](signal.SIGINT, None)  # Ctrl+C arrives after the 2nd cycle starts running

    monkeypatch.setattr(crypto_daemon, "_run_one_cycle", fake_cycle)

    crypto_daemon.run(["BTC"], interval_minutes=5, account_equity=12_345.0)

    # the first cycle's exception didn't stop the loop; the signal after the 2nd cycle did
    assert len(calls) == 2
    assert calls == [["BTC"], ["BTC"]]
