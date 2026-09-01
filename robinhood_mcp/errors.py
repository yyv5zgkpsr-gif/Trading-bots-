class BrokerError(RuntimeError):
    """Raised for any broker-level failure: insufficient funds, a rejected order,
    an oversized sell, a login failure, etc. Callers surface this as a tool-call
    error rather than letting the process crash."""
