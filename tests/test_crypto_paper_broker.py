import pytest

from robinhood_mcp.errors import BrokerError
from robinhood_mcp.crypto_paper_broker import CryptoPaperBroker


@pytest.fixture
def broker(tmp_path):
    return CryptoPaperBroker(state_path=str(tmp_path / "crypto_state.json"))


def test_starts_with_configured_cash_and_no_positions(monkeypatch, tmp_path):
    monkeypatch.setenv("CRYPTO_PAPER_STARTING_CASH", "5000")
    broker = CryptoPaperBroker(state_path=str(tmp_path / "crypto_state.json"))

    account = broker.get_account()

    assert account["mode"] == "paper"
    assert account["cash"] == 5000.0
    assert broker.get_positions() == []


def test_buy_accepts_fractional_quantity(broker):
    result = broker.place_order("BTC", "buy", 0.015, price=60_000.0)

    assert result["state"] == "filled"
    assert result["quantity"] == 0.015

    account = broker.get_account()
    assert account["cash"] == pytest.approx(10_000 - 900)

    positions = broker.get_positions()
    assert positions == [{"symbol": "BTC", "quantity": 0.015, "average_buy_price": 60_000.0}]


def test_buy_rejected_when_cash_insufficient(broker):
    with pytest.raises(BrokerError, match="Insufficient paper cash"):
        broker.place_order("BTC", "buy", 1.0, price=60_000.0)


def test_sell_more_than_held_is_rejected(broker):
    broker.place_order("ETH", "buy", 2.0, price=2_000.0)

    with pytest.raises(BrokerError, match="only 2.0 held"):
        broker.place_order("ETH", "sell", 5.0, price=2_100.0)


def test_sell_closes_position_and_credits_cash(broker):
    broker.place_order("ETH", "buy", 2.0, price=2_000.0)
    broker.place_order("ETH", "sell", 2.0, price=2_200.0)

    account = broker.get_account()
    assert account["cash"] == pytest.approx(10_000 + 400)
    assert broker.get_positions() == []


def test_partial_sell_leaves_a_smaller_position(broker):
    broker.place_order("ETH", "buy", 2.0, price=2_000.0)
    broker.place_order("ETH", "sell", 0.5, price=2_000.0)

    positions = broker.get_positions()
    assert positions == [{"symbol": "ETH", "quantity": 1.5, "average_buy_price": 2_000.0}]


def test_state_persists_across_instances(tmp_path):
    state_path = str(tmp_path / "crypto_state.json")
    CryptoPaperBroker(state_path=state_path).place_order("BTC", "buy", 0.01, price=60_000.0)

    reloaded = CryptoPaperBroker(state_path=state_path)

    assert reloaded.get_positions() == [{"symbol": "BTC", "quantity": 0.01, "average_buy_price": 60_000.0}]


def test_place_order_requires_positive_price(broker):
    with pytest.raises(BrokerError, match="positive `price`"):
        broker.place_order("BTC", "buy", 0.01)


def test_get_quote_errors_in_paper_mode(broker):
    with pytest.raises(BrokerError, match="paper mode"):
        broker.get_quote("BTC")
