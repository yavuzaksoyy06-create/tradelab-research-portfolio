"""Causal, in-memory event records. No downloads, orders or frozen cache access."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import pandas as pd

from research_workspace.equity_data import REQUIRED, SYMBOLS, _validate_and_label
from research_workspace.equity_indicators import indicator_frame
from research_workspace.equity_volume import volume_frame
from research_workspace.equity_structure import confirmed_swing_events, structure_state
from research_sr_v4.causal import build_features

VERSION = "tradelab.stage7.v1"
HORIZONS = (4, 16)
SEALED_START = "2026-10-26"
INSUFFICIENT = "INSUFFICIENT OUT-OF-SAMPLE EVIDENCE"


def fingerprint(frame):
    return hashlib.sha256(frame[list(REQUIRED)].to_csv(
        index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")).hexdigest()


def validated_history(frame, metadata, *, now=None):
    # Inspect timestamps BEFORE numeric bars; never evaluate a sealed price.
    if frame.empty or metadata.get("symbol") not in SYMBOLS:
        raise ValueError("Nonempty supported-symbol history required")
    stamps = pd.to_datetime(frame.timestamp, utc=True)
    if (stamps.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d") >= SEALED_START).any():
        raise ValueError("Stage 7 sealed-period boundary: dates must precede 2026-10-26")
    if metadata.get("orders_enabled") is not False:
        raise ValueError("Read-only provenance required")
    if type(metadata.get("synthetic")) is not bool:
        raise ValueError("Explicit synthetic/actual classification required")
    clean = _validate_and_label(frame[list(REQUIRED)], metadata["symbol"], now=now)
    return clean


def classify_event(bars, snapshots, i, last_break):
    """Frozen pre-crossing geometry; ambiguous bars never get an invented order."""
    candidates = []
    if i >= 2:
        a, b, c = (float(bars.close.iloc[j]) for j in (i - 2, i - 1, i))
        for zone in snapshots[i - 2]["zones"]:
            up = zone["kind"] == "resistance"
            edge = zone["upper"] if up else zone["lower"]
            crossed = (a <= edge < b and c > edge) if up else (a >= edge > b and c < edge)
            if crossed:
                candidates.append({"type": "breakout" if up else "breakdown",
                                   "direction": 1 if up else -1, "zone": deepcopy(zone), "index": i})
    if not candidates and last_break and 0 < i - last_break["index"] <= 16:
        z = last_break["zone"]
        row = bars.iloc[i]
        if row.low <= z["upper"] and row.high >= z["lower"]:
            if (row.close > z["upper"] if last_break["direction"] == 1 else row.close < z["lower"]):
                candidates = [{**deepcopy(last_break), "type": "retest", "index": i}]
    if not candidates:
        return {"type": "none", "direction": 0, "zone": None, "index": i}
    event = candidates[0]
    z = event["zone"]
    start = i - 1 if event["type"] in ("breakout", "breakdown") else i
    spans = any(row.low <= z["lower"] and row.high >= z["upper"]
                for row in bars.iloc[start:i + 1].itertuples())
    if len(candidates) > 1 or spans:
        return {"type": "ambiguous", "direction": 0, "zone": None, "index": i}
    return event


def causal_features(prefix, metadata):
    """Input is already validated history sliced at the visible completed bar."""
    features = build_features(prefix)
    indicators = indicator_frame(prefix)
    volumes = volume_frame(prefix)
    events = confirmed_swing_events(features, len(prefix))
    by_index = {}
    for e in events:
        by_index.setdefault(e["confirmed_index"], []).append(e)
    known, latest, records = [], {"support": [], "resistance": []}, []
    last_break = None
    # Incremental prefix hash avoids quadratic CSV serialization.
    digest = hashlib.sha256()
    for i, row in enumerate(prefix.itertuples(index=False)):
        digest.update(json.dumps([str(row.timestamp), *[float(getattr(row, k)) for k in REQUIRED[1:]]],
                                 separators=(",", ":"), allow_nan=False).encode())
        for event in by_index.get(i, []):
            known.append(event)
            latest[event["kind"]] = (latest[event["kind"]] + [event])[-2:]
        lines = {}
        for kind, pair in latest.items():
            if len(pair) == 2:
                a, b = pair
                slope = (b["price"] - a["price"]) / (b["pivot_index"] - a["pivot_index"])
                lines[kind] = {"slope": slope, "value": b["price"] + slope * (i - b["pivot_index"]),
                               "known_at_index": b["confirmed_index"]}
        event = classify_event(prefix, features["snapshots"], i, last_break)
        if event["type"] in ("breakout", "breakdown"):
            last_break = event
        if i < 20:
            continue
        ind = indicators.iloc[i]
        def available(value):
            return float(value) if math.isfinite(float(value)) else None
        e9, e21 = float(ind.ema_9), float(ind.ema_21)
        prior = indicators.iloc[i - 1]
        rvol = available(volumes.relative_volume_20.iloc[i])
        records.append({
            "index": i, "session": str(row.session), "observed_at": row.bar_end.isoformat(),
            "symbol": metadata["symbol"], "feed": metadata.get("feed", "unspecified"),
            "synthetic": metadata["synthetic"], "prefix_sha256": digest.hexdigest(),
            "close": float(row.close), "atr": float(features["snapshots"][i]["atr"]),
            "ema_sign": 1 if e9 > e21 else -1 if e9 < e21 else 0,
            "ema_down_cross": bool(prior.ema_9 >= prior.ema_21 and e9 < e21),
            "rsi": available(ind.rsi_14), "rvol": rvol,
            "structure": structure_state(known), "lines": lines,
            "zones": deepcopy(features["snapshots"][i]["zones"]), "event": event,
            "previous_up": bool(row.close > prefix.close.iloc[i - 1]),
        })
    return records


def outcome(prefix, record, horizon):
    if horizon not in HORIZONS:
        raise ValueError("Only registered horizons 4 and 16")
    end = record["index"] + horizon
    if end >= len(prefix):
        return {"available_at": None, "return": None, "up": None, "sr_outcome": "pending"}
    final = prefix.iloc[end]
    change = float(final.close) / record["close"] - 1
    event = record["event"]
    label = "no_event"
    if event["type"] == "ambiguous":
        label = "ambiguous"
    elif event["zone"] is not None:
        z = event["zone"]
        future = prefix.iloc[record["index"] + 1:end + 1]
        if ((future.low <= z["lower"]) & (future.high >= z["upper"])).any():
            label = "ambiguous"
        else:
            side = 1 if final.close > z["upper"] else -1 if final.close < z["lower"] else 0
            label = "unresolved" if side == 0 else "continuation" if side == event["direction"] else "reversal"
    return {"available_at": final.bar_end.isoformat(), "return": change,
            "up": int(change > 0), "sr_outcome": label}


def event_dataset(frame, metadata, *, visible_count=None):
    clean = validated_history(frame, metadata)
    n = len(clean) if visible_count is None else visible_count
    if type(n) is not int or not 1 <= n <= len(clean):
        raise ValueError("Invalid replay cursor")
    prefix = clean.iloc[:n]
    records = causal_features(prefix, metadata)
    return {"schema": VERSION, "dataset_sha256": fingerprint(clean),
            "visible_prefix_sha256": fingerprint(prefix), "visible_bars": n,
            "symbol": metadata["symbol"], "feed": metadata.get("feed", "unspecified"),
            "synthetic": metadata["synthetic"],
            "records": [{"features": r, "horizon": h, "outcome": outcome(prefix, r, h)}
                        for r in records for h in HORIZONS]}


def safe_summary(dataset):
    """Allowlist export: no price, volume, return, free-text metadata or credentials."""
    return {k: dataset[k] for k in ("schema", "dataset_sha256", "visible_prefix_sha256",
                                   "visible_bars", "symbol", "synthetic")} | {
        "feed": dataset["feed"] if dataset["feed"] in ("iex", "sip") else "unspecified",
        "records": len(dataset["records"]),
        "completed_outcomes": sum(r["outcome"]["up"] is not None for r in dataset["records"]),
        "horizons": list(HORIZONS), "probabilities": None, "status": INSUFFICIENT,
        "orders_enabled": False,
    }
