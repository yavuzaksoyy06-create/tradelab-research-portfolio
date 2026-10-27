"""Independent, offline V3 reproduction and defect probes. No broker imports."""
from pathlib import Path
import sys, json, hashlib
import pandas as pd

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT / "research_sr_v3"))
from sr_core import prepare_bars, select_completed_sessions, detect_pivots, discover_zones
from sr_execution import simulate_holdout, SimConfig

def frame(rows, stamps=None):
    stamps = stamps or pd.date_range("2026-10-22T13:30Z", periods=len(rows), freq="15min")
    f = pd.DataFrame(rows, columns=["open","high","low","close"])
    f["timestamp"] = pd.to_datetime(stamps, utc=True)
    f["session"] = "2026-10-22"
    return f

def run():
    path = PROJECT/"research_sr_v3/out/MSFT_12_sessions_ohlcv.csv"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == "15440eb4f55efc48b5809cfdcb735f797314f9f4e88709da6ce4bddfdc01e575"
    f,t,v,*_ = select_completed_sessions(prepare_bars(pd.read_csv(path)), min_bars=26)
    piv = detect_pivots(t)
    zones, params = discover_zones(t,piv)
    events,trades,summary = simulate_holdout(v,zones,params["training_median_atr14"])
    expected = pd.read_csv(PROJECT/"research_sr_v3/out/MSFT_hypothetical_trades.csv")
    for col in ["entry_price","planned_stop","planned_target","quantity","exit_price","net_pnl"]:
        assert max(abs(trades[col]-expected[col])) < 1e-6, col
    assert summary["net_pnl_usd"] == -64.659109 and len(events)==7
    # Independent arithmetic against actual source bars, not only saved output.
    import math
    atr_values=[]
    prior=None
    atr=None
    for bar in t.itertuples(index=False):
        tr=max(bar.high-bar.low,abs(bar.high-prior),abs(bar.low-prior)) if prior is not None else bar.high-bar.low
        atr=tr if atr is None else atr+(tr-atr)/14
        atr_values.append(atr)
        prior=bar.close
    # V3 masks initial ATR warm-up; use the source method's 14-row exclusion.
    independent_atr=float(pd.Series(atr_values[14:]).median())
    assert abs(independent_atr-params["training_median_atr14"])<1e-10
    equity=100000.
    last_exit=None
    arithmetic=[]
    source=prepare_bars(pd.read_csv(path)).set_index("timestamp")
    zone_lookup={zone["id"]:zone for zone in zones}
    for trade in trades.itertuples(index=False):
        entry_at=pd.Timestamp(trade.entry_bar_start)
        exit_at=pd.Timestamp(trade.exit_bar_start)
        assert pd.Timestamp(trade.signal_known_at)==entry_at
        assert pd.Timestamp(trade.signal_bar_start)+pd.Timedelta(minutes=15)==entry_at
        assert last_exit is None or entry_at>last_exit
        entry=float(source.loc[entry_at,"open"])*1.0003
        stop=zone_lookup[trade.zone_id]["lower"]-.1*independent_atr
        risk=entry-stop*.9997
        quantity=math.floor(min(equity*.005/risk,equity*.10/entry))
        target=entry+2*risk
        exit_price=min(float(source.loc[exit_at,"open"]),stop)*.9997
        assert source.loc[exit_at,"low"]<=stop
        pnl=quantity*(exit_price-entry)
        for calculated,recorded in [(entry,trade.entry_price),(stop,trade.planned_stop),
                                   (target,trade.planned_target),(exit_price,trade.exit_price),(pnl,trade.net_pnl)]:
            assert abs(calculated-recorded)<1e-6
        assert quantity==trade.quantity
        equity+=pnl
        assert abs(equity-trade.equity_after)<1e-6
        arithmetic.append({"trade_id":trade.trade_id,"raw_entry_open":float(source.loc[entry_at,"open"]),
                           "entry":entry,"stop":stop,"target":target,"quantity":quantity,"net_pnl":pnl})
        last_exit=exit_at
    for pivot in piv.itertuples(index=False):
        assert pd.Timestamp(pivot.confirmed_at)==t.timestamp.iloc[pivot.pivot_index+3]+pd.Timedelta(minutes=15)
    z=[{"id":"S1","kind":"support","lower":99.7,"upper":100.3,"center":100}]
    probes={}
    # Exit at stop precedes unknown remainder of its OHLC bar.
    e,tr,s=simulate_holdout(frame([(100,100.1,99.9,100),(100,105,90,100)]),z,1)
    probes["exit_bar_excursion_contamination"]={
        "exit":float(tr.iloc[0].exit_price),"reported_mae":float(tr.iloc[0].mae_per_share),
        "reported_mfe":float(tr.iloc[0].mfe_per_share),
        "finding":"Full exit-bar range is not position-valid; event ordering is unknown."}
    e,tr,s=simulate_holdout(frame([(100,100.1,99.9,100),(99.599,100.1,99.4,99.9)]),z,1)
    probes["entry_open_already_below_stop"]={
        "trades":len(tr),"status":e.iloc[0].status,
        "finding":"Costs can mask an invalid raw entry-open/stop geometry."}
    e,tr,s=simulate_holdout(frame([(100,100.1,99.9,100),(100,100.2,99.95,100.1),(100,100.2,99.95,100.1)],
        ["2026-10-22T13:30Z","2026-10-22T13:45Z","2026-10-22T14:15Z"]),z,1)
    probes["missing_data_drops_committed_position"]={
        "status":e.iloc[0].status,"trades":len(tr),"equity":s["equity_end"],
        "finding":"An entered position disappears from P&L when later data is missing; incomplete runs must not rank."}
    e,tr,s=simulate_holdout(frame([(100,100.1,99.9,100),(100,100.2,99.95,100.1)]),z,1)
    probes["truncated_day_as_eod"]={
        "exit_reason":tr.iloc[0].exit_reason,"exit_known_by":tr.iloc[0].exit_known_by,
        "finding":"Last observed bar is treated as session close without exchange calendar verification."}
    e,tr,s=simulate_holdout(frame([(100,100.1,99.9,100),(100,100.2,99.3,99.5)]),
                           z,1,SimConfig(risk_fraction=.0001,fee_bps_per_side=100))
    probes["fees_missing_from_planned_risk"]={
        "budget":10,"planned_risk":float(tr.iloc[0].initial_planned_risk_usd),
        "realized_loss":-float(tr.iloc[0].net_pnl),
        "finding":"Known round-trip fees are omitted from sizing risk; not a market-gap overrun."}
    report={"v3_reproduced":True,"sha256":digest,"train_bars":len(t),"holdout_bars":len(v),
            "summary":summary,"independent_trade_arithmetic":arithmetic,
            "independent_atr":independent_atr,"pivot_confirmation_timestamps_verified":len(piv),"probes":probes,
            "limitations":["V3 closed-trade drawdown is not marked-to-market drawdown.",
            "Static train zones are causal for holdout but retrospective train touch scores are not trading signals.",
            "V3 leakage test rewrites a separate frame, not the actual feature input; weak test.",
            "V3 calendar does not validate holidays or early closes.",
            "Historical CSV provenance is a local artifact; SIP entitlement/source not independently re-fetched."]}
    (ROOT/"out/v3_independent_audit.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
if __name__=="__main__": run()


