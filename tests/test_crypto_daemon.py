import signal
import threading
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


def test_log_lines_land_in_the_shared_recent_log_ring_buffer():
    crypto_daemon.RECENT_LOG.clear()

    crypto_daemon._log("hello from a test")

    assert any("hello from a test" in line for line in crypto_daemon.RECENT_LOG)


def test_loop_forever_exits_immediately_if_already_stopped_before_the_first_cycle(monkeypatch):
    stop_event = threading.Event()
    stop_event.set()
    cycle_mock = MagicMock()
    monkeypatch.setattr(crypto_daemon, "_run_one_cycle", cycle_mock)

    crypto_daemon.loop_forever(["BTC"], interval_minutes=0.001, stop_event=stop_event)

    cycle_mock.assert_not_called()


def test_loop_forever_survives_a_failing_cycle_and_stops_cleanly_once_signaled(monkeypatch):
    stop_event = threading.Event()
    calls = []

    def fake_cycle(symbols, account_equity=None):
        calls.append(symbols)
        if len(calls) == 1:
            raise RuntimeError("first cycle blew up")
        if len(calls) == 2:
            stop_event.set()  # the next iteration's wait() returns immediately and the loop exits

    monkeypatch.setattr(crypto_daemon, "_run_one_cycle", fake_cycle)

    # A small interval: nothing here tests early-wake-on-signal (that's just
    # threading.Event.wait's documented behavior), only that a failing cycle
    # doesn't stop the loop and that it does stop once stop_event is set.
    crypto_daemon.loop_forever(["BTC"], interval_minutes=0.001, account_equity=12_345.0, stop_event=stop_event)

    # the first cycle's exception didn't stop the loop; setting stop_event after the 2nd cycle did
    assert len(calls) == 2
    assert calls == [["BTC"], ["BTC"]]


def test_run_wires_os_signals_to_a_stop_event_passed_into_loop_forever(monkeypatch):
    handlers = {}
    monkeypatch.setattr(crypto_daemon.signal, "signal", lambda sig, handler: handlers.setdefault(sig, handler))

    captured_stop_event = {}

    def fake_loop_forever(symbols, interval_minutes, account_equity=None, stop_event=None):
        captured_stop_event["event"] = stop_event
        stop_event.set()  # return immediately, as if Ctrl+C had already happened

    monkeypatch.setattr(crypto_daemon, "loop_forever", fake_loop_forever)

    crypto_daemon.run(["BTC"], interval_minutes=1)

    assert signal.SIGINT in handlers
    assert signal.SIGTERM in handlers
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert captured_stop_event["event"].is_set()
