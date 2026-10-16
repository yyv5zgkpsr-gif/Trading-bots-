from backtest.engine import Portfolio


def test_buy_deducts_cash_and_opens_a_position():
    portfolio = Portfolio(starting_cash=10_000)

    portfolio.buy("d1", 10, 100.0)

    assert portfolio.cash == 9_000.0
    assert portfolio.shares == 10
    assert portfolio.avg_price == 100.0
    assert portfolio.trades[-1].action == "BUY"
    assert portfolio.trades[-1].reason == "signal"


def test_buy_is_capped_by_available_cash():
    portfolio = Portfolio(starting_cash=500)

    portfolio.buy("d1", 10, 100.0)  # would cost 1000; only 500 available

    assert portfolio.shares == 5
    assert portfolio.cash == 0.0


def test_buy_averages_cost_across_multiple_lots():
    portfolio = Portfolio(starting_cash=10_000)

    portfolio.buy("d1", 5, 100.0)
    portfolio.buy("d2", 5, 120.0)

    assert portfolio.shares == 10
    assert portfolio.avg_price == 110.0


def test_sell_cannot_exceed_held_shares():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 5, 100.0)

    portfolio.sell("d2", 100, 110.0)  # only 5 held

    assert portfolio.shares == 0
    assert portfolio.trades[-1].shares == 5


def test_sell_credits_cash_and_resets_avg_price_when_flat():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 10, 100.0)

    portfolio.sell("d2", 10, 120.0, reason="take_profit")

    assert portfolio.shares == 0
    assert portfolio.avg_price == 0.0
    assert portfolio.cash == 10_000 - 1000 + 1200
    assert portfolio.trades[-1].reason == "take_profit"


def test_mark_records_an_equity_point():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 10, 100.0)

    portfolio.mark("d1", 105.0)

    assert portfolio.equity_curve[-1].equity == 9_000 + 10 * 105.0


def test_apply_decision_ignores_hold_and_unapproved():
    from models.schemas import RiskDecision

    portfolio = Portfolio(starting_cash=10_000)
    hold = RiskDecision(
        approved=False,
        action="HOLD",
        position_size_usd=0.0,
        position_size_shares=0,
        stop_loss_price=None,
        take_profit_price=None,
        reasoning="stub",
    )

    portfolio.apply_decision("d1", hold, 100.0)

    assert portfolio.cash == 10_000
    assert portfolio.trades == []
