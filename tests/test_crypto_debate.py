from models.schemas import Direction, TechnicalReport
from agents.crypto_debate import CryptoDebateAgent


def _technical(score: float) -> TechnicalReport:
    return TechnicalReport(
        ticker="BTC",
        trend=Direction.BULLISH,
        rsi=55.0,
        macd=0.5,
        macd_signal=0.2,
        support=59_000.0,
        resistance=61_000.0,
        last_price=60_000.0,
        technical_score=score,
        summary="stub",
    )


def test_strong_positive_score_is_bullish():
    debate = CryptoDebateAgent().run("BTC", _technical(0.5))

    assert debate.recommendation == Direction.BULLISH
    assert debate.conviction == 0.5


def test_strong_negative_score_is_bearish():
    debate = CryptoDebateAgent().run("BTC", _technical(-0.5))

    assert debate.recommendation == Direction.BEARISH


def test_weak_score_is_neutral():
    debate = CryptoDebateAgent().run("BTC", _technical(0.05))

    assert debate.recommendation == Direction.NEUTRAL
