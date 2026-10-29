"""Public, synthetic-only TradeLab portfolio demo.

Standalone Streamlit entry point. Uses the repository's real, causal
analysis and plotting code; never loads Alpaca keys, private market caches,
user uploads or order endpoints. Illustrative educational prices only.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from research_workspace.equity_data import SYMBOLS, analyze_prefix, synthetic_fixture
from research_workspace.equity_ui import equity_chart
from research_workspace.equity_commentary import commentary_report
from research_workspace.equity_volume import volume_frame

ROOT = Path(__file__).resolve().parent
REPO = "https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio"

st.set_page_config(
    page_title="TradeLab | Interactive Research Demo",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(
    """
    <style>
      .stApp { background: #091321; color: #e4edf9; }
      [data-testid="stSidebar"] { background: #0d1a2b; }
      .block-container { max-width: 1480px; padding-top: 1.55rem; }
      h1,h2,h3 { letter-spacing: -0.025em; }
      [data-testid="stMetric"] {
        background: #122239; border: 1px solid #263b56;
        border-radius: 11px; padding: 10px 14px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def educational_bars(symbol: str):
    """Reuse deterministic complete-session fixture; no network requests."""
    return synthetic_fixture(symbol)


def render_replay(symbol: str):
    st.subheader("Causal Market Replay")
    st.caption(
        "Educational 15-minute candles · XNYS calendar · all prices are SYNTHETIC "
        "and follow the same generated pattern for each symbol label. "
        "They are not historical SPY/MSFT/QQQ quotes."
    )
    frame, metadata = educational_bars(symbol)

    if "demo_cursor" not in st.session_state:
        st.session_state.demo_cursor = min(125, len(frame))
    st.session_state.demo_cursor = max(25, min(int(st.session_state.demo_cursor), len(frame)))

    left, right = st.columns([5, 2], gap="large")
    with left:
        count = st.slider(
            "Completed bars visible — future bars stay hidden",
            min_value=25, max_value=len(frame),
            key="demo_cursor",
        )
    with right:
        st.write("")
        if st.button("Advance one bar →", use_container_width=True,
                     disabled=count >= len(frame), key="advance_demo"):
            st.session_state.demo_cursor = min(len(frame), count + 1)
            st.rerun()

    prefix, features = analyze_prefix(frame, count)
    last = features["snapshots"][-1]
    rvol = volume_frame(prefix)["relative_volume_20"].iloc[-1]
    columns = st.columns(4)
    columns[0].metric("Visible bars", f"{count} / {len(frame)}")
    columns[1].metric("Last synthetic close", f"{prefix.close.iloc[-1]:.2f}")
    columns[2].metric("Confirmed active S/R zones", str(len(last["zones"])))
    columns[3].metric("RVOL · previous 20 bars", f"{rvol:.2f}×" if pd.notna(rvol) else "N/A")

    with st.expander("Chart layers", expanded=False):
        a, b, c = st.columns(3)
        overlays = a.multiselect("EMA periods · 15-minute bars", [9, 21, 50, 200],
                                 default=[9, 21], key="demo_ema")
        show_rsi = b.checkbox("RSI 14", value=True, key="demo_rsi")
        show_structure = c.checkbox("HH / HL / LH / LL", value=True, key="demo_structure")
        show_trendlines = a.checkbox("Confirmed trendlines", value=True, key="demo_trendlines")
        show_vol_baseline = b.checkbox("Prior-volume baseline", value=True, key="demo_volume")
    st.plotly_chart(
        equity_chart(
            prefix, features, symbol,
            ema_periods=tuple(overlays), show_rsi=show_rsi,
            show_structure=show_structure, show_trendlines=show_trendlines,
            show_volume_average=show_vol_baseline,
        ),
        width="stretch", key="demo_equity_chart",
    )
    st.caption(
        "A pivot appears only when enough later bars have closed to confirm it; "
        "its label is displayed at the **confirmation** candle. The replay "
        "does not draw current zones into earlier candles. There are no orders, "
        "live signals, return predictions or real market prices in this demo."
    )

    st.markdown("#### Evidence-based chart commentary")
    st.caption(
        "This is the repository's deterministic Turkish analysis engine — "
        "not an LLM, not a trade recommendation."
    )
    report = commentary_report(prefix, features, metadata)
    left, right = st.columns(2)
    for index, section in enumerate(report["sections"]):
        with (left if index % 2 == 0 else right):
            with st.expander(section["heading"], expanded=index < 2):
                st.write(section["text"])
    with st.expander("Inspect as-of numerical evidence"):
        st.json(report["evidence"], expanded=False)


def render_results():
    st.subheader("Research findings · actual archived analysis")
    st.caption(
        "The figures and P&L below are taken from previously inspected "
        "historical research, not from the synthetic replay or a live backtest."
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
st.sidebar.caption("INTERACTIVE PORTFOLIO DEMO · SYNTHETIC ONLY")
st.sidebar.warning("No live prices · No credentials · No trades")
symbol = st.sidebar.selectbox("Illustrative instrument label", SYMBOLS, key="demo_symbol")
st.sidebar.caption("All three labels share the same synthetic educational price path.")
st.sidebar.link_button("View source on GitHub", REPO, use_container_width=True)

st.markdown("# TradeLab Research Terminal")
st.write(
    "**A transparent quantitative research workflow**, from causal chart features "
    "to portfolio evaluation and financial data quality."
)
st.warning(
    "PUBLIC DEMO · ALL INTERACTIVE PRICE DATA IS SYNTHETIC. "
    "No Alpaca login, broker connection, private source files or market orders."
)
tab_replay, tab_results, tab_data, tab_ev = st.tabs([
    "📈 Market Replay", "📊 Research Evidence", "🏦 Financial Data Quality", "🧮 Probability & Risk"
])
with tab_replay:
    render_replay(symbol)
with tab_results:
    render_results()
with tab_data:
    render_data_quality()
with tab_ev:
    render_ev_lab()

st.divider()
st.caption(
    "Stage 7 event/probability research is not demonstrated as market-validated: "
    "real historical calibration has not been completed; predictive probabilities "
    "are disabled. The archived research results and the synthetic replay are "
    "deliberately separate."
)
