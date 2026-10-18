from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"


@dataclass
class NewsReport:
    ticker: str
    headlines: list
    catalysts: list
    catalyst_score: float  # -1..1
    summary: str


@dataclass
class TechnicalReport:
    ticker: str
    trend: Direction
    rsi: float
    macd: float
    macd_signal: float
    support: float
    resistance: float
    last_price: float
    technical_score: float  # -1..1
    summary: str


@dataclass
class FundamentalReport:
    ticker: str
    pe_ratio: Optional[float]
    peg_ratio: Optional[float]
    debt_to_equity: Optional[float]
    revenue_growth: Optional[float]
    profit_margin: Optional[float]
    fundamental_score: float  # -1..1
    summary: str


@dataclass
class SentimentReport:
    ticker: str
    sentiment_score: float  # -1..1
    momentum_5d: float
    momentum_20d: float
    summary: str


@dataclass
class MarketRegimeReport:
    regime: Regime
    volatility: float  # VIX level
    spy_trend: Direction
    rate_10y: Optional[float]
    summary: str


@dataclass
class DebateResult:
    bull_thesis: str
    bear_thesis: str
    conviction: float  # -1 (strong bear) .. 1 (strong bull)
    recommendation: Direction


@dataclass
class RiskDecision:
    approved: bool
    action: str  # BUY / SELL / HOLD
    position_size_usd: float
    position_size_shares: int
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    reasoning: str
    entry_price: Optional[float] = None


@dataclass
class CryptoRiskDecision:
    """Same shape as RiskDecision, with a fractional quantity instead of a
    whole-share count — crypto trades in fractions of a coin."""

    approved: bool
    action: str  # BUY / SELL / HOLD
    position_size_usd: float
    position_size_quantity: float
    stop_loss_price: Optional[float]
    take_profit_price: Optional[float]
    reasoning: str
    entry_price: Optional[float] = None


@dataclass
class ExecutionResult:
    executed: bool
    dry_run: bool
    order_id: Optional[str]
    details: str


@dataclass
class CryptoTradeDecision:
    symbol: str
    technical: TechnicalReport
    debate: DebateResult
    risk: CryptoRiskDecision
    execution: Optional[ExecutionResult]


@dataclass
class TradeDecision:
    ticker: str
    news: NewsReport
    technical: TechnicalReport
    fundamental: FundamentalReport
    sentiment: SentimentReport
    regime: MarketRegimeReport
    debate: DebateResult
    risk: RiskDecision
    execution: Optional[ExecutionResult]
