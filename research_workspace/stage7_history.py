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
from research_workspace.stage7_events import SEALED_START, VERSION, validated_history, research_partition


def collection_plan(symbol, start, end, *, feed):
    """Calendar-only plan; no credentials, network, storage or price access."""
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
    return {"schema": "tradelab.stage7.collection-plan.v1", "symbol": symbol, "feed": feed,
            "adjustment": "split", "sessions": len(sessions), "expected_bars": len(grid),
            "first_session": sessions[0], "last_session": sessions[-1],
            "batches": [{"first_session": sessions[i], "last_session": sessions[min(i+9, len(sessions)-1)],
                         "expected_bars": int(grid.session.isin(sessions[i:i+10]).sum())}
                        for i in range(0, len(sessions), 10)],
            "network_requests_performed": 0, "entitlement_verified": False,
            "orders_enabled": False}


def collect_history(symbol, start, end, *, feed, api_key, api_secret,
                    explicit_download=False, request_page=None):
    if explicit_download is not True:
        raise ValueError("Explicit user-initiated download required")
    plan = collection_plan(symbol, start, end, feed=feed)
    grid = expected_grid(plan["first_session"], plan["last_session"])
    frames, receipts = [], []
    for batch in plan["batches"]:
        try:
            frame, meta = read_alpaca_history(
                symbol, batch["first_session"], batch["last_session"], feed=feed, api_key=api_key,
                api_secret=api_secret, request_page=request_page)
        except Exception:
            # Provider bodies/headers or custom transports must not leak secrets.
            raise EquityProviderError(
                "Historical batch failed: coverage, entitlement, rate limit or network. "
                "No automatic retry; no partial dataset accepted.") from None
        expected = grid.loc[(grid.session >= batch["first_session"]) &
                            (grid.session <= batch["last_session"]), "timestamp"]
        if list(frame.timestamp) != list(expected):
            raise EquityProviderError("Incomplete requested session coverage; dataset rejected")
        frames.append(frame)
        receipts.append({"first_session": batch["first_session"], "last_session": batch["last_session"],
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
                   "sessions": plan["sessions"], "batches": receipts,
                   "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}


def save_private(frame, metadata, directory):
    """Exclusive new directory, outside every Git tree; caller supplies licensed storage."""
    clean = validated_history(frame, metadata)
    if metadata.get("research_partition") is not None and metadata["research_partition"] != research_partition(clean):
        raise ValueError("Registered snapshot changed")
    target = Path(directory).expanduser().resolve()
    if any((parent / ".git").exists() for parent in (target, *target.parents)):
        raise ValueError("Private data must be outside all Git repositories")
    if target.exists():
        raise ValueError("Immutable snapshot requires a new directory")
    payload = clean[list(REQUIRED)].to_csv(index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")
    # Do not serialize arbitrary caller metadata such as credentials or request headers.
    fields = ("symbol", "origin", "provider", "synthetic", "feed", "adjustment",
              "dividends_adjusted", "provider_api_response", "feed_verified",
              "point_in_time_archive_verified", "orders_enabled", "expected_bars",
              "received_bars", "missing_bars", "sessions", "retrieved_at_utc")
    source = {key: metadata[key] for key in fields if key in metadata}
    # Batch receipts are independently allowlisted; no transport headers/bodies.
    receipt_fields = ("first_session", "last_session", "bars", "retrieved_at_utc", "outside_rth_excluded")
    source["batches"] = [{k: row[k] for k in receipt_fields if k in row}
                         for row in metadata.get("batches", [])]
    manifest = {**source, "schema": VERSION, "research_partition": research_partition(clean),
                "csv_sha256": hashlib.sha256(payload).hexdigest(),
                "file": "bars.csv", "bytes": len(payload)}
    target.mkdir(parents=True, exist_ok=False)
    (target / "bars.csv").write_bytes(payload)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_private(directory, *, expected_digests=None):
    """Hash-checked local snapshot; reject sealed timestamps before reading numeric columns."""
    folder = Path(directory)
    # Enforce bounds on the bytes actually consumed, not a racy earlier stat.
    content = {}
    for name, limit in (("manifest.json", 100_000), ("bars.csv", MAX_BYTES)):
        with (folder / name).open("rb") as stream:
            content[name] = stream.read(limit + 1)
        if len(content[name]) > limit:
            raise ValueError("Snapshot exceeds bounded input size")
    digests = {name: hashlib.sha256(payload).hexdigest() for name, payload in content.items()}
    if expected_digests is not None and digests != expected_digests:
        raise ValueError("Snapshot changed during review")
    meta = json.loads(content["manifest.json"].decode("utf-8"))
    if (meta.get("schema") != VERSION or meta.get("feed") not in ("iex", "sip") or
            meta.get("adjustment") != "split" or meta.get("synthetic") is not False or
            meta.get("orders_enabled") is not False):
        raise ValueError("Unsupported source manifest")
    payload = content["bars.csv"]
    if hashlib.sha256(payload).hexdigest() != meta.get("csv_sha256"):
        raise ValueError("Snapshot fingerprint mismatch")
    if type(meta.get("bytes")) is not int or meta["bytes"] != len(payload):
        raise ValueError("Manifest byte count mismatch")
    stamps = pd.read_csv(BytesIO(payload), usecols=["timestamp"])
    dates = pd.to_datetime(stamps.timestamp, utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    if (dates >= SEALED_START).any():
        raise ValueError("Sealed period is not eligible")
    frame = validated_history(pd.read_csv(BytesIO(payload), float_precision="round_trip"), meta)
    counts = {"received_bars": len(frame), "expected_bars": len(frame)}
    counts.update({k: v for k, v in (("sessions", int(frame.session.nunique())), ("missing_bars", 0))
                   if k in meta})
    if any(type(meta.get(key)) is not int or meta[key] != count for key, count in counts.items()):
        raise ValueError("Manifest coverage mismatch")
    if meta.get("research_partition") is not None and meta["research_partition"] != research_partition(frame):
        raise ValueError("Registered snapshot partition mismatch")
    return frame, meta
