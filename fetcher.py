"""
Data fetcher – calls TradingView scanner API for all symbols.
Maintains rolling history for volume and OI comparison.
"""

import logging
import requests
from collections import deque, defaultdict
import config

logger = logging.getLogger(__name__)

# Columns we request from TradingView scanner
_TV_COLUMNS = [
    "close",           # Current / latest bar close
    "open",            # Bar open
    "high",            # Bar high
    "low",             # Bar low
    "volume",          # Volume
    "change",          # % change from prev close
    "change_abs",      # Absolute price change
    "open_interest",   # Open Interest (futures only)
    "VWAP",            # Volume-Weighted Average Price
    "RSI",             # RSI momentum indicator
    "Recommend.All",   # TradingView overall recommendation (-1 to 1)
]

# Rolling history stores keyed by symbol key (e.g. "MCX_AL")
_vol_hist = defaultdict(lambda: deque(maxlen=config.HISTORY_MAXLEN))
_oi_hist  = defaultdict(lambda: deque(maxlen=config.HISTORY_MAXLEN))


def _vol_ratio(key: str, current_vol: float) -> float:
    """Return current volume / rolling average volume."""
    hist = list(_vol_hist[key])
    if len(hist) < 3 or current_vol <= 0:
        return 1.0
    avg = sum(hist) / len(hist)
    return round(current_vol / avg if avg > 0 else 1.0, 2)


def _oi_change_pct(key: str, current_oi: float) -> float:
    """Return % change of OI vs previous recorded value."""
    hist = list(_oi_hist[key])
    if len(hist) < 2 or current_oi <= 0:
        return 0.0
    prev = hist[-1]
    if prev <= 0:
        return 0.0
    return round((current_oi - prev) / prev * 100, 2)


def fetch_market_data(symbols: dict) -> dict:
    """
    Fetch all symbols from TradingView scanner API.

    Parameters
    ----------
    symbols : dict  {key: "EXCHANGE:SYMBOL", ...}

    Returns
    -------
    dict  {key: {field: value, ...}, ...}
    """
    tickers = list(symbols.values())
    ticker_to_key = {v: k for k, v in symbols.items()}

    try:
        resp = requests.post(
            config.TV_SCANNER_URL,
            json={
                "symbols": {"tickers": tickers},
                "columns": _TV_COLUMNS,
            },
            headers={
                "Content-Type": "application/json",
                "Referer": "https://www.tradingview.com/",
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                ),
            },
            timeout=config.REQUEST_TIMEOUT_SEC,
        )
        resp.raise_for_status()
        raw_items = resp.json().get("data", [])
    except Exception as exc:
        logger.error("TradingView fetch failed: %s", exc)
        return {}

    result: dict = {}

    for item in raw_items:
        ticker = item["s"]
        key    = ticker_to_key.get(ticker, ticker)
        values = item.get("d", [])

        parsed: dict = {}
        for i, col in enumerate(_TV_COLUMNS):
            raw = values[i] if i < len(values) else None
            try:
                parsed[col] = float(raw) if raw is not None else 0.0
            except (TypeError, ValueError):
                parsed[col] = raw  # keep string values like Recommend.All

        # --- update rolling history BEFORE computing derived fields ---
        close  = parsed.get("close",  0.0) or 0.0
        volume = parsed.get("volume", 0.0) or 0.0
        oi     = parsed.get("open_interest", 0.0) or 0.0

        if volume > 0:
            _vol_hist[key].append(volume)
        if oi > 0:
            _oi_hist[key].append(oi)

        # --- derived fields ---
        parsed["vol_ratio"]      = _vol_ratio(key, volume)
        parsed["oi_change_pct"]  = _oi_change_pct(key, oi) if oi > 0 else 0.0
        parsed["ticker"]         = ticker

        result[key] = parsed

    logger.debug("Fetched %d symbols", len(result))
    return result
