"""TradeLab employer-facing portfolio demo: real historical daily AAPL sample.

Separate public example (Plotly MIT sample, 2015–2017); does not use
private 15-minute research caches, brokerage APIs or market orders.
Original provider/adjustment provenance is not independently certified.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from demo_daily import (
    SOURCE_URL, daily_indicators, english_report, load_daily_sample, market_chart
)

ROOT = Path(__file__).resolve().parent
REPO = "https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio"

st.set_page_config(
    page_title="TradeLab | Quantitative Research Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
      .stApp { background: #080f1c; color: #e5ebf6; }
      [data-testid="stSidebar"] { background: #0e1a2c; border-right:1px solid #1f3049; }
      .block-container { max-width: 1520px; padding-top: 1.4rem; }
      h1,h2,h3 { letter-spacing: -0.03em; }
      h1 { font-weight: 700 !important; }
      [data-testid="stMetric"] { background: #102137; border:1px solid #253951;
           border-radius: 12px; padding: 12px 14px; }
      .tl-kicker { font-size: .8rem; font-weight: 700; letter-spacing: .18em;
          color: #6ce0c4; }
      .tl-summary { color:#aabed6; font-size:1.04rem; }
    </style>
    """, unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def historical_sample():
    """Immutable bundled historical example; no network access."""
    return load_daily_sample()


def render_replay():
    frame = historical_sample()
    st.markdown("### Historical Market Replay · AAPL")
    st.caption(
        "506 observed daily OHLCV candles · 17 Feb 2015 – 16 Feb 2017 · USD/share · "
        "Source: Plotly historical AAPL dataset (MIT repository). Not live market data."
    )
    if "demo_cursor" not in st.session_state:
        st.session_state.demo_cursor = 350
    st.session_state.demo_cursor = max(220, min(int(st.session_state.demo_cursor), len(frame)))
    c1, c2, c3 = st.columns([7, 1.35, 1.55], gap="small")
    with c1:
        count = st.slider("As-of date · reveal completed trading days only",
                          min_value=220, max_value=len(frame), key="demo_cursor")
    with c2:
        st.write("")
        if st.button("Next day", key="advance_demo", use_container_width=True,
                     disabled=count >= len(frame)):
            st.session_state.demo_cursor = min(count+1, len(frame))
            st.rerun()
    with c3:
        st.write("")
        if st.button("Show full history", key="finish_demo", use_container_width=True,
                     disabled=count >= len(frame)):
            st.session_state.demo_cursor = len(frame)
            st.rerun()
    prefix = frame.iloc[:count].copy()
    observed = prefix.iloc[-1]
    report = english_report(prefix)
    p_change = report["daily_change"]
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Observation date", observed.date.strftime("%d %b %Y"))
    m2.metric("Observed close", f"USD {observed.close:,.2f}",
              f"{p_change:+.2f}%" if p_change is not None else None)
    m3.metric("Observed volume", f"{observed.volume/1_000_000:.2f}M")
    m4.metric("RSI(14), daily", f"{report['rsi']:.1f}" if report["rsi"] is not None else "N/A")
    m5.metric("RVOL, prior 20 days", f"{report['rvol']:.2f}x" if report["rvol"] is not None else "N/A")
    with st.expander("Configure analysis layers", expanded=False):
        c1,c2,c3,c4 = st.columns(4)
        emas = c1.multiselect("EMA · trading days", [20,50,200], default=[20,50], key="demo_ema")
        show_rsi = c2.checkbox("RSI 14", value=True, key="demo_rsi")
        show_structure = c3.checkbox("Confirmed HH/HL/LH/LL", value=True, key="demo_structure")
        show_levels = c4.checkbox("Confirmed high/low levels", value=True, key="demo_levels")
    if not emas:
        st.info("Select at least one EMA period to draw the chart.")
        return
    fig = market_chart(prefix, periods=tuple(emas), show_rsi=show_rsi,
                       show_structure=show_structure, show_levels=show_levels)
    st.plotly_chart(fig, width="stretch", key="daily_aapl_chart")
    st.caption(
        "Causal marker timing: a 2-left / 2-right daily swing is marked at "
        "its CONFIRMATION DATE, never backdated to the candidate swing. "
        "Only the previous 110 observed dates are displayed; calculations "
        "use the entire revealed prefix. Daily periods are not 15-minute periods."
    )
    st.markdown("#### Research Commentary · As-Of Evidence")
    st.caption(
        "English, deterministic observations from the visible daily sample — "
        "not an AI forecast, profitability claim, or trading recommendation."
    )
    cols = st.columns(2)
    for i, section in enumerate(report["sections"]):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown("**"+section["heading"]+"**")
                st.write(section["text"])
    with st.expander("Data source, reproducibility and limitations"):
        st.markdown(
            "The chart uses actual historical daily sample rows hosted by Plotly, "
            "**not invented prices**. The sample was redistributed with attribution "
            "to Plotly's MIT-licensed datasets repository. Original exchange/vendor "
            "provenance and adjustment consistency are not independently validated. "
            "No data is downloaded, no broker credentials are read and no orders "
            "are submitted. This sample is not the source of the V4.1 15-minute results."
        )
        st.link_button("Open original AAPL sample", SOURCE_URL)
        st.link_button("Inspect reproducible data and methodology", f"{REPO}/blob/main/docs/DEMO_REAL_DATA.md")


def render_results():
    st.subheader("Research findings · actual archived analysis")
    st.caption(
        "The figures and P&L below are taken from previously inspected "
        "historical research, not from the separate AAPL daily sample or a live backtest."
    )
    st.image(str(ROOT / "docs/images/research-results.png"),
             caption="Archived V4.1 hypothetical results and separate cost-sensitivity experiment")
    st.markdown("**Three candidate portfolios · 42 already-inspected sessions · $100,000 per candidate · 3 bp/side**")
    st.dataframe(
        pd.DataFrame([
            {"Candidate": "Support touch", "Trades": 53, "Net P&L ($)": -93.36, "Net return (%)": -0.0934},
            {"Candidate": "Rejection", "Trades": 9, "Net P&L ($)": -131.15, "Net return (%)": -0.1312},
            {"Candidate": "Trend filtered", "Trades": 4, "Net P&L ($)": -24.88, "Net return (%)": -0.0249},
        ]),
        hide_index=True,
        width="stretch",
    )
    st.info(
        "All three candidates lost money after the assumed costs. A paired "
        "bootstrap confidence interval for the touch-minus-control comparison "
        "crosses zero. No profitable edge is established."
    )
    st.link_button("Full research evidence", f"{REPO}/blob/main/docs/SR_RESEARCH_EVIDENCE.md")
    st.markdown("#### Experimental discipline")
    st.write(
        "The historic study spans 142 US-equity sessions across SPY, MSFT and QQQ. "
        "The documented V4 sensitivity grid contains 36 configurations; the "
        "earlier samples are not untouched out-of-sample evidence."
    )


def render_data_quality():
    st.subheader("Financial Data Quality Lab")
    st.write(
        "The research workspace includes US Treasury yield-curve and term-spread "
        "analytics plus ECB reference FX returns, validation and SQL reconciliation. "
        "These are stored research results, **not an online data feed in this demo**."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Previous Treasury observations", "3,237")
    c2.metric("Recovered valid tenor rows", "+218")
    c3.metric("Verified derived observations", "3,455")
    st.write(
        "The original parser overlooked Treasury's **1.5-month maturity** "
        "(`BC_1_5MONTH`) even though the raw file hash was valid. The revised "
        "dataset preserves the parent snapshot instead of overwriting history."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.image(str(ROOT / "docs/images/stage5-treasury.png"),
                 caption="Local Treasury yield-curve analytics screenshot")
    with c2:
        st.image(str(ROOT / "docs/images/stage5-ecb.png"),
                 caption="Local ECB FX reference-rate analytics screenshot")
    st.link_button("Data-quality case study", f"{REPO}/blob/main/docs/TREASURY_REMEDIATION.md")


def render_ev_lab():
    st.subheader("Probability & Risk Lab")
    st.caption(
        "Interactive hypothetical arithmetic, independent of any observed "
        "stock performance. Not a recommendation or a strategy backtest."
    )
    p = st.slider("Assumed win probability (%)", 1, 99, 45, 1, key="ev_probability")
    a, b, c = st.columns(3)
    gain = a.number_input("Average win (R)", min_value=0.1, max_value=20.0,
                          value=2.0, step=0.1, key="ev_gain")
    loss = b.number_input("Average loss (R)", min_value=0.1, max_value=20.0,
                          value=1.0, step=0.1, key="ev_loss")
    risk = c.number_input("Example planned risk per trade ($)", min_value=1.0,
                          max_value=100000.0, value=100.0, step=10.0, key="ev_risk")
    probability = p / 100
    ev_r = probability * gain - (1 - probability) * loss
    breakeven = loss / (gain + loss)
    col1, col2, col3 = st.columns(3)
    col1.metric("Expected value", f"{ev_r:+.3f} R")
    col2.metric("Break-even win probability", f"{breakeven:.1%}")
    col3.metric("Expected $ per hypothetical attempt", f"{ev_r * risk:+.2f}")
    st.write(
        "Formula: **EV = P(win) × average win − P(loss) × average loss.** "
        "This is an expectation over repeated identical hypothetical opportunities, "
        "not the expected result of the next individual trade."
    )
    st.caption("R is the defined risk unit. Input probabilities are assumptions, not estimates from TradeLab.")



st.sidebar.markdown("## ◈ TRADELAB")
st.sidebar.caption("QUANTITATIVE RESEARCH · PUBLIC PORTFOLIO")
st.sidebar.markdown("**AAPL / Historical Daily**")
st.sidebar.caption("Observed sample: 2015–2017 · 506 sessions")
st.sidebar.info("Offline historical sample · No account, no API credentials, no orders")
st.sidebar.link_button("GitHub source", REPO, use_container_width=True)
st.sidebar.link_button("Research methodology", f"{REPO}/blob/main/docs/SR_RESEARCH_EVIDENCE.md",
                       use_container_width=True)

st.markdown('<div class="tl-kicker">FINANCIAL RESEARCH / INTERACTIVE CASE STUDIES</div>',
            unsafe_allow_html=True)
st.title("TradeLab · Quantitative Research Terminal")
st.markdown(
    '<div class="tl-summary">From observed market data and causal analysis to '
    'execution-aware portfolio tests, statistical uncertainty and verified financial '
    'data quality.</div>', unsafe_allow_html=True)
st.info(
    "AAPL MARKET REPLAY: historical DAILY market sample (2015–2017). "
    "Separate archived strategy results: MSFT/SPY/QQQ 15-minute research. "
    "No live data, no orders, no demonstrated profitable edge."
)

tab_replay, tab_results, tab_data, tab_ev = st.tabs([
    "📈 Market Replay · AAPL", "📊 Strategy Research", "🏦 Data Quality", "🧮 Risk & Probability",
])
with tab_replay:
    render_replay()
with tab_results:
    render_results()
with tab_data:
    render_data_quality()
with tab_ev:
    render_ev_lab()
st.divider()
st.caption(
    "TradeLab is an independent financial research project. The historical daily AAPL "
    "sample is not used to infer trading alpha. Archived 15-minute portfolio P&L remains "
    "a separate, previously inspected hypothetical study. Stage 7 predictive probabilities "
    "are disabled pending qualifying market-data validation."
)
