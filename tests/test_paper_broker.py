import pytest

from robinhood_mcp.errors import BrokerError
from robinhood_mcp.paper_broker import PaperBroker


@pytest.fixture
def broker(tmp_path):
    return PaperBroker(state_path=str(tmp_path / "state.json"))


def test_starts_with_configured_cash_and_no_positions(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPER_STARTING_CASH", "5000")
    broker = PaperBroker(state_path=str(tmp_path / "state.json"))

    account = broker.get_account()

    assert account["mode"] == "paper"
    assert account["cash"] == 5000.0
    assert account["equity"] == 5000.0
    assert broker.get_positions() == []


def test_buy_deducts_cash_and_opens_a_position(broker):
    result = broker.place_order("AAPL", "buy", 10, price=100.0)

    assert result["state"] == "filled"
    assert result["fill_price"] == 100.0

    account = broker.get_account()
    assert account["cash"] == pytest.approx(10_000 - 1_000)
    assert account["equity"] == pytest.approx(10_000)

    positions = broker.get_positions()
    assert positions == [{"symbol": "AAPL", "quantity": 10, "average_buy_price": 100.0}]


def test_buy_rejected_when_cash_insufficient(broker):
    with pytest.raises(BrokerError, match="Insufficient paper cash"):
        broker.place_order("AAPL", "buy", 1000, price=100.0)


def test_sell_more_than_held_is_rejected(broker):
    broker.place_order("AAPL", "buy", 5, price=100.0)

    with pytest.raises(BrokerError, match="only 5 held"):
        broker.place_order("AAPL", "sell", 10, price=110.0)


def test_sell_closes_position_and_credits_cash(broker):
    broker.place_order("AAPL", "buy", 10, price=100.0)
    broker.place_order("AAPL", "sell", 10, price=120.0)

    account = broker.get_account()
    assert account["cash"] == pytest.approx(10_000 + 200)  # bought at 100, sold at 120
    assert broker.get_positions() == []


def test_state_persists_across_instances(tmp_path):
    state_path = str(tmp_path / "state.json")
    PaperBroker(state_path=state_path).place_order("AAPL", "buy", 10, price=100.0)

    reloaded = PaperBroker(state_path=state_path)

    assert reloaded.get_positions() == [{"symbol": "AAPL", "quantity": 10, "average_buy_price": 100.0}]


def test_place_order_requires_positive_price(broker):
    with pytest.raises(BrokerError, match="positive `price`"):
        broker.place_order("AAPL", "buy", 10)
