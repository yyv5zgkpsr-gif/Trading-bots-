import os

from models.schemas import CryptoTradeDecision

from agents.crypto_debate import CryptoDebateAgent
from agents.crypto_execution import CryptoExecutionAgent
from agents.crypto_risk_manager import CryptoRiskManagerAgent
from agents.crypto_technical import CryptoTechnicalAgent
from agents.ml_crypto_debate import MLCryptoDebateAgent


class CryptoOrchestrator:
    """Coordinates the crypto pipeline for one symbol:

    Technical -> Debate (technical score, or a trained ML model's
    prediction when USE_ML_SIGNAL=true — see agents/ml_crypto_debate.py)
    -> Risk Manager -> Execution (Robinhood MCP, crypto tools, dry-run by
    default).

    Narrower than Orchestrator (agents/orchestrator.py) on purpose: there is
    no news/fundamental/sentiment/regime pipeline for crypto yet, so this
    pipeline is shorter, not degraded.
    """

    def __init__(self):
        self.technical_agent = CryptoTechnicalAgent()
        if os.environ.get("USE_ML_SIGNAL", "false").lower() == "true":
            self.debate_agent = MLCryptoDebateAgent()
        else:
            self.debate_agent = CryptoDebateAgent()
        self.risk_agent = CryptoRiskManagerAgent()
        self.execution_agent = CryptoExecutionAgent()

    def run(self, symbol: str, account_equity: float = None) -> CryptoTradeDecision:
        if account_equity is None:
            account_equity = self.execution_agent.get_account_balance()
        if account_equity is None:
            account_equity = float(os.environ.get("CRYPTO_DEFAULT_ACCOUNT_EQUITY", "10000"))

        technical = self.technical_agent.run(symbol)
        debate = self.debate_agent.run(symbol, technical)
        risk = self.risk_agent.run(debate, technical, account_equity)
        execution = self.execution_agent.run(symbol, risk)

        return CryptoTradeDecision(
            symbol=symbol,
            technical=technical,
            debate=debate,
            risk=risk,
            execution=execution,
        )
