"""Explicit, credentialed, GET-only historical US-equity data adapter.

No orders, trading SDK, disk caches, live streams, or implicit network access.
The caller must opt into a request and provide credentials locally. Tests inject
a transport and never contact the provider.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from http.client import HTTPException
import json
import os
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPSHandler, HTTPRedirectHandler, build_opener

import pandas as pd

from research_sr_v4.data import expected_grid
from research_workspace.equity_data import (
    MAX_BARS, SYMBOLS, _validate_and_label,
)
from research_workspace.stage7_events import SEALED_START

API_ENDPOINT = "https://data.alpaca.markets/v2/stocks/bars"
FEEDS = ("iex", "sip")
MAX_PAGES = 8
MAX_PAGE_BYTES = 2_000_000
_CREDENTIAL_PAIRS = (
    ("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
    ("APCA_API_KEY_ID", "APCA_API_SECRET_KEY"),
)
_HTTP_FAILURES = {
    401: ("authentication", "check the local market-data credentials"),
    403: ("entitlement", "check access to the selected feed"),
    429: ("rate_limit", "request limit reached; try again later"),
}


class EquityProviderError(ValueError):
    """Sanitized user-facing provider or dataset failure."""

    def __init__(self, message: str, *, code: str = "invalid_data"):
        super().__init__(message)
        self.code = code


def _safe_credential(value):
    return isinstance(value, str) and 0 < len(value) <= 512 and all(
        33 <= ord(character) <= 126 for character in value
    )


def _configured_credentials():
    """Resolve a complete pair only; aliases from different pairs never mix."""
    any_configured = False
    for key_name, secret_name in _CREDENTIAL_PAIRS:
        key = os.environ.get(key_name)
        secret = os.environ.get(secret_name)
        if _safe_credential(key) and _safe_credential(secret):
            return "configured", (key, secret)
        any_configured |= bool(key or secret)
    return ("incomplete" if any_configured else "missing"), None


def alpaca_credentials_status() -> str:
    """Return configured, incomplete or missing without exposing a credential."""
    return _configured_credentials()[0]


def _parse_session_date(value) -> date:
    try:
        text = str(value)
        parsed = date.fromisoformat(text)
        if parsed.isoformat() == text:
            return parsed
    except (ValueError, TypeError):
        pass
    raise EquityProviderError("Use valid YYYY-MM-DD dates")


def read_configured_alpaca_history(symbol: str, start: str, end: str, *, feed: str, now=None):
    """Explicit request from the terminal using its server-process configuration."""
    first, last = _parse_session_date(start), _parse_session_date(end)
    if last >= date.fromisoformat(SEALED_START):
        raise EquityProviderError("The requested dates reach the sealed research period", code="sealed_range")
    status, credentials = _configured_credentials()
    if credentials is None:
        raise EquityProviderError("A complete local Alpaca Market Data credential pair is required",
                                  code=f"credentials_{status}")
    key, secret = credentials
    return read_alpaca_history(symbol, first.isoformat(), last.isoformat(),
                               feed=feed, api_key=key, api_secret=secret, now=now)


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
        if 500 <= exc.code <= 599:
            code, detail = "unavailable", "market data service unavailable"
        else:
            code, detail = _HTTP_FAILURES.get(exc.code, ("http_error", "request rejected"))
        raise EquityProviderError(f"Provider returned HTTP {exc.code}; {detail}", code=code) from None
    except (URLError, OSError, HTTPException):
        raise EquityProviderError("Market data service unavailable (network or TLS)", code="unavailable") from None
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
    if not _safe_credential(api_key) or not _safe_credential(api_secret):
        code = "credentials_incomplete" if api_key or api_secret else "credentials_missing"
        raise EquityProviderError("Local Alpaca Market Data credentials are required", code=code)
    first, last = _parse_session_date(start), _parse_session_date(end)
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
    rows = []
    for item in items:
        if not isinstance(item, dict) or any(k not in item for k in ("t", "o", "h", "l", "c", "v")):
            raise EquityProviderError("Incomplete provider OHLCV bar")
        try:
            if not isinstance(item["t"], str):
                raise ValueError
            timestamp = pd.Timestamp(item["t"])
            if pd.isna(timestamp) or timestamp.tzinfo is None:
                raise ValueError
            timestamp = timestamp.tz_convert("UTC")
        except (ValueError, TypeError, OverflowError):
            raise EquityProviderError("Invalid provider timestamps") from None
        rows.append({
            "timestamp": timestamp, "open": item["o"], "high": item["h"],
            "low": item["l"], "close": item["c"], "volume": item["v"],
        })
    raw = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    # Keep original order. Duplicate and out-of-order RTH timestamps fail closed.
    eligible = raw.loc[raw.timestamp.isin(grid.timestamp)].reset_index(drop=True)
    outside_count = len(raw) - len(eligible)
    missing_count = int((~grid.timestamp.isin(eligible.timestamp)).sum())
    if missing_count:
        detail = " IEX covers one exchange; select SIP explicitly if available." if feed == "iex" else ""
        raise EquityProviderError(f"Missing {missing_count} expected regular-session bars.{detail}", code="coverage")
    try:
        clean = _validate_and_label(eligible, symbol, now=clock)
    except (ValueError, TypeError, OverflowError):
        # Pandas errors can contain raw provider fields; the UI gets only a safe code/message.
        raise EquityProviderError("Provider bars failed timestamp or OHLCV validation") from None
    if list(clean.timestamp) != list(grid.timestamp):
        raise EquityProviderError("Incomplete requested session coverage", code="coverage")
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
        "expected_bars": len(grid),
        "missing_bars": 0,
        "session_count": session_count,
        "outside_regular_session_bars_excluded": outside_count,
        "retrieved_at_utc": clock.tz_convert("UTC").isoformat(),
        "point_in_time_archive_verified": False,
        "feed_verified": False,
        "orders_enabled": False,
    }
