from backtest.engine import Portfolio
from backtest.metrics import compute_metrics


def test_no_trades_reports_flat_zero_metrics():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.mark("d1", 10_000)

    metrics = compute_metrics(portfolio)

    assert metrics.num_trades == 0
    assert metrics.win_rate_pct == 0.0
    assert metrics.profit_factor == 0.0
    assert metrics.total_return_pct == 0.0


def test_single_winning_round_trip():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 10, 100.0)
    portfolio.sell("d2", 10, 110.0)
    portfolio.mark("d2", 10_000 + 100)

    metrics = compute_metrics(portfolio)

    assert metrics.num_trades == 1
    assert metrics.num_wins == 1
    assert metrics.num_losses == 0
    assert metrics.win_rate_pct == 100.0
    assert metrics.avg_win_pct == 10.0
    assert metrics.profit_factor == float("inf")
    assert metrics.total_return_pct == 1.0


def test_single_losing_round_trip():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 10, 100.0)
    portfolio.sell("d2", 10, 90.0)
    portfolio.mark("d2", 10_000 - 100)

    metrics = compute_metrics(portfolio)

    assert metrics.num_wins == 0
    assert metrics.num_losses == 1
    assert metrics.win_rate_pct == 0.0
    assert metrics.avg_loss_pct == -10.0
    assert metrics.profit_factor == 0.0


def test_partial_sells_produce_one_round_trip_per_matched_lot():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 10, 100.0)
    portfolio.sell("d2", 4, 110.0)
    portfolio.sell("d3", 6, 120.0)

    metrics = compute_metrics(portfolio)

    assert metrics.num_trades == 2
    assert metrics.num_wins == 2


def test_fifo_matches_multiple_buy_lots_against_one_sell():
    portfolio = Portfolio(starting_cash=10_000)
    portfolio.buy("d1", 5, 100.0)
    portfolio.buy("d2", 5, 120.0)
    portfolio.sell("d3", 10, 130.0)

    metrics = compute_metrics(portfolio)

    # two lots closed: (130-100)/100 = +30%, (130-120)/120 = +8.33%
    assert metrics.num_trades == 2
    assert metrics.num_wins == 2


def test_max_drawdown_from_equity_curve():
    from backtest.engine import EquityPoint

    portfolio = Portfolio(starting_cash=100)
    portfolio.equity_curve = [EquityPoint(d, e) for d, e in [("d1", 100), ("d2", 110), ("d3", 90), ("d4", 95)]]

    metrics = compute_metrics(portfolio)

    assert metrics.max_drawdown_pct == round((90 - 110) / 110 * 100, 2)
