"""Offline, read-only replay provenance manifest; no source authentication claims."""
from __future__ import annotations

import hashlib
import json

from research_workspace.equity_data import SYMBOLS


def replay_manifest(prefix, metadata: dict) -> dict:
    """Describe exactly the displayed prefix without exporting copyrighted bars."""
    if prefix.empty or metadata.get("symbol") not in SYMBOLS:
        raise ValueError("A validated, nonempty equity prefix and supported symbol are required")
    if metadata.get("orders_enabled") is not False:
        raise ValueError("Research export requires orders_enabled=False")
    if metadata.get("feed_verified") is not False:
        raise ValueError("This unverified-source manifest cannot attest to a verified feed")
    if "timestamp" not in prefix or "bar_end" not in prefix:
        raise ValueError("Expected validated bar timestamps and end times")
    values = prefix[["timestamp", "open", "high", "low", "close", "volume"]]
    canonical = values.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return {
        "schema": "tradelab.equity.replay-manifest.v1",
        "purpose": "READ_ONLY_RESEARCH_NOT_TRADING",
        "symbol": metadata["symbol"],
        "origin": metadata["origin"],
        "synthetic": bool(metadata["synthetic"]),
        "feed_verified": False,
        "point_in_time_archive_verified": False,
        "orders_enabled": False,
        "calendar": "XNYS",
        "bar_interval": "15m",
        "visible_bars": len(prefix),
        "first_bar_utc": prefix.timestamp.iloc[0].isoformat(),
        "last_bar_utc": prefix.timestamp.iloc[-1].isoformat(),
        "known_through_utc": prefix.bar_end.iloc[-1].isoformat(),
        "visible_ohlcv_sha256": hashlib.sha256(canonical).hexdigest(),
        "input_sha256": metadata.get("input_sha256"),
        "limitations": [
            "This manifest describes structure and content, not feed authenticity or licenses.",
            "No point-in-time source vintage, broker execution, or returns are verified.",
            "The hash is not a signature or independent market-data attestation.",
        ],
    }


def manifest_json(prefix, metadata: dict) -> str:
    return json.dumps(replay_manifest(prefix, metadata), indent=2, ensure_ascii=False) + "\n"
