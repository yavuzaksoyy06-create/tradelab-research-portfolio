"""Single-symbol long-only simulator. No external side effects or broker dependency."""
from dataclasses import dataclass, asdict
import math
import pandas as pd
from .data import validate

@dataclass(frozen=True)
class ExecutionConfig:
    initial_capital: float = 100000
    risk_fraction: float = .005
    max_notional_fraction: float = .10
    daily_drawdown: float = .02
    half_spread_bps: float = 1
    slippage_bps: float = 2
    fee_bps: float = 0
    stop_buffer_atr: float = .10
    min_risk_atr: float = .05
    max_distance_atr: float = .50
    reward_risk: float = 2
    horizon_bars: int = 4

    def __post_init__(self):
        for name,value in asdict(self).items():
            if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError(f"Invalid execution setting: {name}")
        if self.initial_capital<=0 or not 0<self.risk_fraction<=.005 or not 0<self.max_notional_fraction<=.10:
            raise ValueError("Capital or research risk/notional limits violated")
        if not 0<self.daily_drawdown<=.02 or self.reward_risk<=0 or self.min_risk_atr<=0:
            raise ValueError("Invalid risk policy")
        if not isinstance(self.horizon_bars,int) or self.horizon_bars<1:
            raise ValueError("Invalid horizon")
        if self.fee_bps>=10000 or self.half_spread_bps+self.slippage_bps>=10000:
            raise ValueError("Costs exceed price")

def simulate(bars, signals, cfg=ExecutionConfig(), start=None, end=None):
    """Validate complete exchange sessions before committing any hypothetical fill.
    All orders here are arithmetic records, never submitted anywhere.
    Costs: fixed adverse half-spread + slippage on each side; percentage fees.
    """
    first=str(bars.timestamp.iloc[0].tz_convert("America/New_York").date())
    last=str(bars.timestamp.iloc[-1].tz_convert("America/New_York").date())
    f=validate(bars,first,last)
    start=start or first
    end=end or last
    by_entry={}
    events=[]
    seen=set()
    for s in signals:
        if not start<=str(s["session"])<=end:
            continue
        event={**s,"status":"pending"}
        events.append(event)
        i=s["signal_index"]
        key=(i,s.get("zone_id"),s.get("strategy"))
        if key in seen:
            event["status"]="duplicate_signal"
            continue
        seen.add(key)
        if not isinstance(i,int) or i<0 or i>=len(f):
            event["status"]="invalid_signal_index"
            continue
        try:
            known=pd.Timestamp(s["known_at"])
            valid=known.tzinfo is not None and known==f.bar_end.iloc[i]
            valid=valid and s["session"]==f.session.iloc[i]
            valid=valid and all(math.isfinite(float(s[k])) for k in ("lower","upper","atr"))
            valid=valid and 0<float(s["lower"])<=float(s["upper"]) and float(s["atr"])>0
        except (ValueError,TypeError,KeyError):
            valid=False
        if not valid:
            event["status"]="invalid_signal"
        elif i+1>=len(f) or f.session.iloc[i+1]!=f.session.iloc[i] or f.session.iloc[i+1]>end:
            event["status"]="no_next_same_session_bar"
        else:
            by_entry.setdefault(i+1,[]).append(event)
    cash=cfg.initial_capital
    position=None
    trades=[]
    equity=[]
    day=None
    day_start=cash
    blocked=False
    liquidate=False
    cost=(cfg.half_spread_bps+cfg.slippage_bps)/10000
    fee=cfg.fee_bps/10000
    for i,row in enumerate(f.itertuples(index=False)):
        if not start<=row.session<=end:
            continue
        if day!=row.session:
            if position is not None:
                raise AssertionError("Overnight position under flat-EOD policy")
            day=row.session
            day_start=cash
            blocked=False
            liquidate=False
        incoming=by_entry.get(i,[])
        if len(incoming)>1 or any(e.get("collision",False) for e in incoming):
            for e in incoming:
                e["status"]="multi_zone_collision"
            incoming=[]
        for e in incoming:
            if position is not None:
                e["status"]="position_already_open"
                continue
            if blocked:
                e["status"]="daily_drawdown_block"
                continue
            stop=e["lower"]-cfg.stop_buffer_atr*e["atr"]
            distance=max(e["lower"]-row.open,row.open-e["upper"],0)
            entry=row.open*(1+cost)
            stop_fill=stop*(1-cost)
            unit_risk=entry*(1+fee)-stop_fill*(1-fee)
            if stop<=0 or row.open<=stop:
                e["status"]="entry_open_at_or_below_stop"
            elif distance>cfg.max_distance_atr*e["atr"]:
                e["status"]="entry_too_far"
            elif unit_risk<cfg.min_risk_atr*e["atr"]:
                e["status"]="risk_too_small"
            else:
                qty=math.floor(min(cash*cfg.risk_fraction/unit_risk,
                    cash*cfg.max_notional_fraction/entry,cash/(entry*(1+fee))))
                if qty<1:
                    e["status"]="insufficient_capital"
                    continue
                target=(entry*(1+fee)+cfg.reward_risk*unit_risk)/((1-cost)*(1-fee))
                entry_fee=qty*entry*fee
                cash-=qty*entry+entry_fee
                e["status"]="executed"
                e["entry_index"]=i
                position={"entry_index":i,"entry_at":str(row.timestamp),"entry_price":entry,
                    "raw_entry":row.open,"quantity":qty,"stop":stop,"target":target,
                    "planned_risk":qty*unit_risk,"entry_fee":entry_fee,"signal":e,
                    "valid_high":row.open,"valid_low":row.open,
                    "observed_high":row.open,"observed_low":row.open,
                    "bars_held":0}
        occupied=position is not None
        exposure=0
        if position is not None:
            p=position
            qty=p["quantity"]
            exposure=qty*row.open/(cash+qty*row.open)
            p["bars_held"]+=1
            p["observed_high"]=max(p["observed_high"],row.high)
            p["observed_low"]=min(p["observed_low"],row.low)
            p["valid_high"]=max(p["valid_high"],row.open)
            p["valid_low"]=min(p["valid_low"],row.open)
            reason=None
            raw_exit=None
            exact=True
            collision=False
            if liquidate:
                raw_exit=row.open
                reason="daily_drawdown_next_open"
            elif row.open<=p["stop"]:
                raw_exit=row.open
                reason="gap_stop"
            elif row.open>=p["target"]:
                # At a gap-up opening, use the observed open, not a target price
                # that may lie outside this candle's traded range.
                raw_exit=row.open
                reason="gap_target_open"
            else:
                hit_stop=row.low<=p["stop"]
                hit_target=row.high>=p["target"]
                if hit_stop:
                    raw_exit=p["stop"]
                    reason="stop"
                    collision=hit_target
                    exact=False
                elif hit_target:
                    raw_exit=p["target"]
                    reason="target"
                    exact=False
                else:
                    p["valid_high"]=max(p["valid_high"],row.high)
                    p["valid_low"]=min(p["valid_low"],row.low)
                    if row.bar_end==row.session_close:
                        raw_exit=row.close
                        reason="exchange_session_close"
                    elif p["bars_held"]>=cfg.horizon_bars:
                        raw_exit=row.close
                        reason="horizon_close"
            if reason is not None:
                p["valid_high"]=max(p["valid_high"],raw_exit)
                p["valid_low"]=min(p["valid_low"],raw_exit)
                exit_price=raw_exit*(1-cost)
                exit_fee=qty*exit_price*fee
                cash+=qty*exit_price-exit_fee
                pnl=qty*(exit_price-p["entry_price"])-p["entry_fee"]-exit_fee
                mfe_low=max(0,p["valid_high"]-p["entry_price"])
                mae_low=max(0,p["entry_price"]-p["valid_low"])
                mfe_upper=max(mfe_low,max(0,row.high-p["entry_price"])) if not exact else mfe_low
                mae_upper=max(mae_low,max(0,p["entry_price"]-row.low)) if not exact else mae_low
                trades.append({"trade_id":f"T{len(trades)+1:05d}","strategy":p["signal"].get("strategy"),
                    "session":row.session,"zone_id":p["signal"].get("zone_id"),
                    "regime":p["signal"].get("regime","unknown"),
                    **{k:p[k] for k in ("entry_index","entry_at","entry_price","raw_entry","quantity","stop","target","planned_risk","bars_held")},
                    "exit_index":i,"exit_bar_start":str(row.timestamp),
                    "exit_known_by":str(row.timestamp if reason.startswith("gap") or reason=="daily_drawdown_next_open" else row.bar_end),
                    "exit_price":exit_price,"raw_exit":raw_exit,"reason":reason,"collision_adverse_first":collision,
                    "net_pnl":pnl,"r_multiple":pnl/p["planned_risk"],
                    "fees":p["entry_fee"]+exit_fee,
                    "spread_slippage_cost":qty*((p["entry_price"]-p["raw_entry"])+(raw_exit-exit_price)),
                    "mfe_exact":mfe_low if exact else None,"mae_exact":mae_low if exact else None,
                    "mfe_lower":mfe_low,"mfe_upper":mfe_upper,"mae_lower":mae_low,"mae_upper":mae_upper,
                    "observed_mfe":max(0,p["observed_high"]-p["entry_price"]),
                    "observed_mae":max(0,p["entry_price"]-p["observed_low"]),
                    "cash_after":cash})
                position=None
                liquidate=False
        mark=cash+(position["quantity"]*row.close if position else 0)
        if mark<=day_start*(1-cfg.daily_drawdown):
            blocked=True
            liquidate=position is not None
        equity.append({"timestamp":str(row.bar_end),"session":row.session,"cash":cash,
            "position_quantity":position["quantity"] if position else 0,
            "equity":mark,"occupied_bar":int(occupied),"open_exposure_fraction":exposure,
            "daily_blocked":blocked})
        if cash < -1e-7:
            raise AssertionError("Unintended borrowing")
    if position is not None:
        raise AssertionError("Unresolved position: run is invalid")
    return {"config":asdict(cfg),"events":events,"trades":trades,"equity":equity,
            "final_equity":cash,"start":start,"end":end}

