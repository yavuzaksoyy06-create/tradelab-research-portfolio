"""End-of-bar projection. Never expose the next opening event at a shared timestamp."""
import hashlib,json
import pandas as pd

ENTRY_FIELDS = ("symbol","strategy","zone_id","signal_known_at","entry_at","entry_index",
                "entry_price","quantity","stop","target","planned_risk","equity_at_entry","entry_fee")
IMMEDIATE = {"no_next_same_session_bar","duplicate_signal","invalid_signal","outside_evaluation"}
RULES = {
    "touch": "Independent support contact; at least two confirmed pivots; departure and four-bar separation.",
    "rejection": "Touch plus close above zone upper, close above open, close-low >= 0.10 ATR.",
    "trend_filtered": "Rejection plus completed-hour EMA9 > EMA21 and rising completed-hour close.",
    "trend_baseline": "Frozen completed-hour trend baseline; not support/resistance evidence."
}

def event_id(run_id, kind, *identity):
    return hashlib.sha256(json.dumps([run_id,kind,*identity],default=str).encode()).hexdigest()[:24]

def clean(record):
    return {k: (None if isinstance(v,float) and pd.isna(v) else v) for k,v in record.items()}

class Replay:
    def __init__(self, store, run):
        self.store, self.run = store, run
        self.initial_capital = float(run["audit"]["config"]["initial_capital"])
        self.clock = store.panel["MSFT"]
        self.close_risk = {pd.Timestamp(x["timestamp"]):clean(x) for x in
            run["equity"].query("phase == 'close'").to_dict("records")}
        self.signal_map = {(x["symbol"],x["signal_index"],x["zone_id"],x["strategy"]):x for x in run["signals"]}

    def sessions(self):
        start,end = self.run["dates"]
        return sorted(s for s in self.clock.session.unique() if start <= s <= end)

    def bounds(self, session):
        if session not in self.sessions():
            raise ValueError("Session outside selected frozen experiment")
        indices = self.clock.index[self.clock.session == session]
        return int(indices[0]), len(indices)

    def state(self, symbol, session, completed=0):
        if symbol not in self.store.panel:
            raise ValueError("Unsupported symbol")
        first, count = self.bounds(session)
        if type(completed) is not int or not 0 <= completed <= count:
            raise ValueError("Replay cursor outside session")
        index = first + completed - 1
        at = self.clock.iloc[index].bar_end if completed else self.clock.iloc[first].timestamp
        cutoff = self.clock.iloc[index].bar_end if index >= 0 else at - pd.Timedelta(nanoseconds=1)
        # A cursor of zero is BEFORE session open, not after its opening allocation.
        eq = self.run["equity"]
        eq = eq[(eq.phase == "close") & (pd.to_datetime(eq.timestamp,utc=True) <= cutoff)]
        if completed == 0:
            eq = eq[pd.to_datetime(eq.timestamp,utc=True) < at]
        seq = int(eq.iloc[-1].seq) if len(eq) else 0
        equity = clean(eq.iloc[-1].to_dict()) if len(eq) else {
            "seq":0,"cash":self.initial_capital,"equity":self.initial_capital,"market_value":0.0,
            "realized_pnl":0.0,"unrealized_pnl":0.0,"exposure_fraction":0.0,
            "planned_open_risk":0.0,"daily_drawdown":0.0,"max_drawdown":0.0,
            "positions":0,"identity_error":0.0,"blocked":False,"phase":"before_experiment"}
        features = self.store.features[symbol]
        snapshot = features["snapshots"][index] if index >= 0 else {"zones":[],"atr":None,"regime":"warmup"}
        decisions = []
        for row in self.run["decisions"].to_dict("records"):
            if int(row["signal_index"]) > index:
                continue
            d = clean(row)
            signal = self.signal_map.get((d["symbol"],d["signal_index"],d["zone_id"],d["strategy"]))
            # Decisions stored with final status are only revealed after the NEXT bar has begun.
            if d["signal_index"] == index and d["status"] not in IMMEDIATE:
                for k in ("decision_at","binding_constraint","equity_before","exposure_after","quantity"):
                    d[k] = None
                d["status"] = "pending_next_open"
            d["event_id"] = event_id(self.run["run_id"],"observation",d["decision_id"])
            d["evidence"] = signal
            d["portfolio_at_signal_close"] = self.close_risk.get(pd.Timestamp(d["known_at"]))
            origin = self.store.features[d["symbol"]]
            si = int(d["signal_index"])
            d["feature_snapshot_at_signal_close"] = origin["snapshots"][si]
            confirmations = [x["known_at"] for x in origin["lifecycle"]
                if x["id"] == d["zone_id"] and x["index"] <= si
                and x["event"] in ("created_confirmed","confirmed_update")]
            d["zone_last_confirmation_as_of_signal_close"] = confirmations[-1] if confirmations else None
            d["risk_limits"] = self.store.protocol["portfolio"] if hasattr(self.store,"protocol") else self.run["audit"]["config"]
            d["recorded_preallocation_equity"] = d["equity_before"]
            d["qualification_rule"] = RULES.get(d["strategy"],
                "Frozen opportunity-conditioned delay/control; inspect source_anchor and control_seed.")
            decisions.append(d)
        trades = []
        for row in self.run["trades"].to_dict("records"):
            if row["entry_index"] > index:
                continue
            # Closed-trade IDs are exit-ordered; never expose these future-derived IDs early.
            entry = {k:row[k] for k in ENTRY_FIELDS}
            entry["event_id"] = event_id(self.run["run_id"],"entry",row["symbol"],row["entry_index"],row["zone_id"])
            entry["status"] = "open"
            if row["exit_index"] <= index:
                entry.update(clean(row))
                entry["status"] = "closed"
            trades.append(entry)
        return {
            "symbol":symbol,"session":session,"completed":completed,"index":index,"timestamp":str(at),
            "phase":"completed_bar" if completed else "before_session_open",
            "bars":self.store.panel[symbol].iloc[:index+1].copy(),
            "snapshot":snapshot,
            "snapshots":features["snapshots"][:index+1],
            "pivots":[p for p in features["pivots"] if p["confirmed_index"]<=index],
            "lifecycle":[p for p in features["lifecycle"] if p["index"]<=index],
            "signals":[x for x in self.run["signals"] if x["signal_index"]<=index and x["symbol"]==symbol],
            "decisions":decisions,"trades":trades,"equity":equity,
            "positions":self.run["positions"][self.run["positions"].seq == seq].copy(),
            "equity_history":eq.copy(),
            "risk_events":self.run["risk_events"][self.run["risk_events"].seq<=seq].copy(),
            "ledger":self.run["ledger"][self.run["ledger"].seq<=seq].copy(),
            "cash":self.run["cash"][self.run["cash"].seq<=seq].copy()
        }

    def journal(self, state, symbol=None, kind=None):
        """Queryable causal event projection; retrospective outcomes never mixed into it."""
        events = []
        for d in state["decisions"]:
            observation = {k:d[k] for k in ("symbol","strategy","known_at","evidence","qualification_rule",
                    "feature_snapshot_at_signal_close","zone_last_confirmation_as_of_signal_close","risk_limits","portfolio_at_signal_close")}
            events.append({"event_id":d["event_id"],"kind":"signal","timestamp":d["known_at"],
                           "symbol":d["symbol"],"payload":observation})
            if d["status"] != "pending_next_open":
                events.append({"event_id":event_id(self.run["run_id"],"decision",d["decision_id"]),
                    "kind":"accepted_entry" if d["status"]=="executed" else "rejected_entry",
                    "timestamp":d["decision_at"] or d["known_at"],"symbol":d["symbol"],"payload":d})
        for t in state["trades"]:
            if t["status"] == "closed":
                events.append({"event_id":event_id(self.run["run_id"],"exit",t["event_id"]),
                    "kind":"exit","timestamp":t["exit_known_by"],"symbol":t["symbol"],"payload":t})
        for e in events:
            e["run_id"] = self.run["run_id"]
            e["protocol_sha256"] = self.store.integrity["protocol_sha256"]
            e["dataset_sha256"] = self.store.metadata[e["symbol"]]["sha256"]
        return [e for e in events if (symbol is None or e["symbol"]==symbol) and (kind is None or e["kind"]==kind)]

