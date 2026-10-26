import pytest

from backtest.crypto_engine import CryptoPortfolio


def test_buy_deducts_cash_and_opens_a_fractional_position():
    portfolio = CryptoPortfolio(starting_cash=10_000)

    portfolio.buy("d1", 0.01, 60_000.0)

    assert portfolio.cash == pytest.approx(10_000 - 600)
    assert portfolio.quantity == 0.01
    assert portfolio.avg_price == 60_000.0
    assert portfolio.trades[-1].action == "BUY"
    assert portfolio.trades[-1].quantity == 0.01


def test_buy_is_capped_by_available_cash():
    portfolio = CryptoPortfolio(starting_cash=300)

    portfolio.buy("d1", 0.01, 60_000.0)  # would cost 600; only 300 available

    assert portfolio.quantity == 0.005
    assert portfolio.cash == 0.0


def test_buy_averages_cost_across_multiple_lots():
    portfolio = CryptoPortfolio(starting_cash=10_000)

    portfolio.buy("d1", 0.01, 50_000.0)
    portfolio.buy("d2", 0.01, 70_000.0)

    assert portfolio.quantity == 0.02
    assert portfolio.avg_price == 60_000.0


def test_sell_cannot_exceed_held_quantity():
    portfolio = CryptoPortfolio(starting_cash=10_000)
    portfolio.buy("d1", 0.01, 60_000.0)

    portfolio.sell("d2", 1.0, 65_000.0)  # only 0.01 held

    assert portfolio.quantity == 0.0
    assert portfolio.trades[-1].quantity == 0.01


def test_sell_credits_cash_and_resets_avg_price_when_flat():
    portfolio = CryptoPortfolio(starting_cash=10_000)
    portfolio.buy("d1", 0.01, 60_000.0)

    portfolio.sell("d2", 0.01, 65_000.0, reason="take_profit")

    assert portfolio.quantity == 0.0
    assert portfolio.avg_price == 0.0
    assert portfolio.cash == 10_000 - 600 + 650
    assert portfolio.trades[-1].reason == "take_profit"


def test_mark_records_an_equity_point():
    portfolio = CryptoPortfolio(starting_cash=10_000)
    portfolio.buy("d1", 0.01, 60_000.0)

    portfolio.mark("d1", 61_000.0)

    assert portfolio.equity_curve[-1].equity == 9_400 + 0.01 * 61_000.0


def test_apply_decision_ignores_hold_and_unapproved():
    from models.schemas import CryptoRiskDecision

    portfolio = CryptoPortfolio(starting_cash=10_000)
    hold = CryptoRiskDecision(
        approved=False,
        action="HOLD",
        position_size_usd=0.0,
        position_size_quantity=0.0,
        stop_loss_price=None,
        take_profit_price=None,
        reasoning="stub",
    )

    portfolio.apply_decision("d1", hold, 60_000.0)

    assert portfolio.cash == 10_000
    assert portfolio.trades == []
