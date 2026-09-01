import os

from models.schemas import DebateResult, Direction, RiskDecision, TechnicalReport

from agents.base import Agent


class RiskManagerAgent(Agent):
    """Turns a directional debate outcome into a sized, risk-bounded order (or a HOLD).

    Sizing is fixed-fractional: at most ``MAX_POSITION_PCT`` of account equity,
    scaled down further by how weak the debate's conviction is. Stops/targets are
    simple fixed percentages off the last traded price.
    """

    name = "risk_manager"

    def __init__(self):
        self.max_position_pct = float(os.environ.get("MAX_POSITION_PCT", "0.05"))
        self.stop_loss_pct = float(os.environ.get("DEFAULT_STOP_LOSS_PCT", "0.05"))
        self.take_profit_pct = float(os.environ.get("DEFAULT_TAKE_PROFIT_PCT", "0.10"))
        self.min_conviction = float(os.environ.get("MIN_CONVICTION", "0.15"))

    def run(self, debate: DebateResult, technical: TechnicalReport, account_equity: float) -> RiskDecision:
        if debate.recommendation == Direction.NEUTRAL or abs(debate.conviction) < self.min_conviction:
            return RiskDecision(
                approved=False,
                action="HOLD",
                position_size_usd=0.0,
                position_size_shares=0,
                stop_loss_price=None,
                take_profit_price=None,
                reasoning=(
                    f"Conviction {debate.conviction} is below the {self.min_conviction} threshold "
                    "(or the debate was neutral); standing aside."
                ),
            )

        action = "BUY" if debate.recommendation == Direction.BULLISH else "SELL"
        conviction_scale = min(abs(debate.conviction), 1.0)
        position_size_usd = account_equity * self.max_position_pct * conviction_scale
        price = technical.last_price
        shares = int(position_size_usd // price) if price > 0 else 0

        if shares <= 0:
            return RiskDecision(
                approved=False,
                action="HOLD",
                position_size_usd=0.0,
                position_size_shares=0,
                stop_loss_price=None,
                take_profit_price=None,
                reasoning="Computed position size rounds down to 0 shares at the current price; standing aside.",
            )

        if action == "BUY":
            stop_loss = round(price * (1 - self.stop_loss_pct), 2)
            take_profit = round(price * (1 + self.take_profit_pct), 2)
        else:
            stop_loss = round(price * (1 + self.stop_loss_pct), 2)
            take_profit = round(price * (1 - self.take_profit_pct), 2)

        reasoning = (
            f"{action} {shares} shares (~${shares * price:,.2f}) sized at "
            f"{self.max_position_pct * 100:.1f}% of equity scaled by conviction "
            f"{conviction_scale:.2f} on ${account_equity:,.2f}; stop {stop_loss}, target {take_profit}."
        )

        return RiskDecision(
            approved=True,
            action=action,
            position_size_usd=round(shares * price, 2),
            position_size_shares=shares,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            reasoning=reasoning,
            entry_price=price,
        )
