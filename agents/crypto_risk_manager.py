"""Fixed-fractional sizing for crypto, mirroring agents/risk_manager.py with
two differences: quantity is a fractional coin count (not whole shares), and
the floor for approving a trade is a dollar minimum (MIN_CRYPTO_ORDER_USD)
rather than "at least 1 share" — a tiny position in a $60k asset would
otherwise round down to 0 shares and never trade.
"""

import os

from models.schemas import CryptoRiskDecision, DebateResult, Direction, TechnicalReport

from agents.base import Agent


class CryptoRiskManagerAgent(Agent):
    name = "crypto_risk_manager"

    def __init__(self):
        self.max_position_pct = float(os.environ.get("CRYPTO_MAX_POSITION_PCT", os.environ.get("MAX_POSITION_PCT", "0.05")))
        self.stop_loss_pct = float(
            os.environ.get("CRYPTO_STOP_LOSS_PCT", os.environ.get("DEFAULT_STOP_LOSS_PCT", "0.05"))
        )
        self.take_profit_pct = float(
            os.environ.get("CRYPTO_TAKE_PROFIT_PCT", os.environ.get("DEFAULT_TAKE_PROFIT_PCT", "0.10"))
        )
        self.min_conviction = float(os.environ.get("MIN_CONVICTION", "0.15"))
        self.min_order_usd = float(os.environ.get("MIN_CRYPTO_ORDER_USD", "1.0"))

    def run(self, debate: DebateResult, technical: TechnicalReport, account_equity: float) -> CryptoRiskDecision:
        if debate.recommendation == Direction.NEUTRAL or abs(debate.conviction) < self.min_conviction:
            return CryptoRiskDecision(
                approved=False,
                action="HOLD",
                position_size_usd=0.0,
                position_size_quantity=0.0,
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

        if price <= 0 or position_size_usd < self.min_order_usd:
            return CryptoRiskDecision(
                approved=False,
                action="HOLD",
                position_size_usd=0.0,
                position_size_quantity=0.0,
                stop_loss_price=None,
                take_profit_price=None,
                reasoning=(
                    f"Computed position size (${position_size_usd:.2f}) is below the "
                    f"${self.min_order_usd:.2f} minimum order size; standing aside."
                ),
            )

        quantity = position_size_usd / price

        if action == "BUY":
            stop_loss = round(price * (1 - self.stop_loss_pct), 2)
            take_profit = round(price * (1 + self.take_profit_pct), 2)
        else:
            stop_loss = round(price * (1 + self.stop_loss_pct), 2)
            take_profit = round(price * (1 - self.take_profit_pct), 2)

        reasoning = (
            f"{action} {quantity:.6f} units (~${position_size_usd:,.2f}) sized at "
            f"{self.max_position_pct * 100:.1f}% of equity scaled by conviction "
            f"{conviction_scale:.2f} on ${account_equity:,.2f}; stop {stop_loss}, target {take_profit}."
        )

        return CryptoRiskDecision(
            approved=True,
            action=action,
            position_size_usd=round(position_size_usd, 2),
            position_size_quantity=round(quantity, 8),
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            reasoning=reasoning,
            entry_price=price,
        )
