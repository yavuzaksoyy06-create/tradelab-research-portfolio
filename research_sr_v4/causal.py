"""Streaming confirmed pivots/zones. Prefix invariance is a required invariant."""
from dataclasses import dataclass, asdict
import math
import pandas as pd

@dataclass(frozen=True)
class FeatureConfig:
    left: int = 3
    right: int = 3
    atr_period: int = 14
    lookback_bars: int = 520
    zone_half_width_atr: float = 0.20
    merge_gap_atr: float = 0.10
    touch_separation: int = 4
    min_pivots: int = 2
    rejection_atr: float = 0.10

    def __post_init__(self):
        for n in ("left","right","atr_period","lookback_bars","touch_separation","min_pivots"):
            if not isinstance(getattr(self,n),int) or getattr(self,n)<1:
                raise ValueError(f"Invalid {n}")
        for n in ("zone_half_width_atr","merge_gap_atr","rejection_atr"):
            if not math.isfinite(getattr(self,n)) or getattr(self,n)<0:
                raise ValueError(f"Invalid {n}")
        if self.zone_half_width_atr<=0:
            raise ValueError("Zone width must be positive")

def build_features(bars, cfg=FeatureConfig()):
    """Input must have passed data.validate. Each row is known at its bar_end."""
    active=[]
    history=[]
    lifecycle=[]
    pivots=[]
    signals=[]
    snapshots=[]
    atr=None
    ema9=ema21=None
    hour_closes=[]
    seq=0
    prev_close=None
    last_session=None
    session_bar=0
    for i,row in enumerate(bars.itertuples(index=False)):
        if row.session != last_session:
            session_bar=0
            last_session=row.session
        tr=max(row.high-row.low,abs(row.high-prev_close),abs(row.low-prev_close)) if prev_close is not None else row.high-row.low
        atr=tr if atr is None else atr+(tr-atr)/cfg.atr_period
        prev_close=row.close
        session_bar+=1
        # Four completed regular-session bars form one session-anchored hour.
        # Ignore an incomplete final hourly bucket, never use its future close.
        if session_bar%4==0:
            hour_closes.append(row.close)
            ema9=row.close if ema9 is None else ema9+(row.close-ema9)*2/10
            ema21=row.close if ema21 is None else ema21+(row.close-ema21)*2/22
        trend=(len(hour_closes)>=21 and ema9>ema21 and hour_closes[-1]>hour_closes[-4])
        regime="uptrend" if trend else ("warmup" if len(hour_closes)<21 else "other")
        for z in active[:]:
            kept=[p for p in z["members"] if i-p["pivot_index"]<=cfg.lookback_bars]
            if not kept:
                lifecycle.append({"id":z["id"],"event":"expired","known_at":str(row.bar_end),"index":i})
                active.remove(z)
                continue
            if len(kept)!=len(z["members"]):
                z["members"]=kept
                z["lower"]=min(p["price"]-p["width"] for p in kept)
                z["upper"]=max(p["price"]+p["width"] for p in kept)
                lifecycle.append({"id":z["id"],"event":"rolling_update","known_at":str(row.bar_end),"index":i})
            broken=(row.close<z["lower"]-.25*atr if z["kind"]=="support" else row.close>z["upper"]+.25*atr)
            z["break_streak"]=z["break_streak"]+1 if broken else 0
            if z["break_streak"]>=2:
                lifecycle.append({"id":z["id"],"event":"invalidated","known_at":str(row.bar_end),"index":i})
                active.remove(z)
        # Evaluate zones that existed before this candle's new pivot confirmations.
        touched=[]
        for z in active:
            contact=row.low<=z["upper"] and row.high>=z["lower"]
            independent=contact and not z["was_touching"] and i-z["last_touch"]>=cfg.touch_separation
            if independent:
                z["touches"]+=1
                z["last_touch"]=i
                if z["kind"]=="support" and len(z["members"])>=cfg.min_pivots:
                    touched.append(z)
            z["was_touching"]=contact
        if i>=cfg.atr_period and atr>0 and touched:
            # Any active support overlap in the signal candle is ambiguous, even
            # if one contact is not independent. Never choose the winner after the fact.
            all_contact=[z for z in active if z["kind"]=="support" and
                         len(z["members"])>=cfg.min_pivots and row.low<=z["upper"] and row.high>=z["lower"]]
            prior_vol=[b.volume for b in history[-20:]]
            vol_ratio=row.volume/(sum(prior_vol)/len(prior_vol)) if prior_vol and sum(prior_vol)>0 else None
            for z in touched:
                common={"signal_index":i,"known_at":str(row.bar_end),"session":row.session,
                    "zone_id":z["id"],"lower":z["lower"],"upper":z["upper"],"atr":atr,
                    "touches":z["touches"],"pivot_count":len(z["members"]),
                    "zone_created_at":z["created_at"],"relative_volume":vol_ratio,
                    "regime":regime,"collision":len(all_contact)>1}
                signals.append({**common,"strategy":"touch"})
                rejection=row.close>z["upper"] and row.close>row.open and row.close-row.low>=cfg.rejection_atr*atr
                if rejection:
                    signals.append({**common,"strategy":"rejection"})
                    if trend:
                        signals.append({**common,"strategy":"trend_filtered"})
        # Confirm a strict pivot only once the right-hand candle closes.
        history.append(row)
        p=i-cfg.right
        if p>=cfg.left and i>=cfg.atr_period:
            candidate=history[p]
            surrounding=history[p-cfg.left:p]+history[p+1:i+1]
            for kind,price,strict in (
                ("support",candidate.low,all(candidate.low<b.low for b in surrounding)),
                ("resistance",candidate.high,all(candidate.high>b.high for b in surrounding))):
                if not strict:
                    continue
                pivot={"kind":kind,"price":price,"pivot_index":p,"confirmed_index":i,
                    "pivot_at":str(candidate.timestamp),"confirmed_at":str(row.bar_end),
                    "width":cfg.zone_half_width_atr*atr}
                pivots.append(pivot)
                lo,hi=price-pivot["width"],price+pivot["width"]
                # Transitive closure prevents a newly widened merge from leaving
                # another adjacent same-kind zone behind.
                matches=[]
                while True:
                    found=[z for z in active if z["kind"]==kind and z not in matches and
                           lo<=z["upper"]+cfg.merge_gap_atr*atr and hi>=z["lower"]-cfg.merge_gap_atr*atr]
                    if not found:
                        break
                    matches.extend(found)
                    lo=min(lo,min(z["lower"] for z in found))
                    hi=max(hi,max(z["upper"] for z in found))
                if matches:
                    z=matches[0]
                    members=[pivot]+[m for other in matches for m in other["members"]]
                    z["members"]=members
                    z["lower"]=min(m["price"]-m["width"] for m in members)
                    z["upper"]=max(m["price"]+m["width"] for m in members)
                    # Touch counts from different zones are not additive independent evidence.
                    z["touches"]=max(m["touches"] for m in matches)
                    z["last_touch"]=max(m["last_touch"] for m in matches)
                    z["was_touching"]=True  # Require a fresh departure/re-entry after a merge.
                    for other in matches[1:]:
                        lifecycle.append({"id":other["id"],"event":"merged","into":z["id"],"known_at":str(row.bar_end),"index":i})
                        active.remove(other)
                    lifecycle.append({"id":z["id"],"event":"confirmed_update","known_at":str(row.bar_end),"index":i})
                else:
                    seq+=1
                    z={"id":f"Z{seq:05d}","kind":kind,"lower":lo,"upper":hi,
                        "members":[pivot],"touches":0,"last_touch":-100000,
                        "was_touching":True,"break_streak":0,"created_at":str(row.bar_end)}
                    active.append(z)
                    lifecycle.append({"id":z["id"],"event":"created_confirmed","known_at":str(row.bar_end),"index":i})
        snapshots.append({"index":i,"known_at":str(row.bar_end),"atr":atr,"regime":regime,
            "hourly_ema9":ema9,"hourly_ema21":ema21,
            "zones":[{k:z[k] for k in ("id","kind","lower","upper","touches","created_at")}
                     | {"pivot_count":len(z["members"])} for z in active]})
    return {"config":asdict(cfg),"pivots":pivots,"lifecycle":lifecycle,"signals":signals,"snapshots":snapshots}

