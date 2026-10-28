"""Explicit, credentialed, GET-only historical US-equity data adapter.

No orders, trading SDK, disk caches, live streams, or implicit network access.
The caller must opt into a request and provide credentials locally. Tests inject
a transport and never contact the provider.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

import pandas as pd

from research_sr_v4.data import expected_grid
from research_workspace.equity_data import (
    MAX_BARS, SYMBOLS, _validate_and_label,
)

API_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
FEEDS = ("iex", "sip")
MAX_PAGES = 8
MAX_PAGE_BYTES = 2_000_000


class EquityProviderError(ValueError):
    """Sanitized user-facing provider or dataset failure."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise EquityProviderError("Provider redirect refused: credentials never follow redirects")


def _api_get(params: dict, key: str, secret: str) -> dict:
    """Allowlisted HTTPS GET with no redirects and no credential-bearing error text."""
    url = API_ENDPOINT + "?" + urlencode(params)
    request = Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }, method="GET")
    opener = build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(request, timeout=20) as response:
            if response.status != 200 or response.url != url:
                raise EquityProviderError("Unexpected provider response")
            if response.headers.get_content_type() != "application/json":
                raise EquityProviderError("Provider did not return JSON")
            payload = response.read(MAX_PAGE_BYTES + 1)
            if len(payload) > MAX_PAGE_BYTES:
                raise EquityProviderError("Provider page exceeded size limit")
    except HTTPError as exc:
        # Never display request URL, headers, bodies, keys, or secrets.
        raise EquityProviderError(f"Provider returned HTTP {exc.code}; check data entitlement and credentials") from None
    except URLError:
        raise EquityProviderError("Market data service unavailable (network or TLS)") from None
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, ValueError):
        raise EquityProviderError("Provider returned invalid JSON") from None
    if not isinstance(parsed, dict):
        raise EquityProviderError("Provider JSON schema mismatch")
    return parsed


def read_alpaca_history(
    symbol: str, start: str, end: str, *,
    feed: str, api_key: str, api_secret: str, now=None, request_page=None,
):
    """Fetch bounded historical bars, discard only non-session bars, validate all RTH.

    A successful HTTPS response establishes an API source, not exchange/audit
    authenticity, contractual redistribution rights, or point-in-time vintage.
    """
    if symbol not in SYMBOLS or feed not in FEEDS:
        raise EquityProviderError("Only SPY/MSFT/QQQ and explicit iex/sip feeds are supported")
    if not api_key or not api_secret:
        raise EquityProviderError("Local Alpaca Market Data credentials are required")
    try:
        first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    except (ValueError, TypeError):
        raise EquityProviderError("Use valid YYYY-MM-DD dates") from None
    if first > last or (last - first).days > 20:
        raise EquityProviderError("Select no more than 21 calendar days in chronological order")
    if first < date(2000, 1, 1) or last > date(2035, 12, 31):
        raise EquityProviderError("Dates must fall within the configured 2000–2035 XNYS calendar")
    grid = expected_grid(first.isoformat(), last.isoformat())
    session_count = int(grid.session.nunique()) if not grid.empty else 0
    if not 1 <= session_count <= 10 or len(grid) > MAX_BARS:
        raise EquityProviderError("Select 1–10 full XNYS sessions (max 5000 bars)")
    clock = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    if clock.tzinfo is None:
        raise EquityProviderError("Validation clock needs an explicit timezone")
    if grid.bar_end.iloc[-1] > clock:
        raise EquityProviderError("Cannot request an unfinished or future full session")

    params = {
        "symbols": symbol, "timeframe": "15Min",
        "start": grid.timestamp.iloc[0].isoformat(),
        "end": grid.bar_end.iloc[-1].isoformat(),
        "feed": feed, "adjustment": "split",
        "sort": "asc", "limit": 1000,
    }
    transport = _api_get if request_page is None else request_page
    items = []
    seen_tokens = set()
    for page_number in range(MAX_PAGES):
        response = transport(params.copy(), api_key, api_secret)
        if not isinstance(response, dict) or not isinstance(response.get("bars"), dict):
            raise EquityProviderError("Provider bars schema mismatch")
        if set(response["bars"]) - {symbol}:
            raise EquityProviderError("Provider returned an unexpected symbol")
        chunk = response["bars"].get(symbol, [])
        if not isinstance(chunk, list):
            raise EquityProviderError("Provider bars must be a list")
        items.extend(chunk)
        if len(items) > MAX_BARS * 4:
            raise EquityProviderError("Too many provider bars in response")
        token = response.get("next_page_token")
        if token is None or token == "":
            break
        if not isinstance(token, str) or len(token) > 2048 or token in seen_tokens:
            raise EquityProviderError("Invalid or repeated provider page token")
        seen_tokens.add(token)
        params["page_token"] = token
    else:
        raise EquityProviderError("Provider pagination exceeds safety limit")
    if not items:
        raise EquityProviderError("No historical bars returned; feed and entitlement may differ")

    rows = []
    for item in items:
        if not isinstance(item, dict) or any(k not in item for k in ("t", "o", "h", "l", "c", "v")):
            raise EquityProviderError("Incomplete provider OHLCV bar")
        rows.append({
            "timestamp": item["t"], "open": item["o"], "high": item["h"],
            "low": item["l"], "close": item["c"], "volume": item["v"],
        })
    raw = pd.DataFrame(rows)
    try:
        timestamps = pd.to_datetime(raw.timestamp, utc=True, errors="raise")
    except (ValueError, TypeError, OverflowError):
        raise EquityProviderError("Invalid provider timestamps") from None
    # Keep original order. Duplicate and out-of-order RTH timestamps fail closed.
    eligible = raw.loc[timestamps.isin(grid.timestamp)].reset_index(drop=True)
    outside_count = len(raw) - len(eligible)
    clean = _validate_and_label(eligible, symbol, now=clock)
    return clean, {
        "symbol": symbol,
        "origin": f"ALPACA HISTORICAL {feed.upper()} API RESPONSE — NOT INDEPENDENTLY VERIFIED",
        "provider": "Alpaca Market Data API",
        "provider_api_response": True,
        "feed": feed,
        "adjustment": "split",
        "currency": "USD",
        "synthetic": False,
        "market": "XNYS / US equities",
        "bar_interval": "15m",
        "bars": len(clean),
        "session_count": session_count,
        "outside_regular_session_bars_excluded": outside_count,
        "retrieved_at_utc": clock.tz_convert("UTC").isoformat(),
        "point_in_time_archive_verified": False,
        "feed_verified": False,
        "orders_enabled": False,
    }
