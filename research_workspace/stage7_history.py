"""Explicit bounded GET-only collection; never automatically invoked by the UI."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from io import BytesIO
import pandas as pd
from research_sr_v4.data import expected_grid
from research_workspace.equity_data import REQUIRED, SYMBOLS, MAX_BYTES, _validate_and_label
from research_workspace.equity_provider import read_alpaca_history, EquityProviderError
from research_workspace.stage7_events import SEALED_START, VERSION, validated_history


def collect_history(symbol, start, end, *, feed, api_key, api_secret,
                    explicit_download=False, request_page=None):
    if explicit_download is not True:
        raise ValueError("Explicit user-initiated download required")
    if symbol not in SYMBOLS or feed not in ("iex", "sip"):
        raise ValueError("Explicit supported symbol and a single feed required")
    first, last = pd.Timestamp(start), pd.Timestamp(end)
    if first > last or first < pd.Timestamp("2000-01-01") or last >= pd.Timestamp(SEALED_START):
        raise ValueError("Invalid range or sealed period requested")
    if (last - first).days > 200:
        raise ValueError("Maximum 200 calendar days")
    grid = expected_grid(first.date().isoformat(), last.date().isoformat())
    sessions = list(dict.fromkeys(grid.session))
    if not 1 <= len(sessions) <= 120:
        raise ValueError("Collection requires 1–120 complete sessions")
    frames, receipts = [], []
    for offset in range(0, len(sessions), 10):
        batch = sessions[offset:offset + 10]
        try:
            frame, meta = read_alpaca_history(
                symbol, batch[0], batch[-1], feed=feed, api_key=api_key,
                api_secret=api_secret, request_page=request_page)
        except Exception:
            # Provider bodies/headers or custom transports must not leak secrets.
            raise EquityProviderError(
                "Historical batch failed: coverage, entitlement, rate limit or network. "
                "No automatic retry; no partial dataset accepted.") from None
        expected = grid.loc[grid.session.isin(batch), "timestamp"]
        if list(frame.timestamp) != list(expected):
            raise EquityProviderError("Incomplete requested session coverage; dataset rejected")
        frames.append(frame)
        receipts.append({"first_session": batch[0], "last_session": batch[-1],
                         "bars": len(frame), "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                         "outside_rth_excluded": meta["outside_regular_session_bars_excluded"]})
    clean = _validate_and_label(pd.concat(frames, ignore_index=True)[list(REQUIRED)], symbol)
    return clean, {"schema": VERSION, "symbol": symbol, "feed": feed,
                   "origin": "ALPACA HISTORICAL API RESPONSE — NOT INDEPENDENTLY VERIFIED",
                   "provider": "Alpaca Market Data API", "synthetic": False,
                   "adjustment": "split", "dividends_adjusted": False,
                   "provider_api_response": True, "feed_verified": False,
                   "point_in_time_archive_verified": False, "orders_enabled": False,
                   "expected_bars": len(grid), "received_bars": len(clean), "missing_bars": 0,
                   "sessions": len(sessions), "batches": receipts,
                   "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}


def save_private(frame, metadata, directory):
    """Exclusive new directory, outside every Git tree; caller supplies licensed storage."""
    target = Path(directory).expanduser().resolve()
    if any((parent / ".git").exists() for parent in (target, *target.parents)):
        raise ValueError("Private data must be outside all Git repositories")
    if target.exists():
        raise ValueError("Immutable snapshot requires a new directory")
    payload = frame[list(REQUIRED)].to_csv(index=False, lineterminator="\n").encode("utf-8")
    manifest = {**metadata, "csv_sha256": hashlib.sha256(payload).hexdigest(),
                "file": "bars.csv", "bytes": len(payload)}
    target.mkdir(parents=True, exist_ok=False)
    (target / "bars.csv").write_bytes(payload)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_private(directory):
    """Hash-checked local snapshot; reject sealed timestamps before reading numeric columns."""
    folder = Path(directory)
    if (folder / "manifest.json").stat().st_size > 100_000 or (folder / "bars.csv").stat().st_size > MAX_BYTES:
        raise ValueError("Snapshot exceeds bounded input size")
    meta = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if (meta.get("schema") != VERSION or meta.get("feed") not in ("iex", "sip") or
            meta.get("adjustment") != "split" or meta.get("synthetic") is not False or
            meta.get("orders_enabled") is not False):
        raise ValueError("Unsupported source manifest")
    payload = (folder / "bars.csv").read_bytes()
    if hashlib.sha256(payload).hexdigest() != meta.get("csv_sha256"):
        raise ValueError("Snapshot fingerprint mismatch")
    stamps = pd.read_csv(BytesIO(payload), usecols=["timestamp"])
    dates = pd.to_datetime(stamps.timestamp, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    if (dates >= SEALED_START).any():
        raise ValueError("Sealed period is not eligible")
    frame = validated_history(pd.read_csv(BytesIO(payload)), meta)
    if len(frame) != meta.get("received_bars") or len(frame) != meta.get("expected_bars"):
        raise ValueError("Manifest coverage mismatch")
    return frame, meta
