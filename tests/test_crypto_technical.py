from unittest.mock import patch

import numpy as np
import pandas as pd

from agents.crypto_technical import CryptoTechnicalAgent, to_yfinance_crypto_symbol


def test_to_yfinance_crypto_symbol_appends_usd_suffix():
    assert to_yfinance_crypto_symbol("btc") == "BTC-USD"
    assert to_yfinance_crypto_symbol("ETH") == "ETH-USD"


def test_to_yfinance_crypto_symbol_is_idempotent():
    assert to_yfinance_crypto_symbol("BTC-USD") == "BTC-USD"


def _ohlc(n=60, start=100.0, end=150.0):
    close = pd.Series(np.linspace(start, end, n))
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close})


def test_run_fetches_the_yfinance_symbol_but_reports_the_robinhood_ticker():
    df = _ohlc()

    with patch("agents.crypto_technical.fetch_price_history", return_value=df) as mock_fetch:
        report = CryptoTechnicalAgent().run("BTC")

    mock_fetch.assert_called_once_with("BTC-USD", period="6mo")
    assert report.ticker == "BTC"
    assert report.last_price == df["Close"].iloc[-1]
