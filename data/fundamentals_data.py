"""Fundamental data access via yfinance's info payload."""

import yfinance as yf


def fetch_fundamentals(ticker: str) -> dict:
    info = yf.Ticker(ticker).info or {}
    return {
        "pe_ratio": info.get("trailingPE"),
        "peg_ratio": info.get("pegRatio") or info.get("trailingPegRatio"),
        "debt_to_equity": info.get("debtToEquity"),
        "revenue_growth": info.get("revenueGrowth"),
        "profit_margin": info.get("profitMargins"),
        "market_cap": info.get("marketCap"),
        "short_name": info.get("shortName") or ticker,
    }
