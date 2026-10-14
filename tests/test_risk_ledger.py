from robinhood_mcp.risk_ledger import RiskLedger


def test_record_requires_at_least_one_level(tmp_path):
    ledger = RiskLedger(path=str(tmp_path / "levels.json"))

    ledger.record("AAPL", "buy", stop_loss=None, take_profit=None)

    assert ledger.all() == {}


def test_record_and_read_back(tmp_path):
    ledger = RiskLedger(path=str(tmp_path / "levels.json"))

    ledger.record("AAPL", "buy", stop_loss=95.0, take_profit=110.0)

    assert ledger.all() == {"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}}


def test_clear_removes_entry(tmp_path):
    ledger = RiskLedger(path=str(tmp_path / "levels.json"))
    ledger.record("AAPL", "buy", stop_loss=95.0, take_profit=110.0)

    ledger.clear("AAPL")

    assert ledger.all() == {}


def test_clear_is_a_noop_for_unknown_symbol(tmp_path):
    ledger = RiskLedger(path=str(tmp_path / "levels.json"))

    ledger.clear("AAPL")  # must not raise

    assert ledger.all() == {}


def test_state_persists_across_instances(tmp_path):
    path = str(tmp_path / "levels.json")
    RiskLedger(path=path).record("AAPL", "buy", stop_loss=95.0, take_profit=110.0)

    reloaded = RiskLedger(path=path)

    assert reloaded.all() == {"AAPL": {"side": "buy", "stop_loss": 95.0, "take_profit": 110.0}}
