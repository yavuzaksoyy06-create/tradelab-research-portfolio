"""Outcome-blind, causal opportunity matching; residual realized exposure is audited."""
import hashlib
import math

SEEDS=(11,23,37,51,71)

def matched_controls(panel,anchors,seed):
    """One intended control per anchor. Delay 0..3 bars within its session hour.
    Selection is decided from anchor identity, never its future result or trade fill.
    At the scheduled completed candle, translate the predeclared percentage
    stop/zone geometry to its observable close. This probes timing conditional
    on SR opportunities; it cannot identify the value of SR event detection.
    """
    result=[]
    for s in anchors:
        symbol=s["symbol"]
        i=s["signal_index"]
        f=panel[symbol]
        anchor=f.iloc[i]
        local=anchor.timestamp.tz_convert("America/New_York")
        offset=(local.hour*60+local.minute-570)//15
        key=f"{seed}|{symbol}|{s['known_at']}|{s['zone_id']}|{s['strategy']}"
        delay=int(hashlib.sha256(key.encode()).hexdigest()[:16],16)%4
        # Do not move across a fixed session-anchored one-hour time-of-day bucket.
        delay=min(delay,3-offset%4,int((anchor.session_close-anchor.timestamp).total_seconds()/900)-1)
        j=i+delay
        if j>=len(f):
            continue # Only possible when the supplied data ends mid-session; engine rejects it.
        row=f.iloc[j]
        scale=row.close/anchor.close
        result.append({**s,"strategy":f"matched_{s['strategy']}","zone_id":f"M:{s['zone_id']}:{i}",
            "signal_index":j,"known_at":str(row.bar_end),"session":row.session,
            "lower":s["lower"]*scale,"upper":s["upper"]*scale,"atr":s["atr"]*scale,
            "source_anchor":s["known_at"],"control_seed":seed,"control_delay_bars":delay,
            "anchor_index":i})
    return result

def trend_baseline(panel,features):
    """Same portfolio risk engine; fixed completed-hour opportunity grid."""
    result=[]
    for symbol,f in panel.items():
        for i,snap in enumerate(features[symbol]["snapshots"]):
            if i<130 or i%4 or snap["regime"]!="uptrend":
                continue
            row=f.iloc[i]
            atr=snap["atr"]
            result.append({"symbol":symbol,"strategy":"trend_baseline","zone_id":"TREND",
                "signal_index":i,"known_at":str(row.bar_end),"session":row.session,
                "lower":row.close-.9*atr,"upper":row.close+.1*atr,"atr":atr,
                "regime":snap["regime"],"collision":False})
    return result


