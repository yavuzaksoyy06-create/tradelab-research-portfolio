"""User-supplied US equity bar inspection; separate from frozen V4.1 research.

This module never fetches data, creates orders, or marks a CSV as provider verified.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import hashlib
import math

import pandas as pd

from research_sr_v4.data import validate, expected_grid, DataQualityError
from research_sr_v4.causal import build_features

SYMBOLS = ('SPY', 'MSFT', 'QQQ')
REQUIRED = ('timestamp', 'open', 'high', 'low', 'close', 'volume')
MAX_BYTES = 5_000_000
MAX_BARS = 5_000


def _validate_symbol(symbol: str) -> None:
    if symbol not in SYMBOLS:
        raise ValueError('Supported symbols: SPY, MSFT, QQQ')


def _validate_and_label(raw: pd.DataFrame, symbol: str, *, now=None) -> pd.DataFrame:
    _validate_symbol(symbol)
    if set(raw.columns) != set(REQUIRED) or len(raw.columns) != len(REQUIRED):
        raise ValueError('CSV columns must be timestamp,open,high,low,close,volume')
    if raw.empty or len(raw) > MAX_BARS:
        raise ValueError('Dataset must contain 1–5000 complete 15-minute bars')
    if raw.isna().any().any():
        raise ValueError('Missing values are not accepted')
    try:
        parsed = [pd.Timestamp(item) for item in raw['timestamp']]
        if any(t.tzinfo is None or pd.isna(t) for t in parsed):
            raise ValueError('Each timestamp needs an explicit timezone offset or Z')
        stamps = pd.DatetimeIndex(pd.to_datetime(parsed, utc=True))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Timestamps must be valid and timezone-aware') from exc
    if stamps.has_duplicates or not stamps.is_monotonic_increasing:
        raise ValueError('Timestamps must be unique and strictly increasing')
    ny_dates = stamps.tz_convert('America/New_York')
    start, end = ny_dates[0].date().isoformat(), ny_dates[-1].date().isoformat()
    # V4 enforces XNYS grids, coherent OHLCV, and completed-bar availability.
    return validate(raw[list(REQUIRED)], start, end, now=now, allow_outside_rth=False)


def read_uploaded_csv(payload: bytes, symbol: str, *, now=None):
    """Validate structural consistency; do not assert authenticity or source rights."""
    _validate_symbol(symbol)
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError('Upload a nonempty CSV of at most 5 MB')
    try:
        source = pd.read_csv(BytesIO(payload), dtype={'timestamp': 'string'})
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError('Unable to read CSV') from exc
    frame = _validate_and_label(source, symbol, now=now)
    return frame, {
        'symbol': symbol,
        'origin': 'USER-SUPPLIED CSV — PROVIDER NOT VERIFIED',
        'synthetic': False,
        'market': 'XNYS / US equities',
        'bar_interval': '15m',
        'input_sha256': hashlib.sha256(payload).hexdigest(),
        'bars': len(frame),
        'session_count': int(frame.session.nunique()),
        'point_in_time_archive_verified': False,
        'feed_verified': False,
        'orders_enabled': False,
    }


def synthetic_fixture(symbol='SPY'):
    """Deterministic complete-session educational example; NOT market prices."""
    _validate_symbol(symbol)
    grid = expected_grid('2026-10-05', '2026-10-16')
    rows = []
    prev = 100.0
    for i, row in enumerate(grid.itertuples(index=False)):
        close = 100 + 0.018 * i + 1.65 * math.sin(i / 5.5) + 0.52 * math.sin(i / 17.0)
        opening = prev
        high = max(opening, close) + 0.18 + 0.04 * (i % 3)
        low = min(opening, close) - 0.17 - 0.03 * (i % 4)
        rows.append(dict(timestamp=row.timestamp.isoformat(), open=round(opening, 4),
                         high=round(high, 4), low=round(low, 4),
                         close=round(close, 4), volume=100000 + (i % 13) * 6000))
        prev = close
    frame = _validate_and_label(pd.DataFrame(rows), symbol, now=datetime.now(timezone.utc))
    return frame, {
        'symbol': symbol,
        'origin': 'SYNTHETIC EDUCATIONAL DATA — NOT REAL MARKET PRICES',
        'synthetic': True,
        'market': 'XNYS calendar / synthetic OHLCV',
        'bar_interval': '15m',
        'bars': len(frame),
        'session_count': int(frame.session.nunique()),
        'point_in_time_archive_verified': False,
        'feed_verified': False,
        'orders_enabled': False,
    }


def analyze_prefix(frame: pd.DataFrame, visible_count: int):
    """Recompute from visible completed bars only; no future-derived levels."""
    if isinstance(visible_count, bool) or not isinstance(visible_count, int) or not 1 <= visible_count <= len(frame):
        raise ValueError('Replay cursor outside available complete bars')
    prefix = frame.iloc[:visible_count].copy()
    features = build_features(prefix)
    return prefix, features
