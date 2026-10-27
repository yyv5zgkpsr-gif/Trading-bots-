"""Train a direction-prediction model for one crypto symbol from historical
daily bars, with a chronological train/validation/test split (never random
— shuffling would leak future bars into training and make the numbers
meaningless).

Needs real network access to fetch price history, so it cannot run inside
this repo's dev sandbox (the same block that stops every other real-data
fetch here). Run it on your own machine:

    pip install -r requirements-ml.txt
    python -m ml.train BTC --period 5y
    python -m ml.train ETH --period 5y --horizon 10 --threshold 0.03

The test-fold metrics are printed but the test fold is never used to pick
a horizon/threshold/model — if you're trying several settings, compare
them on the validation fold and only check the test fold once, at the
end, as a final honesty check. A model that looks great on test after
you've already tuned against it isn't validated, it's overfit to test too.
"""

import argparse
import json
from pathlib import Path

from agents.crypto_technical import to_yfinance_crypto_symbol
from backtest.crypto_runner import MIN_LOOKBACK_DAYS
from data.market_data import fetch_price_history
from ml.dataset import DEFAULT_HORIZON_DAYS, DEFAULT_LABEL_THRESHOLD, build_dataset, chronological_split
from ml.evaluate import evaluate_as_backtest, evaluate_classifier
from ml.model import DirectionModel

DEFAULT_MODEL_DIR = Path(__file__).parent / "models"


def _fold_price_history(price_history, fold_index):
    """Slices `price_history` down to just enough warmup bars (so the
    backtest's SMA50 etc. are ready right at the fold boundary) plus the
    fold's own date range — isolating the backtest's starting_cash and
    equity curve to that fold alone, instead of carrying cumulative
    performance over from whatever came before it in the full series."""
    if len(fold_index) == 0:
        return price_history.iloc[:0]
    start_loc = price_history.index.get_loc(fold_index[0])
    end_loc = price_history.index.get_loc(fold_index[-1])
    warmup_start = max(0, start_loc - MIN_LOOKBACK_DAYS)
    return price_history.iloc[warmup_start : end_loc + 1]


def train_and_evaluate(
    symbol: str,
    price_history,
    horizon: int = DEFAULT_HORIZON_DAYS,
    threshold: float = DEFAULT_LABEL_THRESHOLD,
    train_frac: float = 0.6,
    val_frac: float = 0.2,
) -> dict:
    """Does the actual work, independent of argparse/fetching, so tests can
    drive it with synthetic price history. Returns a dict with the fitted
    model, the split sizes, and both evaluations (classifier metrics +
    a full backtest) on validation and on the held-out test fold."""
    X, y = build_dataset(price_history, horizon=horizon, threshold=threshold)
    if len(X) < 30:
        raise ValueError(
            f"Only {len(X)} labeled rows after dropping warmup/horizon — need more history (try a longer --period)."
        )

    train_idx, val_idx, test_idx = chronological_split(len(X), train_frac, val_frac)
    X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
    X_val, y_val = X.iloc[val_idx], y.iloc[val_idx]
    X_test, y_test = X.iloc[test_idx], y.iloc[test_idx]

    model = DirectionModel()
    model.fit(X_train, y_train)

    # Slice price_history (not X/y) to each fold's own date range (plus just
    # enough warmup) so the backtest's equity curve is isolated to that
    # fold, not cumulative performance carried over from everything before it.
    val_history = _fold_price_history(price_history, X_val.index)
    test_history = _fold_price_history(price_history, X_test.index)

    return {
        "model": model,
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "val_classifier_metrics": evaluate_classifier(model, X_val, y_val) if len(X_val) else None,
        "test_classifier_metrics": evaluate_classifier(model, X_test, y_test) if len(X_test) else None,
        "val_backtest_metrics": evaluate_as_backtest(symbol, model, val_history) if len(X_val) else None,
        "test_backtest_metrics": evaluate_as_backtest(symbol, model, test_history) if len(X_test) else None,
    }


MIN_TRADES_TO_JUDGE = 3  # a handful of lucky trades isn't profitability, it's noise


def is_profitable(result: dict) -> bool:
    """The gate for 'ready to trade automatically': both the validation AND
    the held-out test fold backtests must show a positive return, each
    with enough trades to mean something. Requiring val AND test (not just
    test) makes a single lucky fold harder to pass off as a real edge.
    agents/ml_crypto_debate.py refuses to load a model that fails this."""
    val = result["val_backtest_metrics"]
    test = result["test_backtest_metrics"]
    if val is None or test is None:
        return False
    return (
        val.num_trades >= MIN_TRADES_TO_JUDGE
        and test.num_trades >= MIN_TRADES_TO_JUDGE
        and val.total_return_pct > 0
        and test.total_return_pct > 0
    )


def main():
    parser = argparse.ArgumentParser(description="Train a crypto direction model with a chronological train/val/test split.")
    parser.add_argument("symbol", help="Crypto ticker, e.g. BTC, ETH")
    parser.add_argument("--period", default="5y", help="yfinance period, e.g. 2y, 5y, max (default: 5y)")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON_DAYS, help="forward-return label horizon, in days")
    parser.add_argument("--threshold", type=float, default=DEFAULT_LABEL_THRESHOLD, help="+/- forward return to count as BUY/SELL")
    parser.add_argument("--train-frac", type=float, default=0.6)
    parser.add_argument("--val-frac", type=float, default=0.2)
    parser.add_argument("--out", default=None, help="output .joblib path (default: ml/models/<symbol>_direction.joblib)")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    price_history = fetch_price_history(to_yfinance_crypto_symbol(symbol), period=args.period)

    result = train_and_evaluate(
        symbol,
        price_history,
        horizon=args.horizon,
        threshold=args.threshold,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
    )

    print(f"=== {symbol} direction model: {result['n_train']} train / {result['n_val']} val / {result['n_test']} test rows ===")
    print(f"Horizon: {args.horizon}d, label threshold: +/-{args.threshold * 100:.1f}%")
    print("\n--- Validation fold ---")
    print(json.dumps(result["val_classifier_metrics"], indent=2))
    print(result["val_backtest_metrics"])
    print("\n--- Test fold (held out — only look at this once) ---")
    print(json.dumps(result["test_classifier_metrics"], indent=2))
    print(result["test_backtest_metrics"])

    profitable = is_profitable(result)
    out_path = Path(args.out) if args.out else DEFAULT_MODEL_DIR / f"{symbol.lower()}_direction.joblib"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result["model"].save(out_path)

    meta = {
        "symbol": symbol,
        "period": args.period,
        "horizon": args.horizon,
        "threshold": args.threshold,
        "train_frac": args.train_frac,
        "val_frac": args.val_frac,
        "n_train": result["n_train"],
        "n_val": result["n_val"],
        "n_test": result["n_test"],
        "val_backtest_metrics": vars(result["val_backtest_metrics"]) if result["val_backtest_metrics"] else None,
        "test_backtest_metrics": vars(result["test_backtest_metrics"]) if result["test_backtest_metrics"] else None,
        "profitable": profitable,
    }
    meta_path = out_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"\nSaved model to {out_path}\nSaved metadata to {meta_path}")

    if profitable:
        print(
            f"\nPROFITABLE on both validation and test folds (>= {MIN_TRADES_TO_JUDGE} trades each, "
            "positive return both times). agents/ml_crypto_debate.py will accept this model."
        )
    else:
        print(
            "\nNOT PROFITABLE on this evidence (validation and/or test fold showed a non-positive "
            f"return, or fewer than {MIN_TRADES_TO_JUDGE} trades to judge by) — "
            "agents/ml_crypto_debate.py will REFUSE to load this model for live/paper trading. "
            "Try a different --horizon/--threshold, more --period history, or accept that this "
            "symbol/setup isn't ready to trade automatically yet."
        )


if __name__ == "__main__":
    main()
