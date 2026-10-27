"""ML-backed replacement for agents/crypto_debate.py's conviction: loads a
model trained by ml/train.py and uses its prediction instead of the raw
technical score. Same run(symbol, technical) signature as
CryptoDebateAgent, so agents/crypto_orchestrator.py can swap one for the
other with no other changes.

Refuses to load a model that ml/train.py's own held-out backtest didn't
judge profitable (see ml/train.py's is_profitable): "trained" is not the
bar for live/paper trading, "trained AND backtested profitably on data it
never trained on" is. This is a deliberate fail-closed default — a wrong
or missing metadata file, or one saying the model wasn't profitable,
stops the agent from being constructed at all rather than quietly trading
on an unvalidated model.
"""

import json
import os
from pathlib import Path

from models.schemas import DebateResult, Direction, TechnicalReport

from agents.base import Agent
from agents.crypto_technical import to_yfinance_crypto_symbol
from agents.debate import CONVICTION_THRESHOLD
from data.market_data import fetch_price_history
from ml.features import build_feature_frame
from ml.model import DirectionModel

DEFAULT_MODEL_DIR = Path(__file__).parent.parent / "ml" / "models"
DEFAULT_FEATURE_PERIOD = "1y"  # plenty of warmup for SMA50 + rolling windows, fast to fetch


class ModelNotReadyError(RuntimeError):
    """A model exists but ml/train.py's own backtest didn't judge it
    profitable, or it was never evaluated at all (no metadata file)."""


def _model_dir() -> Path:
    configured = os.environ.get("ML_MODEL_DIR")
    return Path(configured) if configured else DEFAULT_MODEL_DIR


def _require_profitable_metadata(model_path: Path) -> dict:
    meta_path = model_path.with_suffix(".json")
    if not meta_path.exists():
        raise ModelNotReadyError(
            f"{meta_path} is missing — train this model with `python -m ml.train` first, which writes "
            "the backtest metadata this agent requires before it will load any model."
        )
    meta = json.loads(meta_path.read_text())
    if not meta.get("profitable"):
        raise ModelNotReadyError(
            f"{model_path} was trained but ml/train.py's own validation+test backtest did not judge it "
            "profitable (see its 'profitable' field in "
            f"{meta_path}) — refusing to use it for live/paper trading. Retrain with different "
            "settings, or don't set USE_ML_SIGNAL for this symbol yet."
        )
    return meta


class MLCryptoDebateAgent(Agent):
    name = "ml_crypto_debate"

    def __init__(self, model_dir: Path = None):
        self.model_dir = model_dir or _model_dir()
        self._models: dict[str, DirectionModel] = {}  # lazily loaded, keyed by symbol

    def _load(self, symbol: str) -> DirectionModel:
        if symbol not in self._models:
            model_path = self.model_dir / f"{symbol.lower()}_direction.joblib"
            if not model_path.exists():
                raise ModelNotReadyError(
                    f"{model_path} does not exist — train it with `python -m ml.train {symbol}` first."
                )
            _require_profitable_metadata(model_path)
            self._models[symbol] = DirectionModel.load(model_path)
        return self._models[symbol]

    def run(self, symbol: str, technical: TechnicalReport) -> DebateResult:
        model = self._load(symbol)

        price_history = fetch_price_history(to_yfinance_crypto_symbol(symbol), period=DEFAULT_FEATURE_PERIOD)
        latest_features = build_feature_frame(price_history).iloc[[-1]]

        if latest_features.isna().any(axis=None):
            conviction = 0.0  # not enough history yet for every feature's warmup window
        else:
            conviction = float(model.predict_conviction(latest_features).iloc[0])

        if conviction > CONVICTION_THRESHOLD:
            recommendation = Direction.BULLISH
        elif conviction < -CONVICTION_THRESHOLD:
            recommendation = Direction.BEARISH
        else:
            recommendation = Direction.NEUTRAL

        thesis = (
            f"{symbol}: ML model conviction {round(conviction, 3)} (technical score for reference: "
            f"{technical.technical_score}, {technical.summary})."
        )

        return DebateResult(
            bull_thesis=thesis,
            bear_thesis=thesis,
            conviction=round(conviction, 3),
            recommendation=recommendation,
        )
