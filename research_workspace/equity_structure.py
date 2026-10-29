"""Causal confirmed-swing structure and mechanical research trendlines.

All events become available at the V4 pivot *confirmation* bar. A trendline is
drawn only from the second confirmed same-kind swing onward and stops when a
newer confirmed swing replaces its pivot pair. No future candles, look-ahead,
manual fitting, trade signals, or alteration of the frozen V4/V4.1 engines.
"""
from __future__ import annotations

from collections import defaultdict
import math


def confirmed_swing_events(features: dict, bar_count: int) -> list[dict]:
    """Classify latest confirmed pivot vs prior same-kind confirmed pivot."""
    if not isinstance(bar_count, int) or isinstance(bar_count, bool) or bar_count < 1:
        raise ValueError("bar_count must be a positive integer")
    events = []
    previous = {}
    last_confirmed = -1
    for p in features["pivots"]:
        kind = p["kind"]
        index = p["confirmed_index"]
        if kind not in ("support", "resistance") or not 0 <= p["pivot_index"] <= index < bar_count:
            raise ValueError("Invalid confirmed swing")
        if index < last_confirmed:
            raise ValueError("Pivots must be ordered by confirmation time")
        last_confirmed = index
        price = float(p["price"])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Non-finite or nonpositive swing price")
        before = previous.get(kind)
        if before is None:
            label = "L0" if kind == "support" else "H0"
        else:
            prior = float(before["price"])
            tolerance = 1e-8 * max(1.0, abs(prior))
            if abs(price - prior) <= tolerance:
                label = "EL" if kind == "support" else "EH"
            elif price > prior:
                label = "HL" if kind == "support" else "HH"
            else:
                label = "LL" if kind == "support" else "LH"
        events.append({
            "kind": kind, "label": label, "price": price,
            "pivot_index": p["pivot_index"], "confirmed_index": index,
            "confirmed_at": p["confirmed_at"],
            "previous_price": None if before is None else float(before["price"]),
        })
        previous[kind] = p
    return events


def structure_state(events: list[dict]) -> str:
    """Descriptive structure from latest comparisons, never a forecast."""
    latest = {}
    for event in events:
        latest[event["kind"]] = event["label"]
    highs, lows = latest.get("resistance"), latest.get("support")
    if highs == "HH" and lows == "HL":
        return "rising"
    if highs == "LH" and lows == "LL":
        return "falling"
    if highs in (None, "H0") or lows in (None, "L0"):
        return "insufficient"
    return "mixed"


def confirmed_trendline_segments(features: dict, bar_count: int) -> list[dict]:
    """Finite, immutable segments for each pair of confirmed same-kind pivots.

    The line equation uses the two actual pivot prices/bar indices. Its first
    drawable point is at the *second confirmation*, never a pivot in the past.
    Each time a new pivot is confirmed, the prior segment stops and a new
    segment begins. Projections extend only to the replay cursor.
    """
    events = confirmed_swing_events(features, bar_count)
    by_bar = defaultdict(list)
    for event in events:
        by_bar[event["confirmed_index"]].append(event)
    latest = {"support": [], "resistance": []}
    segments = []
    running = {}
    for i in range(bar_count):
        for event in by_bar[i]:
            kind = event["kind"]
            latest[kind].append(event)
            latest[kind] = latest[kind][-2:]
        for kind in ("support", "resistance"):
            pair = latest[kind]
            if len(pair) != 2:
                continue
            a, b = pair
            denominator = b["pivot_index"] - a["pivot_index"]
            if denominator <= 0:
                raise ValueError("Distinct ordered same-kind pivots are required")
            slope = (b["price"] - a["price"]) / denominator
            value = b["price"] + slope * (i - b["pivot_index"])
            if not math.isfinite(value):
                raise ValueError("Trendline projection became nonfinite")
            pair_id = (a["confirmed_index"], b["confirmed_index"])
            if kind not in running or running[kind]["pair_id"] != pair_id:
                current = {
                    "kind": kind, "pair_id": pair_id,
                    "start_index": i, "end_index": i,
                    "known_at_index": b["confirmed_index"],
                    "pivot_indices": (a["pivot_index"], b["pivot_index"]),
                    "slope_per_bar": slope,
                    "values": [value],
                }
                segments.append(current)
                running[kind] = current
            else:
                running[kind]["end_index"] = i
                running[kind]["values"].append(value)
    return segments
