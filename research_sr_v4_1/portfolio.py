"""Consolidated observable-event timeline; no broker or network operations."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict
import hashlib,json,math
import pandas as pd
from .data import validate_panel
from .policy import PortfolioConfig,plan_entry,costs,open_exit,bar_exit

SCHEMAS={
"equity":["seq","timestamp","session","phase","cash","buying_power","reserved_cash","market_value","equity",
          "realized_pnl","unrealized_pnl","costs_accrued","exposure_fraction","positions","planned_open_risk",
          "daily_drawdown","max_drawdown","blocked","identity_error"],
"cash":["seq","timestamp","symbol","action","cash_flow","cash_after","fee","execution_cost"],
"positions":["seq","timestamp","phase","symbol","quantity","mark","market_value","entry_price","unrealized_pnl","planned_risk"],
"trades":["trade_id","symbol","strategy","zone_id","regime","session","signal_known_at","entry_at","entry_index",
          "entry_price","quantity","stop","target","planned_risk","equity_at_entry","entry_fee",
          "exit_bar_start","exit_known_by","exit_index","raw_exit","exit_price","exit_fee","reason","net_pnl",
          "r_multiple","bars_held","collision_adverse_first","mfe_exact","mae_exact","mfe_lower","mfe_upper",
          "mae_lower","mae_upper","observed_mfe","observed_mae"],
"decisions":["decision_id","symbol","strategy","zone_id","signal_index","known_at","session","status",
             "decision_at","quantity","binding_constraint","equity_before","exposure_after","source_anchor","control_seed"],
"risk_events":["seq","timestamp","session","phase","event","symbol","equity","threshold","detail"],
"ledger":["seq","timestamp","phase","action","symbol","quantity","price","cash_before","cash_after","realized_pnl"]
}

def simulate(panel,signals,cfg=PortfolioConfig(),start=None,end=None,now=None):
    first=next(iter(panel.values()))
    data_start=str(pd.Timestamp(first.timestamp.iloc[0]).tz_convert("America/New_York").date())
    data_end=str(pd.Timestamp(first.timestamp.iloc[-1]).tz_convert("America/New_York").date())
    panel=validate_panel(panel,data_start,data_end,now)
    start=start or data_start
    end=end or data_end
    if not data_start<=start<=end<=data_end:
        raise ValueError("Evaluation bounds outside supplied complete dataset")
    order=[s for s in cfg.allocation_order if s in panel]
    rows={s:list(panel[s].itertuples(index=False)) for s in order}
    clock=rows[order[0]]
    result={k:[] for k in SCHEMAS}
    result.update({"config":asdict(cfg),"start":start,"end":end})
    scheduled=defaultdict(list)
    seen=set()
    def sort_key(s):
        return (str(s.get("known_at","")),str(s.get("symbol","")),str(s.get("zone_id","")),
                str(s.get("strategy","")),str(s.get("signal_index","")),
                json.dumps(s,sort_keys=True,default=str))
    for n,s in enumerate(sorted(signals,key=sort_key)):
        d={k:s.get(k) for k in SCHEMAS["decisions"]}
        d.update({"decision_id":f"D{n+1:06d}","status":"pending","quantity":0})
        result["decisions"].append(d)
        symbol=s.get("symbol")
        i=s.get("signal_index")
        valid=symbol in panel and type(i) is int and 0<=i<len(clock)
        try:
            valid=valid and pd.Timestamp(s["known_at"]).tzinfo is not None
            valid=valid and pd.Timestamp(s["known_at"])==clock[i].bar_end
            valid=valid and s["session"]==clock[i].session
            valid=valid and all(math.isfinite(float(s[k])) for k in ("lower","upper","atr"))
            valid=valid and 0<s["lower"]<=s["upper"] and s["atr"]>0
        except (KeyError,ValueError,TypeError):
            valid=False
        if not valid:
            d["status"]="invalid_signal"
            continue
        if not start<=s["session"]<=end:
            d["status"]="outside_evaluation"
            continue
        key=(symbol,i,s.get("zone_id"),s.get("strategy"))
        if key in seen:
            d["status"]="duplicate_signal"
            continue
        seen.add(key)
        if i+1>=len(clock) or clock[i+1].session!=s["session"]:
            d["status"]="no_next_same_session_bar"
            continue
        scheduled[i+1].append((s,d))
    cash=cfg.initial_capital
    realized=0.
    accrued=0.
    positions={}
    seq=0
    peak=cfg.initial_capital
    daily_peak=cfg.initial_capital
    session=None
    blocked=False
    force_next_open=False
    c,fee=costs(cfg)
    marks={}
    def nextseq():
        nonlocal seq
        seq+=1
        return seq
    def valuation():
        gross=sum(p["quantity"]*marks[s] for s,p in positions.items())
        unreal=sum(p["quantity"]*(marks[s]-p["entry_price"])-p["entry_fee"] for s,p in positions.items())
        return cash+gross,gross,unreal
    def risk_event(time,phase,event,symbol="",detail=""):
        eq,_,_=valuation()
        result["risk_events"].append({"seq":nextseq(),"timestamp":str(time),"session":session,
            "phase":phase,"event":event,"symbol":symbol,"equity":eq,
            "threshold":cfg.daily_drawdown if event=="daily_drawdown_breach" else (cfg.aggregate_exposure_cap if event=="mark_to_market_exposure_breach" else None),
            "detail":detail})
    def observe(time,phase):
        nonlocal peak,daily_peak,blocked,force_next_open
        eq,gross,unreal=valuation()
        peak=max(peak,eq)
        daily_peak=max(daily_peak,eq)
        dd=1-eq/daily_peak
        if dd>=cfg.daily_drawdown-1e-12 and not blocked:
            blocked=True
            force_next_open=True
            risk_event(time,phase,"daily_drawdown_breach",detail="Entries blocked; surviving positions liquidate at next open")
        if eq>0 and gross/eq>cfg.aggregate_exposure_cap+1e-10:
            risk_event(time,phase,"mark_to_market_exposure_breach",detail="Price movement; no new risk allowed above cap")
        err=eq-(cfg.initial_capital+realized+unreal)
        if abs(err)>1e-7 or cash < -1e-7:
            raise AssertionError("Cash/equity accounting identity violated")
        n=nextseq()
        result["equity"].append({"seq":n,"timestamp":str(time),"session":session,"phase":phase,
            "cash":cash,"buying_power":max(0,cash),"reserved_cash":0.,"market_value":gross,"equity":eq,
            "realized_pnl":realized,"unrealized_pnl":unreal,"costs_accrued":accrued,
            "exposure_fraction":gross/eq if eq else 0.,"positions":len(positions),
            "planned_open_risk":sum(p["planned_risk"] for p in positions.values()),
            "daily_drawdown":dd,"max_drawdown":1-eq/peak,"blocked":blocked,"identity_error":err})
        for symbol in order:
            if symbol in positions:
                p=positions[symbol]
                result["positions"].append({"seq":n,"timestamp":str(time),"phase":phase,"symbol":symbol,
                    "quantity":p["quantity"],"mark":marks[symbol],"market_value":p["quantity"]*marks[symbol],
                    "entry_price":p["entry_price"],
                    "unrealized_pnl":p["quantity"]*(marks[symbol]-p["entry_price"])-p["entry_fee"],
                    "planned_risk":p["planned_risk"]})
    def close_position(symbol,bar,i,raw,reason,phase,exact,collision=False):
        nonlocal cash,realized,accrued
        p=positions[symbol]
        p["valid_high"]=max(p["valid_high"],raw)
        p["valid_low"]=min(p["valid_low"],raw)
        exit_price=raw*(1-c)
        q=p["quantity"]
        exit_fee=q*exit_price*fee
        proceeds=q*exit_price-exit_fee
        pnl=proceeds-p["entry_debit"]
        before=cash
        cash+=proceeds
        realized+=pnl
        execution_cost=q*(raw-exit_price)
        accrued+=exit_fee+execution_cost
        at=bar.timestamp if phase=="open" else bar.bar_end
        n=nextseq()
        result["cash"].append({"seq":n,"timestamp":str(at),"symbol":symbol,"action":"exit",
            "cash_flow":proceeds,"cash_after":cash,"fee":exit_fee,"execution_cost":execution_cost})
        result["ledger"].append({"seq":n,"timestamp":str(at),"phase":phase,"action":"exit","symbol":symbol,
            "quantity":q,"price":exit_price,"cash_before":before,"cash_after":cash,"realized_pnl":pnl})
        mfe=max(0,p["valid_high"]-p["entry_price"])
        mae=max(0,p["entry_price"]-p["valid_low"])
        result["trades"].append({"trade_id":f"T{len(result['trades'])+1:06d}","symbol":symbol,
            "strategy":p["signal"]["strategy"],"zone_id":p["signal"].get("zone_id"),
            "regime":p["signal"].get("regime","unknown"),"session":session,
            "signal_known_at":p["signal"]["known_at"],
            **{k:p[k] for k in ("entry_at","entry_index","entry_price","quantity","stop","target",
                                 "planned_risk","equity_at_entry","entry_fee","bars_held")},
            "exit_bar_start":str(bar.timestamp),"exit_known_by":str(at),"exit_index":i,
            "raw_exit":raw,"exit_price":exit_price,"exit_fee":exit_fee,"reason":reason,"net_pnl":pnl,
            "r_multiple":pnl/p["planned_risk"],"collision_adverse_first":collision,
            "mfe_exact":mfe if exact else None,"mae_exact":mae if exact else None,
            "mfe_lower":mfe,"mae_lower":mae,
            "mfe_upper":mfe if exact else max(mfe,bar.high-p["entry_price"]),
            "mae_upper":mae if exact else max(mae,p["entry_price"]-bar.low),
            "observed_mfe":max(0,p["observed_high"]-p["entry_price"]),
            "observed_mae":max(0,p["entry_price"]-p["observed_low"])})
        del positions[symbol]
        if -pnl>p["planned_risk"]+1e-7:
            risk_event(at,phase,"loss_exceeds_planned",symbol,f"loss={-pnl:.8f}; planned={p['planned_risk']:.8f}")
    for i,tick in enumerate(clock):
        if not start<=tick.session<=end:
            continue
        marks={s:rows[s][i].open for s in order}
        if tick.session!=session:
            if positions:
                raise AssertionError("Overnight positions under EOD-flat policy")
            session=tick.session
            daily_peak=cash
            blocked=False
            force_next_open=False
            risk_event(tick.timestamp,"open","session_reset",detail="Daily high-water mark reset to flat cash")
        # Only opens are accessed before allocation. No other symbol's intrabar
        # exit proceeds can finance an entry at this timestamp.
        forcing=force_next_open
        force_next_open=False
        for symbol in order:
            if symbol not in positions:
                continue
            p=positions[symbol]
            op=rows[symbol][i].open
            p["valid_high"]=max(p["valid_high"],op)
            p["valid_low"]=min(p["valid_low"],op)
            p["observed_high"]=max(p["observed_high"],op)
            p["observed_low"]=min(p["observed_low"],op)
            raw,reason=open_exit(p,op,forcing)
            if reason:
                close_position(symbol,rows[symbol][i],i,raw,reason,"open",True)
        observe(tick.timestamp,"open")
        incoming=scheduled.get(i,[])
        for symbol in order:
            group=[(s,d) for s,d in incoming if s["symbol"]==symbol]
            if not group:
                continue
            if len(group)>1 or any(s.get("collision",False) for s,d in group):
                for s,d in group:
                    d.update(status="multi_zone_collision",decision_at=str(tick.timestamp))
                continue
            s,d=group[0]
            d["decision_at"]=str(tick.timestamp)
            if blocked:
                d["status"]="daily_drawdown_block"
                continue
            if symbol in positions:
                d["status"]="position_already_open"
                continue
            if len(positions)>=cfg.max_positions:
                d["status"]="position_count_cap"
                continue
            eq,gross,_=valuation()
            plan,reason=plan_entry(marks[symbol],s,eq,cash,gross,cfg)
            d["equity_before"]=eq
            if reason:
                d["status"]=reason
                continue
            before=cash
            cash-=plan["entry_debit"]
            accrued+=plan["entry_cost"]
            positions[symbol]={**plan,"entry_at":str(tick.timestamp),"entry_index":i,
                "signal":s,"bars_held":0,"valid_high":marks[symbol],"valid_low":marks[symbol],
                "observed_high":marks[symbol],"observed_low":marks[symbol]}
            new_eq,new_gross,_=valuation()
            if new_gross>cfg.aggregate_exposure_cap*new_eq+1e-7:
                raise AssertionError("Entry violated post-cost aggregate exposure cap")
            d.update(status="executed",quantity=plan["quantity"],binding_constraint=plan["binding_constraint"],
                     exposure_after=new_gross/new_eq)
            n=nextseq()
            result["cash"].append({"seq":n,"timestamp":str(tick.timestamp),"symbol":symbol,"action":"entry",
                "cash_flow":-plan["entry_debit"],"cash_after":cash,"fee":plan["entry_fee"],
                "execution_cost":plan["entry_cost"]-plan["entry_fee"]})
            result["ledger"].append({"seq":n,"timestamp":str(tick.timestamp),"phase":"entry","action":"entry",
                "symbol":symbol,"quantity":plan["quantity"],"price":plan["entry_price"],
                "cash_before":before,"cash_after":cash,"realized_pnl":0.})
            observe(tick.timestamp,"after_entry")
        observe(tick.timestamp,"after_entries")
        for symbol in order:
            if symbol not in positions:
                continue
            p=positions[symbol]
            bar=rows[symbol][i]
            p["bars_held"]+=1
            p["observed_high"]=max(p["observed_high"],bar.high)
            p["observed_low"]=min(p["observed_low"],bar.low)
            raw,reason,exact,collision=bar_exit(p,bar,cfg)
            if exact:
                p["valid_high"]=max(p["valid_high"],bar.high)
                p["valid_low"]=min(p["valid_low"],bar.low)
            if reason:
                close_position(symbol,bar,i,raw,reason,"bar_end",exact,collision)
        marks={s:rows[s][i].close for s in order}
        observe(tick.bar_end,"close")
    if positions:
        raise AssertionError("Unresolved positions invalidate experiment")
    if any(d["status"]=="pending" for d in result["decisions"]):
        raise AssertionError("Unresolved decision")
    if abs(cash-(cfg.initial_capital+sum(t["net_pnl"] for t in result["trades"])))>1e-7:
        raise AssertionError("Final trade/P&L reconciliation")
    result["final_equity"]=cash
    result["audit"]={"schema_version":"1","config":asdict(cfg),"allocation_policy":list(cfg.allocation_order),
        "phases":["open_exits","observable_open_risk","ordered_entries","intrabar_and_close_exits","close_mark_risk"],
        "maximum_identity_error":max(abs(x["identity_error"]) for x in result["equity"]),
        "final_open_positions":len(positions),"cash_flow_reconciliation_error":
            cash-cfg.initial_capital-sum(x["cash_flow"] for x in result["cash"]),
        "intrabar_exit_proceeds_available_only_after_all_open_entries":True,
        "reservation_policy":"zero: signals are intentions, only immediate fills debit cash",
        "daily_drawdown_basis":"observable session high-water equity; opens, transactions and closes",
        "opening_fill_assumption":"synchronized opening prices observable without latency; no auction/queue model",
        "orders_submitted":False}
    return result

def write_tables(result,directory):
    from pathlib import Path
    path=Path(directory)
    path.mkdir(parents=True,exist_ok=True)
    for name,cols in SCHEMAS.items():
        pd.DataFrame(result[name],columns=cols).to_csv(path/f"portfolio_{name}.csv",index=False,lineterminator="\n")
    (path/"portfolio_audit.json").write_text(json.dumps(result["audit"],indent=2,sort_keys=True),encoding="utf-8")


