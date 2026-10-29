"""Causal descriptive volume analytics from completed 15-minute equity bars.

The baseline is a simple rolling mean of the 20 PREVIOUS bars, excluding the
current bar. It is NOT a time-of-day seasonality-adjusted expected volume.
IEX and SIP volume cannot be treated as equivalent coverage.
"""
from __future__ import annotations

import math

import pandas as pd

VOLUME_LOOKBACK = 20


def volume_frame(prefix: pd.DataFrame, *, lookback: int = VOLUME_LOOKBACK) -> pd.DataFrame:
    """Return past-only volume baseline and current/prior-baseline ratio.

    The first result is at bar index=lookback; zero prior mean is unavailable.
    Never replace an unavailable baseline with zero or with future observations.
    """
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
        raise ValueError("Volume lookback must be a positive integer")
    if prefix.empty or "volume" not in prefix:
        raise ValueError("Volume analytics require nonempty validated bars")
    volume = pd.to_numeric(prefix["volume"], errors="raise").reset_index(drop=True)
    if not all(math.isfinite(float(v)) and float(v) >= 0 for v in volume):
        raise ValueError("Volume must be finite and nonnegative")

    baseline = volume.shift(1).rolling(lookback, min_periods=lookback).mean()
    baseline = baseline.where(baseline > 0)
    relative = volume.div(baseline)
    return pd.DataFrame({
        "prior_volume_mean_20": baseline,
        "relative_volume_20": relative,
    })
