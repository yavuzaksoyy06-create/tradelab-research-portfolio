"""Historically causal display bands for the frozen V4 S/R snapshots.

Only the already-computed, completed-bar snapshots are inspected. Bands never
project the latest zone geometry backwards over bars where it was not known.
"""
from __future__ import annotations


def historical_zone_bands(snapshots, *, visible_start: int = 0):
    """Return maximal adjacent bar-close intervals with identical zone geometry.

    Each returned interval is inclusive. An interval appears only on bars whose
    snapshot lists that zone; updates, merges, invalidations and expiry close
    the existing interval. This function performs *no* price calculations.
    """
    if not isinstance(visible_start, int) or isinstance(visible_start, bool):
        raise ValueError("visible_start must be an integer")
    if not 0 <= visible_start <= len(snapshots):
        raise ValueError("visible_start outside completed snapshots")
    finished = []
    running = {}
    for index in range(visible_start, len(snapshots)):
        snapshot = snapshots[index]
        if snapshot["index"] != index:
            raise ValueError("Snapshots must be ordered by original bar index")
        current = {zone["id"]: zone for zone in snapshot["zones"]}
        if len(current) != len(snapshot["zones"]):
            raise ValueError("Duplicate zone id in snapshot")
        for zone_id, interval in list(running.items()):
            zone = current.get(zone_id)
            if zone is None or (
                zone["kind"], zone["lower"], zone["upper"]
            ) != (
                interval["kind"], interval["lower"], interval["upper"]
            ):
                finished.append(interval)
                del running[zone_id]
        for zone_id, zone in current.items():
            if zone_id in running:
                running[zone_id]["end_index"] = index
            else:
                running[zone_id] = {
                    "zone_id": zone_id,
                    "kind": zone["kind"],
                    "lower": zone["lower"],
                    "upper": zone["upper"],
                    "start_index": index,
                    "end_index": index,
                }
    finished.extend(running.values())
    return sorted(finished, key=lambda band: (
        band["start_index"], band["zone_id"], band["end_index"]
    ))
