"""Binance Square research helper: top 24h USDT movers (read-only).

Source: https://data-api.binance.vision/api/v3/ticker/24hr — the public
Binance market-data mirror. (api.binance.com is geo-blocked from some
networks, so this module always uses data-api.binance.vision.)
"""

from __future__ import annotations

from .http import get_json

TICKER_URL = "https://data-api.binance.vision/api/v3/ticker/24hr"
DEFAULT_MIN_QUOTE_VOLUME_USD = 5_000_000
DEFAULT_LIMIT = 10


def filter_sort_tickers(
    tickers: list[dict],
    min_quote_volume: float = DEFAULT_MIN_QUOTE_VOLUME_USD,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Keep USDT pairs above the volume floor, sorted by 24h % change desc.

    Each returned row is a dict with symbol, price, change_pct and
    quote_volume (all floats except symbol). Rows with unparseable numbers
    are skipped, never guessed.
    """
    rows: list[dict] = []
    for item in tickers:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", ""))
        if not symbol.endswith("USDT"):
            continue
        try:
            price = float(item["lastPrice"])
            change_pct = float(item["priceChangePercent"])
            quote_volume = float(item["quoteVolume"])
        except (KeyError, TypeError, ValueError):
            continue
        if quote_volume < min_quote_volume:
            continue
        rows.append(
            {
                "symbol": symbol,
                "price": price,
                "change_pct": change_pct,
                "quote_volume": quote_volume,
            }
        )
    rows.sort(key=lambda row: row["change_pct"], reverse=True)
    return rows[:limit]


def fetch_top_movers(
    min_quote_volume: float = DEFAULT_MIN_QUOTE_VOLUME_USD,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Fetch live 24h tickers and return the top movers."""
    payload = get_json(TICKER_URL)
    if not isinstance(payload, list):
        raise ValueError("ticker endpoint did not return a list")
    return filter_sort_tickers(payload, min_quote_volume, limit)
