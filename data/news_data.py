"""News / catalyst data access. Uses free, keyless sources (Google News RSS and the
public SEC EDGAR full-text search API) so the pipeline runs without paid API keys.
Both calls degrade to an empty result on any network/parse failure."""

import feedparser
import requests

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
SEC_FULLTEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


def fetch_news_headlines(ticker: str, company_name: str = None, limit: int = 10) -> list[dict]:
    query = requests.utils.quote(company_name or ticker)
    try:
        feed = feedparser.parse(GOOGLE_NEWS_RSS.format(query=query))
    except Exception:
        return []

    headlines = []
    for entry in feed.entries[:limit]:
        source = getattr(entry, "source", None)
        headlines.append(
            {
                "title": entry.get("title", ""),
                "published": entry.get("published", ""),
                "link": entry.get("link", ""),
                "source": source.get("title", "") if isinstance(source, dict) else "",
            }
        )
    return headlines


def fetch_sec_filings(ticker: str, limit: int = 5) -> list[dict]:
    try:
        resp = requests.get(
            SEC_FULLTEXT_SEARCH_URL,
            params={"q": ticker, "forms": "8-K"},
            headers={"User-Agent": "trading-bot-research contact@example.com"},
            timeout=10,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])[:limit]
    except Exception:
        return []

    filings = []
    for hit in hits:
        source = hit.get("_source", {})
        filings.append(
            {
                "form": source.get("root_form"),
                "filed": source.get("file_date"),
                "title": (source.get("display_names") or [""])[0],
            }
        )
    return filings
