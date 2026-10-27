"""Traceable presentation models built exclusively from causal replay state."""
import pandas as pd
from .replay import event_id

UNAVAILABLE = "Not recorded / Unavailable"

def matched_trade(event, state):
    payload=event["payload"]
    signal_at=payload.get("known_at",payload.get("signal_known_at"))
    zone=payload.get("zone_id",(payload.get("evidence") or {}).get("zone_id"))
    return next((t for t in state["trades"] if t["symbol"]==event["symbol"] and
                 t["strategy"]==payload.get("strategy") and t["zone_id"]==zone and
                 t["signal_known_at"]==signal_at),None)

def events_at(replay,state):
    events=replay.journal(state,state["symbol"])
    for e in events:
        payload=e["payload"];signal=payload.get("evidence") or {}
        trade=payload if e["kind"]=="exit" else matched_trade(e,state)
        index=signal.get("signal_index",payload.get("signal_index"))
        if e["kind"]=="accepted_entry" and trade:index=trade["entry_index"]
        elif e["kind"]=="exit":index=payload["exit_index"]
        elif e["kind"]=="rejected_entry" and payload.get("decision_at"):
            # Opening decisions share a timestamp with the preceding close.
            # Place at the affected bar, not the preceding signal bar.
            candidates=state["bars"].index[state["bars"].timestamp==pd.Timestamp(payload["decision_at"])]
            if len(candidates):index=int(candidates[0])
        if index is None:continue
        e["known_index"]=int(index)
        e["observable_at"]=str(state["bars"].loc[int(index),"bar_end"])
        e["price"]=(trade["entry_price"] if e["kind"]=="accepted_entry" and trade else
                    payload["exit_price"] if e["kind"]=="exit" else signal.get("upper"))
        e["marker_type"]=("stop_exit" if e["kind"]=="exit" and "stop" in payload.get("reason","") else
                           "target_exit" if e["kind"]=="exit" and "target" in payload.get("reason","") else e["kind"])
    for row in state["risk_events"].to_dict("records"):
        if "lock" not in row["event"]:continue
        bars=state["bars"]
        stamps=bars.timestamp if row["phase"]=="open" else bars.bar_end
        candidates=bars.index[stamps==pd.Timestamp(row["timestamp"])]
        if not len(candidates):continue
        idx=int(candidates[0])
        events.append({"event_id":event_id(replay.run["run_id"],"risk",row["seq"],row["event"]),
            "kind":"risk_lock","marker_type":"risk_lock","timestamp":row["timestamp"],
            "observable_at":str(bars.loc[idx,"bar_end"]),"known_index":idx,
            "symbol":state["symbol"],"payload":row,"price":float(bars.loc[idx,"high"])})
    return sorted((e for e in events if "known_index" in e and e["known_index"]<=state["index"]),
                  key=lambda e:(e["known_index"],e["event_id"]))

def inspect_event(event,state,replay):
    """No access to future trades: only state projections enter the ordinary view."""
    p=event["payload"];ev=p.get("evidence") or {}
    trade=p if event["kind"]=="exit" else matched_trade(event,state)
    idx=event["known_index"]
    bar=state["bars"].loc[idx].to_dict()
    snapshot=state["snapshots"][idx]
    identity={"event_id":event["event_id"],"symbol":event["symbol"],"strategy":p.get("strategy"),
        "event_timestamp":event["timestamp"],"observable_after_bar_close":event["observable_at"],
        "signal_confirmation_timestamp":p.get("known_at",p.get("signal_known_at")),
        "classification":event["kind"],"zone_id":p.get("zone_id",ev.get("zone_id"))}
    evidence={"completed_bar":bar,"ATR":snapshot.get("atr"),"regime":snapshot.get("regime"),
        "active_zones":snapshot.get("zones",[]),"signal_evidence":ev,
        "pivot_confirmations":[v for v in state["pivots"] if v["confirmed_index"]<=idx and
                               v.get("zone_id")==identity["zone_id"]]}
    # The saved pivot schema has no zone foreign key: show confirmed evidence with its real fields.
    if not evidence["pivot_confirmations"]:
        evidence["pivot_confirmations"]=[v for v in state["pivots"] if v["confirmed_index"]==idx]
    decision={"rule":p.get("qualification_rule"),"rule_satisfied":True if ev else None,
              "decision":p.get("status","raw observation" if event["kind"]=="signal" else None),
              "saved_reason":p.get("binding_constraint") or p.get("reason") or p.get("detail")}
    risk={"portfolio_at_signal_close":p.get("portfolio_at_signal_close"),
          "recorded_preallocation_equity":p.get("recorded_preallocation_equity"),
          "risk_limits":p.get("risk_limits",replay.run["audit"]["config"]),
          "cursor_portfolio":state["equity"],"cursor_positions":state["positions"].to_dict("records"),
          "stop":None,"target":None,"quantity":None,"planned_risk":None,
          "planner_position_availability":None}
    execution=None;ledger=[];cash=[]
    if trade:
        execution=dict(trade)
        execution["first_permissible_entry_record"] = None
        execution["exact_intrabar_exit_timestamp"] = None
        # Ledger is already seq-limited by Replay.state; match symbol and known execution times.
        stamps=[pd.Timestamp(trade["entry_at"])]
        if trade["status"]=="closed":stamps.append(pd.Timestamp(trade["exit_known_by"]))
        for key,dest in (("ledger",ledger),("cash",cash)):
            frame=state.get(key,pd.DataFrame())
            if not frame.empty:
                selected=frame[(frame.symbol==trade["symbol"]) & pd.to_datetime(frame.timestamp,utc=True).isin(stamps)]
                dest.extend(selected.to_dict("records"))
        for name in ("stop","target","quantity","planned_risk"):
            risk[name]=trade.get(name)
    return {"identity":identity,"market_evidence":evidence,"signal_evaluation":decision,
            "risk_assessment":risk,"simulated_execution":execution,"ledger":ledger,"cash_costs":cash}

def next_recorded_cursor(replay,symbol,session,completed,kind):
    """Explicit navigation advances knowledge; never returns future outcome fields."""
    first,count=replay.bounds(session)
    if kind=="signal":
        indices=[s["signal_index"] for s in replay.run["signals"] if s["symbol"]==symbol]
    elif kind=="trade":
        indices=replay.run["trades"].query("symbol == @symbol").entry_index.tolist()
    else:raise ValueError("Unsupported navigation kind")
    eligible=[int(i)-first+1 for i in indices if first+completed<=i<first+count]
    return min(eligible) if eligible else completed

def display_values(value):
    if isinstance(value,dict):return {k:display_values(v) for k,v in value.items()}
    if isinstance(value,list):return [display_values(v) for v in value]
    if value is None:return UNAVAILABLE
    return value
