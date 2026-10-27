"""Read-only adapter to frozen V4 data and features; no network/API/credential access."""
from pathlib import Path
import hashlib,json
import pandas as pd
from research_sr_v4.data import validate,DataQualityError,expected_grid
from research_sr_v4.causal import build_features

ROOT=Path(__file__).resolve().parent
V4=ROOT.parent/"research_sr_v4"

def validate_panel(panel,start,end,now=None):
    if not panel or not set(panel)<={"MSFT","SPY","QQQ"}:
        raise DataQualityError("Unsupported or empty universe")
    cleaned={}
    for symbol,f in panel.items():
        if f.empty:
            raise DataQualityError(f"{symbol}: empty data")
        ts=pd.to_datetime(f.timestamp,utc=True)
        if not ts.is_monotonic_increasing:
            raise DataQualityError(f"{symbol}: input timestamps are not ordered")
        cleaned[symbol]=validate(f,start,end,now=now)
    grids=[f.timestamp.tolist() for f in cleaned.values()]
    if any(g!=grids[0] for g in grids):
        raise DataQualityError("Symbols must have identical complete session grids")
    return cleaned

def load_cache():
    panel,metadata={},{}
    for symbol in ("MSFT","SPY","QQQ"):
        p=V4/"out/cache"/f"{symbol}_2026-04-01_2026-10-22_sip_split_15m.csv"
        m=json.loads(p.with_suffix(".json").read_text())
        if hashlib.sha256(p.read_bytes()).hexdigest()!=m["sha256"]:
            raise DataQualityError(f"{symbol}: cache SHA256 mismatch")
        if (m["symbol"],m["feed"],m["adjustment"],m["timeframe"])!=(symbol,"sip","split","15min"):
            raise DataQualityError(f"{symbol}: metadata mismatch")
        panel[symbol]=pd.read_csv(p)
        metadata[symbol]=m
    return validate_panel(panel,"2026-04-01","2026-10-22"),metadata

def features_and_signals(panel):
    features={s:build_features(f) for s,f in panel.items()}
    signals=[{"symbol":s,**x} for s,f in features.items() for x in f["signals"]]
    return features,signals

