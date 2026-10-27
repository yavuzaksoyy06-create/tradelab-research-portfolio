"""Calendar-aware, fail-closed data validation and read-only Alpaca ingestion."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import exchange_calendars as xc

ROOT = Path(__file__).resolve().parent
PRICE = ["open", "high", "low", "close"]
class DataQualityError(ValueError):
    pass

def schedule(start, end):
    """Inclusive session dates; XNYS includes US holidays and shortened sessions."""
    cal = xc.get_calendar("XNYS", start="2000-01-01", end="2035-12-31")
    return cal.schedule.loc[str(start)[:10]:str(end)[:10], ["open", "close"]]

def expected_grid(start, end):
    rows = []
    for day, s in schedule(start, end).iterrows():
        for stamp in pd.date_range(s.open, s.close, freq="15min", inclusive="left"):
            rows.append((stamp, stamp + pd.Timedelta(minutes=15), str(day.date()), s.close))
    return pd.DataFrame(rows, columns=["timestamp", "bar_end", "session", "session_close"])

def validate(raw, start, end, now=None, allow_outside_rth=False):
    """Reject bad/partial sessions; never repair, forward-fill, or deduplicate prices."""
    required = ["timestamp", *PRICE, "volume"]
    if not set(required).issubset(raw.columns):
        raise DataQualityError("Missing OHLCV columns")
    if raw.empty:
        raise DataQualityError("Empty dataset")
    f = raw[required].copy()
    for stamp in f.timestamp:
        try:
            if pd.Timestamp(stamp).tzinfo is None:
                raise DataQualityError("Naive timestamp: explicit timezone required")
        except (TypeError, ValueError) as exc:
            raise DataQualityError("Invalid or naive timestamp") from exc
    f["timestamp"] = pd.to_datetime(f.timestamp, utc=True, errors="raise")
    if f.timestamp.isna().any() or f.timestamp.duplicated().any():
        raise DataQualityError("Invalid or duplicate timestamp")
    f[PRICE + ["volume"]] = f[PRICE + ["volume"]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(f[PRICE + ["volume"]].to_numpy()).all():
        raise DataQualityError("Non-finite OHLCV")
    if (f[PRICE] <= 0).any().any() or (f.volume < 0).any():
        raise DataQualityError("Invalid price or volume")
    if ((f.high < f[["open", "close", "low"]].max(axis=1)) |
        (f.low > f[["open", "close", "high"]].min(axis=1))).any():
        raise DataQualityError("Inconsistent OHLC range")
    grid = expected_grid(start, end)
    if grid.empty:
        raise DataQualityError("No exchange sessions in requested interval")
    missing = grid.timestamp[~grid.timestamp.isin(f.timestamp)]
    extra = f.timestamp[~f.timestamp.isin(grid.timestamp)]
    if len(missing):
        raise DataQualityError(f"Missing {len(missing)} scheduled bars; first={missing.iloc[0]}")
    if len(extra) and not allow_outside_rth:
        raise DataQualityError(f"Unexpected/off-session bars: {len(extra)}")
    f = grid.merge(f, on="timestamp", validate="one_to_one").sort_values("timestamp").reset_index(drop=True)
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise DataQualityError("Validation clock must be timezone-aware")
    if (f.bar_end > now).any():
        raise DataQualityError("Unfinished or future bars")
    f.attrs["quality"] = {"sessions":f.session.nunique(), "bars":len(f),
        "outside_rth_removed":len(extra), "calendar":"XNYS", "timezone":"America/New_York",
        "start":str(start), "end":str(end), "checked_at":now.isoformat(),
        "last_bar_end":f.bar_end.iloc[-1].isoformat(),
        "age_since_last_bar_hours":(now-f.bar_end.iloc[-1]).total_seconds()/3600}
    return f

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def fetch(symbol, start, end, feed="sip", refresh=False):
    """Exclusive API end is next midnight NY. No trading endpoints or feed fallback."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed, Adjustment
    from dotenv import dotenv_values
    import os
    if symbol not in {"MSFT","SPY","QQQ"} or feed not in {"sip","iex"}:
        raise ValueError("Explicit supported symbol and feed required")
    cache = ROOT / "out" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{symbol}_{start}_{end}_{feed}_split_15m.csv"
    meta_path = path.with_suffix(".json")
    if path.exists() and meta_path.exists() and not refresh:
        meta = json.loads(meta_path.read_text())
        if digest(path) != meta["sha256"]:
            raise DataQualityError("Cache hash mismatch")
        return validate(pd.read_csv(path), start, end), meta
    secrets = dotenv_values(ROOT.parent / ".env")
    key = os.environ.get("ALPACA_API_KEY") or secrets.get("ALPACA_API_KEY") or secrets.get("APCA_API_KEY_ID")
    secret = os.environ.get("ALPACA_SECRET_KEY") or secrets.get("ALPACA_SECRET_KEY") or secrets.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise DataQualityError("Historical API credentials unavailable under supported key names")
    client = StockHistoricalDataClient(key, secret)
    req = StockBarsRequest(symbol_or_symbols=[symbol], timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=pd.Timestamp(start,tz="America/New_York").to_pydatetime(),
        end=(pd.Timestamp(end,tz="America/New_York")+pd.Timedelta(days=1)).to_pydatetime(),
        feed=DataFeed(feed), adjustment=Adjustment.SPLIT)
    # Exceptions must be sanitized by caller. Never persist request headers or secrets.
    raw = client.get_stock_bars(req).df.reset_index()
    if "symbol" in raw:
        raw = raw.loc[raw.symbol == symbol]
    clean = validate(raw, start, end, allow_outside_rth=True)
    clean[["timestamp",*PRICE,"volume"]].to_csv(path,index=False)
    meta = {"symbol":symbol,"provider":"Alpaca historical","feed":feed,"adjustment":"split",
        "dividends_adjusted":False,"timeframe":"15min","sha256":digest(path),
        "retrieved_utc":datetime.now(timezone.utc).isoformat(), **clean.attrs["quality"]}
    meta_path.write_text(json.dumps(meta,indent=2),encoding="utf-8")
    with sqlite3.connect(ROOT / "out" / "experiments.sqlite") as db:
        db.execute("CREATE TABLE IF NOT EXISTS datasets (sha256 TEXT PRIMARY KEY, metadata TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO datasets VALUES (?,?)",(meta["sha256"],json.dumps(meta)))
    return clean, meta

def main():
    results = []
    for symbol in ["MSFT","SPY","QQQ"]:
        try:
            bars,meta=fetch(symbol,"2026-04-01","2026-10-22")
            results.append({"symbol":symbol,"ok":True,"metadata":meta})
        except Exception as exc:
            # Avoid leaking SDK request details, headers, or credential values.
            status = getattr(exc,"status_code",None)
            reason = str(exc) if isinstance(exc,DataQualityError) else type(exc).__name__
            results.append({"symbol":symbol,"ok":False,"error":reason,"http_status":status})
        print(json.dumps(results[-1]),flush=True)
    (ROOT/"out/ingestion_attempt.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
if __name__=="__main__":
    main()

