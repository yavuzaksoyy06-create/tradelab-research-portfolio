"""Causal, descriptive indicators for completed research bars only.

No broker connectivity, external data, fitted parameters, future-bar access or
changes to the frozen V4/V4.1 feature engine. Warm-up values remain unavailable.
"""
from __future__ import annotations

import math

import pandas as pd

EMA_PERIODS = (9, 21, 50, 200)
RSI_PERIOD = 14


def wilder_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """RSI seeded with an SMA of the first *period* observed close differences.

    First available at bar index=period. Subsequent values use recursive
    Wilder averages of completed differences, and never future prices.
    """
    if period < 1 or isinstance(period, bool):
        raise ValueError("RSI period must be a positive integer")
    prices = pd.Series(close, dtype="float64").reset_index(drop=True)
    result = pd.Series(float("nan"), index=prices.index, dtype="float64")
    if len(prices) <= period:
        return result

    changes = prices.diff()
    gains = changes.clip(lower=0.0)
    losses = (-changes).clip(lower=0.0)
    avg_gain = float(gains.iloc[1: period + 1].mean())
    avg_loss = float(losses.iloc[1: period + 1].mean())

    for i in range(period, len(prices)):
        if i > period:
            avg_gain = ((period - 1) * avg_gain + float(gains.iloc[i])) / period
            avg_loss = ((period - 1) * avg_loss + float(losses.iloc[i])) / period
        if avg_loss == 0.0:
            result.iloc[i] = 50.0 if avg_gain == 0.0 else 100.0
        else:
            rs = avg_gain / avg_loss
            result.iloc[i] = 100.0 - (100.0 / (1.0 + rs))
    return result


def indicator_frame(prefix: pd.DataFrame) -> pd.DataFrame:
    """Calculate indicators from the available replay prefix only.

    EMAs start recursively at the first observed close, but are not displayed
    until their own full lookback has passed. RSI uses Wilder's SMA seed.
    """
    if prefix.empty or "close" not in prefix:
        raise ValueError("Indicators require a nonempty validated close series")
    close = pd.to_numeric(prefix["close"], errors="raise").reset_index(drop=True)
    if not all(math.isfinite(float(v)) and float(v) > 0 for v in close):
        raise ValueError("Indicators require finite positive closes")
    out = pd.DataFrame(index=range(len(close)))
    for period in EMA_PERIODS:
        out[f"ema_{period}"] = close.ewm(
            span=period, adjust=False, min_periods=period
        ).mean()
    out["rsi_14"] = wilder_rsi(close)
    return out
