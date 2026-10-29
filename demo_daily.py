"""Offline historical AAPL DAILY example; separate from TradeLab 15-minute engines.

Data source: https://github.com/plotly/datasets/blob/master/finance-charts-apple.csv
Plotly sample-datasets repository: MIT license. 506 daily observations, 2015-02-17 to 2017-02-16.
Original exchange/vendor/adjustment provenance is not independently audited.
No API requests, accounts or orders; no retrospective signal performance claims.
"""
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from research_workspace.equity_indicators import wilder_rsi
from research_workspace.equity_volume import volume_frame

SAMPLE_PATH = Path(__file__).resolve().parent / "demo_data" / "aapl_daily_2015_2017.csv"
SOURCE_URL = "https://github.com/plotly/datasets/blob/master/finance-charts-apple.csv"
EXPECTED = ("date", "open", "high", "low", "close", "volume")
EXPECTED_ROWS = 506


def load_daily_sample():
    """Validate the entire bundled real-price example before analysis."""
    frame = pd.read_csv(SAMPLE_PATH)
    if tuple(frame.columns) != EXPECTED or len(frame) != EXPECTED_ROWS:
        raise ValueError("Historical daily sample schema/length mismatch")
    frame["date"] = pd.to_datetime(frame.date, format="%Y-%m-%d", errors="raise")
    if (frame.date.isna().any() or frame.date.duplicated().any()
            or not frame.date.is_monotonic_increasing):
        raise ValueError("Historical daily sample dates invalid")
    if (frame.date.iloc[0].strftime("%Y-%m-%d") != "2015-02-17"
            or frame.date.iloc[-1].strftime("%Y-%m-%d") != "2017-02-16"):
        raise ValueError("Historical sample date coverage mismatch")
    for column in EXPECTED[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if (frame[list(EXPECTED[1:])].isna().any().any()
            or not frame[list(EXPECTED[1:])].map(lambda v: bool(pd.notna(v) and abs(v) < float("inf"))).all().all()):
        raise ValueError("Invalid numeric daily sample")
    if ((frame[["open", "high", "low", "close"]] <= 0).any().any()
            or (frame.volume < 0).any()):
        raise ValueError("Invalid price or volume")
    if ((frame.high < frame[["open", "low", "close"]].max(axis=1)).any()
            or (frame.low > frame[["open", "high", "close"]].min(axis=1)).any()):
        raise ValueError("Incoherent OHLC sample")
    return frame.reset_index(drop=True)


def daily_indicators(prefix):
    """Daily-period indicators with warm-up, using the visible prefix only."""
    close = prefix.close.reset_index(drop=True)
    result = pd.DataFrame(index=range(len(prefix)))
    for period in (20, 50, 200):
        result[f"ema_{period}"] = close.ewm(span=period, adjust=False, min_periods=period).mean()
    result["rsi_14"] = wilder_rsi(close)
    result["relative_volume_20"] = volume_frame(prefix).relative_volume_20
    return result


def confirmed_pivots(prefix, left=2, right=2):
    """A pivot becomes available only AFTER the right-side daily bars close."""
    if type(left) is not int or type(right) is not int or left < 1 or right < 1:
        raise ValueError("Invalid pivot confirmation")
    result, last_seen = [], {}
    for pivot in range(left, len(prefix) - right):
        row = prefix.iloc[pivot]
        highs = list(prefix.high.iloc[pivot-left:pivot]) + list(prefix.high.iloc[pivot+1:pivot+right+1])
        lows = list(prefix.low.iloc[pivot-left:pivot]) + list(prefix.low.iloc[pivot+1:pivot+right+1])
        kinds = []
        if float(row.high) > max(highs):
            kinds.append(("high", float(row.high)))
        if float(row.low) < min(lows):
            kinds.append(("low", float(row.low)))
        for kind, value in kinds:
            prior = last_seen.get(kind)
            label = ("H0" if kind == "high" else "L0") if prior is None else (
                ("HH" if value > prior else "LH") if kind == "high"
                else ("LL" if value < prior else "HL"))
            result.append(dict(kind=kind, pivot_index=pivot, confirmed_index=pivot+right,
                               price=value, label=label,
                               pivot_date=prefix.date.iloc[pivot].strftime("%Y-%m-%d"),
                               known_at=prefix.date.iloc[pivot+right].strftime("%Y-%m-%d")))
            last_seen[kind] = value
    return result


def market_chart(prefix, periods=(20, 50), show_rsi=True, show_structure=True, show_levels=True):
    """Replay chart: no level or swing is plotted before its confirmation."""
    if not periods or any(k not in (20, 50, 200) for k in periods):
        raise ValueError("Invalid daily EMA periods")
    if prefix.empty:
        raise ValueError("Empty replay")
    n = len(prefix)
    first = max(0, n - 110)
    visible = prefix.iloc[first:]
    all_dates = prefix.date.dt.strftime("%Y-%m-%d").to_list()
    dates = all_dates[first:]
    ind = daily_indicators(prefix).iloc[first:]
    pivots = confirmed_pivots(prefix)
    fig = make_subplots(rows=3 if show_rsi else 2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.045,
                        row_heights=[0.63, 0.2, 0.17] if show_rsi else [0.75, 0.25])
    fig.add_trace(go.Candlestick(x=dates, open=visible.open, high=visible.high,
                                 low=visible.low, close=visible.close,
                                 increasing_line_color="#3bdec1", decreasing_line_color="#f47782",
                                 name="AAPL · observed daily OHLC", showlegend=False), row=1, col=1)
    fig.add_trace(go.Bar(x=dates, y=visible.volume,
                         marker_color=["#3bdec1" if c >= o else "#f47782"
                                       for c,o in zip(visible.close, visible.open)],
                         name="Volume", showlegend=False, opacity=0.65), row=2, col=1)
    for period, color in ((20, "#6bb7fd"), (50, "#f4bd76"), (200, "#ae9aff")):
        if period in periods:
            fig.add_trace(go.Scatter(x=dates, y=ind[f"ema_{period}"],
                                     line=dict(color=color, width=1.7),
                                     name=f"EMA {period} days", connectgaps=False), row=1, col=1)
    if show_rsi:
        fig.add_trace(go.Scatter(x=dates, y=ind.rsi_14, mode="lines",
                                 line=dict(color="#c7a7ff", width=1.8),
                                 name="RSI 14 days", connectgaps=False), row=3, col=1)
        for level in (30, 70):
            fig.add_hline(y=level, row=3, col=1, line_color="#576b83",
                          line_dash="dot", line_width=1)
        fig.update_yaxes(range=[0, 100], title="RSI", row=3, col=1)
    if show_structure:
        for kind, color in (("high", "#ffb08b"), ("low", "#79ebc3")):
            observed = [e for e in pivots if e["kind"] == kind and e["confirmed_index"] >= first]
            if observed:
                fig.add_trace(go.Scatter(
                    x=[all_dates[e["confirmed_index"]] for e in observed],
                    y=[e["price"] for e in observed], mode="markers+text",
                    text=[e["label"] for e in observed], textposition="top center",
                    marker=dict(size=7, color=color), textfont=dict(size=10, color=color),
                    customdata=[[e["pivot_date"], e["known_at"]] for e in observed],
                    hovertemplate="Swing date: %{customdata[0]}<br>Known: %{customdata[1]}<br>USD %{y:.2f}<extra></extra>",
                    name=f"Confirmed {kind} pivots", showlegend=False), row=1, col=1)
    if show_levels:
        for kind, color in (("high", "#ffb08b"), ("low", "#79ebc3")):
            events = [e for e in pivots if e["kind"] == kind]
            if events:
                event = events[-1]
                start = max(first, event["confirmed_index"])
                fig.add_trace(go.Scatter(
                    x=[all_dates[start], all_dates[-1]],
                    y=[event["price"], event["price"]], mode="lines",
                    line=dict(color=color, width=1.5, dash="dash"),
                    name=f"Confirmed {kind} level", showlegend=True), row=1, col=1)
    fig.update_layout(template="plotly_dark", height=630, hovermode="x unified",
                      paper_bgcolor="#0b1628", plot_bgcolor="#0b1628",
                      font=dict(color="#d7e5f3"), margin=dict(l=15,r=25,t=35,b=15),
                      legend=dict(orientation="h", y=1.08), xaxis_rangeslider_visible=False)
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=dates)
    fig.update_yaxes(title="USD/share", row=1, col=1)
    fig.update_yaxes(title="Volume", row=2, col=1)
    return fig


def english_report(prefix):
    """Deterministic English commentary with no fitted forecast or future data."""
    if prefix.empty:
        raise ValueError("Empty prefix")
    row = prefix.iloc[-1]
    ind = daily_indicators(prefix).iloc[-1]
    events = confirmed_pivots(prefix)
    latest_high = next((e for e in reversed(events) if e["kind"] == "high"), None)
    latest_low = next((e for e in reversed(events) if e["kind"] == "low"), None)
    current = float(row.close)
    change = 100 * (current / float(prefix.close.iloc[-2]) - 1) if len(prefix) > 1 else None
    def val(v):
        return f"{float(v):.2f}" if pd.notna(v) else "unavailable"
    trend = ("EMA20 above EMA50" if ind.ema_20 > ind.ema_50 else "EMA20 at/below EMA50") \
        if pd.notna(ind.ema_20) and pd.notna(ind.ema_50) else "insufficient history"
    def zone_text(e):
        return f"{e['label']} at USD {e['price']:.2f}, confirmed on {e['known_at']}" if e else "not yet confirmed"
    sections = [
        ("Market snapshot", f"Daily replay as of {row.date:%d %b %Y}. Observed close: USD {current:.2f}; "
         + (f"one-day price change: {change:+.2f}%." if change is not None else "no prior close.")),
        ("Trend and momentum", f"{trend}. EMA20: {val(ind.ema_20)}; EMA50: {val(ind.ema_50)}. "
         f"RSI(14): {val(ind.rsi_14)}. These readings are descriptive, not trading instructions."),
        ("Confirmed structure", f"Latest high: {zone_text(latest_high)}. "
         f"Latest low: {zone_text(latest_low)}. A swing appears only after two later trading days complete."),
        ("Volume context", f"Observed volume: {float(row.volume):,.0f} shares; "
         f"RVOL vs the prior 20 days: {val(ind.relative_volume_20)}x. "
         "This is not evidence of institutional order flow."),
        ("Research provenance", "Observed historical AAPL daily OHLCV from the Plotly sample dataset (2015–2017). "
         "Original vendor and adjustment provenance are not independently verified. "
         "These daily bars are unrelated to TradeLab's archived 15-minute backtests."),
    ]
    return dict(asof=row.date.strftime("%Y-%m-%d"),close=current,
                daily_change=change, rsi=float(ind.rsi_14) if pd.notna(ind.rsi_14) else None,
                rvol=float(ind.relative_volume_20) if pd.notna(ind.relative_volume_20) else None,
                sections=[dict(heading=h, text=t) for h,t in sections])
