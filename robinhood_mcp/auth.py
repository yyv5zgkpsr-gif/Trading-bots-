"""Shared Robinhood login, memoized per process.

Stocks and crypto trade under the same Robinhood account/session — logging
in twice would just waste a login attempt (and risk tripping MFA/rate
limits) for no benefit. Whichever broker (``LiveBroker`` or
``CryptoLiveBroker``) is constructed first calls ``ensure_login()``; every
later call is a no-op.
"""

import os

from robinhood_mcp.errors import BrokerError

try:
    import robin_stocks.robinhood as rh
except ImportError:  # pragma: no cover - exercised only when dependency missing
    rh = None

_logged_in = False


def ensure_login() -> None:
    global _logged_in
    if _logged_in:
        return

    if rh is None:
        raise BrokerError(
            "robin_stocks is not installed. Run `pip install robin_stocks` to use ROBINHOOD_MCP_MODE=live."
        )

    username = os.environ.get("ROBINHOOD_USERNAME")
    password = os.environ.get("ROBINHOOD_PASSWORD")
    mfa_code = os.environ.get("ROBINHOOD_MFA_CODE")
    if not username or not password:
        raise BrokerError("ROBINHOOD_USERNAME and ROBINHOOD_PASSWORD must be set to use ROBINHOOD_MCP_MODE=live.")

    login_kwargs = {"username": username, "password": password, "store_session": True}
    if mfa_code:
        login_kwargs["mfa_code"] = mfa_code

    try:
        login_result = rh.login(**login_kwargs)
    except Exception as exc:
        raise BrokerError(f"Robinhood login failed: {exc}") from exc
    if not login_result or not login_result.get("access_token"):
        raise BrokerError("Robinhood login failed: no access token returned. Check credentials/MFA.")

    _logged_in = True
