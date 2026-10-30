"""Fixed, retrospective BIST daily research from an entitled local CSV only."""
from io import BytesIO
import hashlib
import json
import re
from urllib.parse import urlsplit

import exchange_calendars as xcals
import numpy as np
import pandas as pd

PROTOCOL = "tradelab.bist.daily.v1"
SYMBOLS = ("THYAO", "GARAN", "ASELS")
COLUMNS = ("date", "open", "high", "low", "close", "volume", "adjusted_close")
MAX_BYTES = 2_000_000
CONSTANTS = {"timeframe": "1d", "currency": "TRY", "exchange": "XIST",
             "usage_rights": "user_confirmed_local_research",
             "adjustment": "provider_adjusted_close", "source_independently_verified": False}


def _manifest(meta):
    if not isinstance(meta, dict) or meta.get("symbol") not in SYMBOLS:
        raise ValueError("BIST_INVALID_MANIFEST")
    if any(meta.get(k) != v or type(meta.get(k)) is not type(v) for k, v in CONSTANTS.items()):
        raise ValueError("BIST_INVALID_MANIFEST")
    for key, limit in (("provider", 200), ("license_reference", 200), ("source_url", 2048)):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
            raise ValueError("BIST_INVALID_SOURCE")
    url = urlsplit(meta["source_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("BIST_INVALID_SOURCE")
    if not re.fullmatch("[0-9a-f]{64}", str(meta.get("csv_sha256", ""))):
        raise ValueError("BIST_INVALID_MANIFEST")
    keys = (*CONSTANTS, "symbol", "provider", "license_reference", "source_url", "csv_sha256")
    return {key: meta[key] for key in keys}


def _validated(frame):
    if tuple(frame.columns) != COLUMNS or not 200 <= len(frame) <= 5000:
        raise ValueError("BIST_INVALID_SCHEMA")
    clean = frame.copy()
    dates = pd.to_datetime(clean.date, format="%Y-%m-%d", errors="raise")
    if dates.dt.tz is not None or dates.isna().any() or (dates != dates.dt.normalize()).any():
        raise ValueError("BIST_INVALID_DATES")
    # Reject reserved dates before interpreting any numerical values.
    if (dates >= pd.Timestamp("2026-10-26")).any():
        raise ValueError("BIST_SEALED_PERIOD")
    if (dates >= pd.Timestamp("2025-01-01")).any():
        raise ValueError("BIST_HOLDOUT_RESERVED")
    if (dates < pd.Timestamp("2020-01-01")).any() or not dates.is_monotonic_increasing or dates.duplicated().any():
        raise ValueError("BIST_INVALID_DATES")
    expected = xcals.get_calendar("XIST", start="2020-01-01", end="2024-12-31").sessions
    if not pd.DatetimeIndex(dates).equals(expected):
        raise ValueError("BIST_INCOMPLETE_COVERAGE")
    clean["date"] = dates
    for col in COLUMNS[1:]:
        clean[col] = pd.to_numeric(clean[col], errors="raise").astype(float)
    numbers = clean[list(COLUMNS[1:])].to_numpy()
    if not np.isfinite(numbers).all() or (clean.volume < 0).any() or (clean[["open", "high", "low", "close", "adjusted_close"]] <= 0).any().any():
        raise ValueError("BIST_INVALID_NUMERICS")
    if ((clean.low > clean[["open", "close"]].min(axis=1)) |
        (clean.high < clean[["open", "close"]].max(axis=1)) | (clean.low > clean.high)).any():
        raise ValueError("BIST_INVALID_OHLC")
    return clean.reset_index(drop=True)


def _fingerprint(frame):
    return hashlib.sha256(frame.to_csv(index=False, float_format="%.17g", date_format="%Y-%m-%d",
                                      lineterminator="\n").encode("utf-8")).hexdigest()


def _registration(meta):
    content = {**_manifest(meta), "protocol": meta.get("protocol"),
               "canonical_sha256": meta.get("canonical_sha256")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def load_csv(payload, manifest):
    """Validate complete 2020–24 history. No network, filesystem writes or inference."""
    meta = _manifest(manifest)
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("BIST_INPUT_SIZE")
    if hashlib.sha256(payload).hexdigest() != meta["csv_sha256"]:
        raise ValueError("BIST_HASH_MISMATCH")
    raw = pd.read_csv(BytesIO(payload), dtype=str)
    frame = _validated(raw)
    meta.update(protocol=PROTOCOL, canonical_sha256=_fingerprint(frame), bytes=len(payload),
                bars=len(frame), first_session="2020-01-02", last_session="2024-12-31",
                orders_enabled=False)
    meta["registration_sha256"] = _registration(meta)
    return frame, meta


def _net_returns(returns, positions, bps):
    # Initial entry is established at the preceding close; include liquidation.
    turnover = np.abs(np.diff(positions, prepend=0.0))
    factor = (1 + positions * returns) * (1 - bps / 10_000 * turnover)
    factor[-1] *= 1 - bps / 10_000 * positions[-1]
    return factor - 1, turnover


def _metrics(returns):
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        wealth = np.cumprod(1 + returns)
    if not np.isfinite(returns).all() or not np.isfinite(wealth).all() or (wealth <= 0).any():
        raise ValueError("BIST_INVALID_CALCULATION")
    peak = np.maximum.accumulate(np.r_[1.0, wealth])[1:]
    with np.errstate(over="ignore", invalid="ignore"):
        result = {"net_total_return": float(wealth[-1] - 1),
                  "annualized_volatility_252": float(np.std(returns, ddof=1) * np.sqrt(252)),
                  "max_drawdown": float(np.min(wealth / peak - 1))}
    if not all(np.isfinite(v) for v in result.values()):
        raise ValueError("BIST_INVALID_CALCULATION")
    return result


def _block_interval(excess):
    rng = np.random.default_rng(7)
    n, block = len(excess), 20
    means = []
    for _ in range(500):
        starts = rng.integers(0, n - block + 1, size=int(np.ceil(n / block)))
        sample = np.concatenate([excess[i:i + block] for i in starts])[:n]
        means.append(sample.mean())
    return [float(x) for x in np.quantile(means, [.025, .975])]


def analyze(frame, metadata):
    """One fixed model; 2023–24 validation only. Returns private chart rows separately."""
    meta = _manifest(metadata)
    clean = _validated(frame)
    if (metadata.get("protocol") != PROTOCOL or metadata.get("canonical_sha256") != _fingerprint(clean) or
            metadata.get("registration_sha256") != _registration(metadata)):
        raise ValueError("BIST_REGISTERED_INPUT_CHANGED")
    prices = clean.adjusted_close
    ema20 = prices.ewm(span=20, adjust=False, min_periods=20).mean()
    ema60 = prices.ewm(span=60, adjust=False, min_periods=60).mean()
    signal = (ema20 > ema60).astype(float)
    # A close-t signal executes at close t+1, first earning t+1 -> t+2.
    position = signal.shift(2, fill_value=0)
    gross = prices.pct_change(fill_method=None).fillna(0)
    if not np.isfinite(gross).all() or not np.isfinite(ema20.iloc[19:]).all() or not np.isfinite(ema60.iloc[59:]).all():
        raise ValueError("BIST_INVALID_CALCULATION")
    mask = clean.date >= pd.Timestamp("2023-01-01")
    curve = clean.loc[mask, ["date", "adjusted_close"]].copy().reset_index(drop=True)
    curve["ema20"], curve["ema60"] = ema20[mask].to_numpy(), ema60[mask].to_numpy()
    pos, returns = position[mask].to_numpy(), gross[mask].to_numpy()
    sensitivities = {}
    for bps in (10, 25, 50):
        net, turnover = _net_returns(returns, pos, bps)
        bh, _ = _net_returns(returns, np.ones(len(pos)), bps)
        sensitivities[str(bps)] = {"strategy": _metrics(net), "buy_hold": _metrics(bh)}
        if bps == 25:
            primary, benchmark, changes = net, bh, turnover
    curve["position"], curve["net_return"] = pos, primary
    curve["net_equity"] = np.cumprod(1 + primary)
    curve["buyhold_equity"] = np.cumprod(1 + benchmark)
    annual = {str(year): float(np.prod(1 + primary[curve.date.dt.year.to_numpy() == year]) - 1)
              for year in (2023, 2024)}
    summary = {"protocol": PROTOCOL, "status": "retrospective_research_only", "symbol": meta["symbol"],
               "csv_sha256": meta["csv_sha256"], "canonical_sha256": metadata["canonical_sha256"],
               "timeframe": "1d", "currency": "TRY", "exchange": "XIST", "input_bars": len(clean),
               "evaluation_first_session": curve.date.iloc[0].date().isoformat(),
               "evaluation_last_session": curve.date.iloc[-1].date().isoformat(), "evaluated_bars": len(curve),
               "ema_spans": [20, 60], "signal_delay_bars": 2, "cost_bps_per_side": 25,
               "sensitivity_bps_per_side": sensitivities, "exposure": float(pos.mean()),
               "cash_baseline": _metrics(np.zeros(len(pos))),
               "registration_sha256": metadata["registration_sha256"],
               "turnover_including_terminal_exit": float(changes.sum() + pos[-1]),
               "position_changes_including_terminal_exit": int(np.count_nonzero(changes) + (pos[-1] != 0)),
               "annual_net_returns": annual, "daily_mean_excess_vs_buy_hold": float((primary - benchmark).mean()),
               "daily_mean_excess_95_block_interval": _block_interval(primary - benchmark),
               "bootstrap": {"method": "moving_block", "block_sessions": 20, "replications": 500, "seed": 7},
               "holdout_scored": False, "source_independently_verified": False,
               "point_in_time_vintage_verified": False, "parameter_search_performed": False,
               "orders_enabled": False,
               "limits": ["Current chosen survivors; not a representative BIST universe",
                          "Provider-adjusted history is retrospective, not an independently archived vintage",
                          "Nominal TRY; no inflation, FX, cash yield, tax, liquidity, lot-size or limit-fill model",
                          "Fixed EMA rule; block interval is descriptive, not significance or profitable-edge proof",
                          "2025 final holdout and dates on/after 2026-10-26 are not evaluated"]}
    try:
        json.dumps(summary, allow_nan=False)
    except ValueError:
        raise ValueError("BIST_INVALID_CALCULATION") from None
    return summary, curve
