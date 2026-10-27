"""TradeLab local historical workstation. No broker connectivity."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import pandas as pd
import streamlit as st
import plotly.express as px
from research_terminal import __version__
from research_terminal.adapter import Store,ROOT,BASE,PERIODS,read_json,integrity
from research_terminal.replay import Replay
from research_terminal.charts import market,portfolio,style
from research_terminal.intake import validate_manifest
from research_terminal.analytics import risk_view,reconciliation

st.set_page_config(page_title="TradeLab | Research Terminal",page_icon="◈",layout="wide")
st.markdown("""<style>
.stApp{background:#080f1b;color:#dbe6f5} section[data-testid="stSidebar"]{background:#0c1422}
.block-container{padding-top:3.8rem;max-width:1600px}
[data-testid="stMetric"]{background:#111e30;border:1px solid #21314a;border-radius:8px;padding:14px}
[data-testid="stMetricValue"]{font-size:clamp(1rem,2.7vw,1.65rem)!important}
[data-testid="stMetricLabel"] p{white-space:normal;font-size:12px}
[data-testid="stAppDeployButton"]{display:none}
h1,h2,h3{letter-spacing:-.025em} .eyebrow{color:#6ee7c5;letter-spacing:.18em;font-size:12px}
</style>""",unsafe_allow_html=True)

@st.cache_resource
def load_store():
    return Store()

with st.sidebar:
    st.markdown("## ◈ TRADELAB")
    st.caption(f"RESEARCH TERMINAL {__version__}")
    page=st.radio("Workspace",["Overview","Market Intelligence","Strategy Lab","Portfolio & Risk","Research Audit"],key="page")
    period=st.selectbox("Frozen period",PERIODS,key="period")
try:
    with st.spinner("Verifying frozen sources, data and research outputs…"):
        store=load_store()
    variant=st.sidebar.selectbox("Frozen strategy",store.variants(period),
        index=store.variants(period).index("touch"),key="variant")
    run=store.run(period,variant)
except (OSError,ValueError,KeyError) as exc:
    st.error("Research unavailable: "+str(exc))
    st.info("Restore the verified local cache/manifest. No data was substituted.")
    st.stop()

st.sidebar.caption("Previously observed historical data\n\nSIP · split-adjusted · XNYS · 15 min")
st.sidebar.caption("Research only • No broker connection")
st.markdown('<div class="eyebrow">HISTORICAL RESEARCH / FROZEN V4.1</div>',unsafe_allow_html=True)
st.title(page)
st.caption(f'{run["dates"][0]} → {run["dates"][1]}  ·  {variant}  ·  Run {run["run_id"][:12]}')
m=run["metrics"]

def money(value):
    return "$" + f"{value:,.2f}"

def metric_row(values):
    columns=st.columns(len(values))
    for col,(label,value) in zip(columns,values):
        col.metric(label,value)

def table(frame):
    if isinstance(frame,list): frame=pd.DataFrame(frame)
    if frame.empty: st.info("No records available at this selection.")
    else: st.dataframe(frame,hide_index=True,width="stretch")

if page=="Overview":
    st.warning("No robust trading advantage demonstrated. These dates were already examined; this is not a new holdout.")
    metric_row([("Virtual starting capital",money(run["audit"]["config"]["initial_capital"])),("Final hypothetical equity",money(m["final_equity"])),
                ("Net historical P&L",money(m["net_pnl"])),("Maximum drawdown",f'{m["max_drawdown_pct"]:.3f}%')])
    metric_row([("Trades",m["executed_trades"]),("Active sessions",m["active_trade_sessions"]),
                ("Mean opening exposure",f'{m["average_open_exposure_fraction"]:.2%}'),("Valid sessions / symbol","142")])
    st.plotly_chart(portfolio(run["equity"].query("phase == 'close'")),width="stretch")
    st.markdown("#### Dataset coverage")
    table([{"symbol":s,"feed":v["feed"],"adjustment":v["adjustment"],"bars":len(store.panel[s]),
            "start":v["start"],"end":v["end"],"sha256":v["sha256"]} for s,v in store.metadata.items()])
    st.caption("Zero-latency opening fills, assumed costs, ambiguous intrabar paths, no dividends. Control comparisons test timing conditional on SR opportunities.")

elif page=="Market Intelligence":
    from research_terminal.inspection import events_at,inspect_event,matched_trade,next_recorded_cursor,display_values
    from research_terminal.charts import clock_label,MARKERS
    replay=Replay(store,run)
    c1,c2,c3=st.columns([1,1.5,1])
    symbol=c1.selectbox("Instrument",list(store.panel),key="symbol")
    session=c2.selectbox("Session",replay.sessions(),key="session")
    history=c3.selectbox("Visible completed bars",[50,100,200],index=1,key="history")
    first,count=replay.bounds(session)
    selection=(period,variant,symbol,session)
    if st.session_state.get("selection")!=selection:
        st.session_state["cursor"]=0
        st.session_state["selection"]=selection
        st.session_state.pop("inspector_event",None)
        st.session_state["hindsight"]=False
    def move(delta=None):
        st.session_state.cursor=0 if delta is None else min(count,max(0,st.session_state.cursor+delta))
        st.session_state["navigation_note"]=""
    def jump_event(kind):
        target=next_recorded_cursor(replay,symbol,session,st.session_state.cursor,kind)
        st.session_state["navigation_note"]="No later matching event in this session." if target==st.session_state.cursor else ""
        if target!=st.session_state.cursor:
            st.session_state["select_jump_kind"]="signal" if kind=="signal" else "accepted_entry"
            st.session_state["event_filter"]="all"
            st.session_state["event_search"]=""
        st.session_state.cursor=target
    b1,b2,b3,b4=st.columns(4)
    b1.button("Reset to open",on_click=move,width="stretch")
    b2.button("Previous candle",on_click=move,args=(-1,),width="stretch")
    b3.button("+1 candle",on_click=move,args=(1,),width="stretch")
    b4.button("+4 candles",on_click=move,args=(4,),width="stretch")
    b1,b2=st.columns(2)
    b1.button("Next recorded signal",on_click=jump_event,args=("signal",),width="stretch")
    b2.button("Next simulated trade",on_click=jump_event,args=("trade",),width="stretch")
    st.caption("Event jumps explicitly advance replay within this session; no future event details are previewed.")
    labels={0:"Before session open"}
    labels.update({j:clock_label(replay.clock.iloc[first+j-1].bar_end) for j in range(1,count+1)})
    st.select_slider("Completed candle / jump (America/New_York)",options=list(labels),format_func=labels.get,key="cursor")
    if st.session_state.get("navigation_note"):st.info(st.session_state.navigation_note)
    state=replay.state(symbol,session,st.session_state.cursor)
    stamp=pd.Timestamp(state["timestamp"])
    st.caption(f'{session} · {state["phase"]} · {clock_label(stamp)} · Türkiye {stamp.tz_convert("Europe/Istanbul"):%H:%M} · UTC {stamp:%H:%M} · {state["completed"]}/{count} completed · {count-state["completed"]} remaining')
    metric_row([("As-of equity",money(state["equity"]["equity"])),("As-of cash",money(state["equity"]["cash"])),
                ("ATR",f'{state["snapshot"]["atr"]:.4f}' if state["snapshot"]["atr"] is not None else "Unavailable"),
                ("Completed-hour regime",state["snapshot"]["regime"])])
    with st.expander("Chart layers and marker guide"):
        visibility={}
        cols=st.columns(3)
        for i,(key,label) in enumerate([("zones","Support / resistance"),("pivots","Confirmed pivots"),
            ("execution","Simulated entries / exits"),("rejected","Rejected opportunities"),("signals","Signals"),("atr","ATR"),("volume","Volume")]):
            visibility[key]=cols[i%3].checkbox(label,value=True,key="show_"+key)
        st.caption("Outlined diamond: confirmed pivot · outlined blue triangle: signal · filled green triangle: simulated entry · pink down triangle: timed exit · red X: stop · green star: target · orange open X: rejection · yellow warning star: risk lock.")
    all_events=events_at(replay,state)
    visible_start=int(state["bars"].tail(history).index[0]) if len(state["bars"]) else 0
    event_options=[e for e in all_events if e["known_index"]>=visible_start]
    kinds=["all",*sorted({e["kind"] for e in event_options})]
    kind=st.selectbox("Event category",kinds,key="event_filter")
    search=st.text_input("Search event ID / zone / status",key="event_search")
    filtered=[e for e in event_options if (kind=="all" or e["kind"]==kind) and search.lower() in json.dumps(e,default=str).lower()]
    jump_kind=st.session_state.pop("select_jump_kind",None)
    if jump_kind:
        match=next((e for e in filtered if e["kind"]==jump_kind and e["known_index"]==state["index"]),None)
        if match:st.session_state["inspector_event"]=match["event_id"]
    event=None
    if filtered:
        ids=[e["event_id"] for e in filtered];by_id={e["event_id"]:e for e in filtered}
        if st.session_state.get("inspector_event") not in ids:st.session_state["inspector_event"]=ids[-1]
        selected=st.selectbox("Inspect event",ids,key="inspector_event",
            format_func=lambda x:f'{by_id[x]["kind"]} · {clock_label(by_id[x]["timestamp"])} · {x[:8]}')
        event=by_id[selected]
    else:
        st.session_state.pop("inspector_event",None)
        st.info("No recorded events in the visible completed-bar window. Advance replay or broaden the window.")
    trade=(event["payload"] if event and event["kind"]=="exit" else matched_trade(event,state) if event else None)
    st.plotly_chart(market(state,history,all_events,event["event_id"] if event else None,visibility,trade),
                    width="stretch",config={"scrollZoom":True,"displaylogo":False},key="market_chart")
    st.caption("Gapless trading-bar axis; true times in hover. Event selector highlights its chart marker. Chart clicking is not enabled. Dashed stop/target applies only to the selected known position.")
    st.markdown("### Decision Inspector")
    if event:
        detail=inspect_event(event,state,replay)
        st.caption("Historical simulated execution, not broker fills. Missing evidence is explicitly unavailable.")
        for title,key in [("A · Event identity","identity"),("B · Market evidence at event bar close","market_evidence"),
            ("C · Signal evaluation","signal_evaluation"),("D · Risk assessment (times labeled)","risk_assessment"),
            ("E · Simulated trade detail — observable at cursor","simulated_execution")]:
            with st.expander(title,expanded=key in ("identity","signal_evaluation")):
                st.json(display_values(detail[key]))
        with st.expander("Trade ledger and recorded fees / execution costs"):
            st.caption("Exact intrabar exit time and unrecorded planner intermediates: Not recorded / Unavailable.")
            table(detail["ledger"]);table(detail["cash_costs"])
        with st.expander("Full auditable event payload"):st.json(event)
    tabs=st.tabs(["Causal zones","Decision journal","Portfolio at cursor","Retrospective — explicit hindsight"])
    with tabs[0]:
        table(state["snapshot"]["zones"])
        with st.expander("Zone lifecycle and pivot evidence"):
            table([x for x in state["lifecycle"] if x["index"]>=first])
            table([x for x in state["pivots"] if x["confirmed_index"]>=first])
    with tabs[1]:
        table([{k:v for k,v in e.items() if k!="payload"} for e in filtered])
        st.download_button("Export causal journal JSON",json.dumps(filtered,indent=2,default=str),
                           "causal_journal.json","application/json")
    with tabs[2]:
        st.json(state["equity"]);table(state["positions"]);table(state["risk_events"]);table(state["ledger"])
    with tabs[3]:
        if st.checkbox("Reveal later observed outcomes (hindsight)",value=False,key="hindsight"):
            st.warning("RETROSPECTIVE: this table can contain events later than the replay cursor.")
            table(run["trades"].query("symbol == @symbol and session == @session"))
        else:st.info("Future outcomes are hidden. Normal replay contains completed information only.")

elif page=="Strategy Lab":
    st.warning("Frozen comparisons on previously observed data. No parameter tuning or new out-of-sample claim.")
    comp=store.comparison(period)
    columns=["variant","signals","executed_trades","rejected","win_rate","expectancy_usd","expectancy_r",
             "net_pnl","max_drawdown_pct","spread_slippage","fees","average_open_exposure_fraction","active_trade_sessions"]
    table(comp[columns])
    st.plotly_chart(style(px.bar(comp,x="variant",y="net_pnl",color="net_pnl",
        color_continuous_scale=["#fc7385","#35d4ab"])),width="stretch")
    st.markdown("#### Selected strategy: sample gates and descriptive evidence")
    st.json(m)
    st.markdown("#### Matched-control evidence")
    st.json(store.report["windows"][period]["matched_comparisons"])
    st.caption("Null statistics mean insufficient evidence. Control seeds are correlated counterfactuals, not independent samples.")

elif page=="Portfolio & Risk":
    st.info("RETROSPECTIVE full-period analytics. Use Market Intelligence for a time-limited replay.")
    metric_row([("Net P&L",money(m["net_pnl"])),("Transaction costs",money(m["spread_slippage"]+m["fees"])),
                ("Rejected entries",m["rejected"]),("Maximum identity error",f'{m["max_identity_error"]:.2e}')])
    st.plotly_chart(portfolio(run["equity"].query("phase == 'close'")),width="stretch")
    risk,by_symbol=risk_view(run)
    close=risk[risk.phase=="close"]
    st.plotly_chart(style(px.line(close,x="timestamp",y=["realized_pnl","unrealized_pnl"],
        title="Recorded realized / unrealized P&L"),360),width="stretch")
    st.plotly_chart(style(px.line(close,x="timestamp",y="planned_risk_pct",
        title="Planned open risk / equity (%)"),300),width="stretch")
    if not by_symbol.empty:
        st.plotly_chart(style(px.line(by_symbol[by_symbol.phase=="close"],x="timestamp",
            y="symbol_exposure_pct",color="symbol",markers=True,
            title="Symbol exposure at recorded position snapshots (flat intervals omitted)"),350),width="stretch")
    st.json(reconciliation(run))
    st.markdown("#### Frozen risk limits")
    st.json(store.protocol["portfolio"])
    st.markdown("#### Marked positions / risk budget")
    table(run["positions"].tail(100))
    table(run["equity"][["timestamp","phase","planned_open_risk","equity","blocked"]].tail(100))
    table(run["risk_events"])
    trades=run["trades"]
    if trades.empty: st.info("No simulated trades in this experiment.")
    else:
        trade_id=st.selectbox("Inspect historical trade",trades.trade_id.tolist())
        t=trades.loc[trades.trade_id==trade_id].iloc[0]
        st.json(json.loads(t.to_json()))
        st.caption("Net P&L is the frozen engine's exit proceeds minus entry debit; costs are already included.")
        decisions=run["decisions"]
        table(decisions[(decisions.symbol==t.symbol)&(decisions.known_at==t.signal_known_at)])
        table(run["ledger"][(run["ledger"].symbol==t.symbol)&
              (pd.to_datetime(run["ledger"].timestamp,utc=True)>=pd.Timestamp(t.entry_at))&
              (pd.to_datetime(run["ledger"].timestamp,utc=True)<=pd.Timestamp(t.exit_known_by))])
    table(run["decisions"].query("status != 'executed'"))

else:
    st.markdown("#### Frozen source and dataset integrity")
    try:
        _,check=integrity()
        st.success("Current source / artifact hashes verified")
        st.json(check)
    except (OSError,ValueError) as exc: st.error(str(exc))
    st.json(store.metadata)
    with st.expander("Frozen configuration"):
        st.json(store.protocol)
    st.markdown("#### Test and reproducibility evidence")
    for label,path in [("Original V4.1 verification",BASE/"out/reproducibility_verification.json"),
                       ("Rerun baseline",ROOT/"checkpoint/research_sr_v4_1/out/test_summary.json"),
                       ("Terminal tests",ROOT/"out/test_summary.json")]:
        st.markdown("**"+label+"**")
        if path.exists(): st.json(read_json(path))
        else: st.info("No executed evidence saved yet.")
    st.markdown("#### Prospective intake — dry run only")
    st.json(validate_manifest())
    st.caption("No evaluation path is provided. A versioned local manifest is validated by the documented command.")
    export=st.selectbox("Read-only report export",["equity","cash","positions","trades","decisions","risk_events","ledger","metrics","audit"])
    data=run[export]
    raw=data.to_csv(index=False) if isinstance(data,pd.DataFrame) else json.dumps(data,indent=2)
    ext="csv" if isinstance(data,pd.DataFrame) else "json"
    st.download_button("Download existing report",raw,f"{period}_{variant}_{export}.{ext}",
        "text/csv" if ext=="csv" else "application/json")

