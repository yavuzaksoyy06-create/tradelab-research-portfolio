"""Read-only US equity inspection from synthetic or user-supplied complete bars."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from research_sr_v4.data import DataQualityError
from research_workspace.equity_data import SYMBOLS, analyze_prefix, read_uploaded_csv, synthetic_fixture


def equity_chart(prefix, features, symbol):
    visible = prefix.tail(130)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.78, 0.22])
    fig.add_trace(go.Candlestick(x=visible.timestamp, open=visible.open,
                                  high=visible.high, low=visible.low, close=visible.close,
                                  increasing_line_color='#43d6a6', decreasing_line_color='#f27d88',
                                  name='OHLC'), row=1, col=1)
    colors = ['#43d6a6' if c >= o else '#f27d88' for c, o in zip(visible.close, visible.open)]
    fig.add_trace(go.Bar(x=visible.timestamp, y=visible.volume, marker_color=colors,
                         name='Volume', opacity=0.7), row=2, col=1)
    latest = features['snapshots'][-1]
    for zone in latest['zones']:
        fig.add_hrect(y0=zone['lower'], y1=zone['upper'],
                      fillcolor='#39cda1' if zone['kind']=='support' else '#ee8f8f',
                      opacity=0.15, line_width=0, row=1, col=1)
    first_index = len(prefix) - len(visible)
    pivots = [p for p in features['pivots'] if first_index <= p['pivot_index'] < len(prefix)
              and p['confirmed_index'] < len(prefix)]
    for kind, color, shape in [('support', '#59e6b7', 'triangle-up'),
                               ('resistance', '#f3a2a5', 'triangle-down')]:
        selected = [p for p in pivots if p['kind'] == kind]
        if selected:
            fig.add_trace(go.Scatter(x=[prefix.iloc[p['pivot_index']].timestamp for p in selected],
                                     y=[p['price'] for p in selected], mode='markers',
                                     marker=dict(symbol=shape, size=9, color=color),
                                     customdata=[p['confirmed_at'] for p in selected],
                                     hovertemplate='Confirmed at %{customdata}<extra>'+kind+'</extra>',
                                     name=kind), row=1, col=1)
    fig.update_layout(template='plotly_dark', paper_bgcolor='#0b1322', plot_bgcolor='#0b1322',
                      height=570, margin=dict(l=18,r=18,t=54,b=20),
                      title=f'{symbol} · completed 15-minute bars · read-only',
                      xaxis_rangeslider_visible=False, hovermode='x unified', showlegend=False)
    fig.update_yaxes(title_text='Price (source units)', row=1, col=1)
    fig.update_yaxes(title_text='Volume', row=2, col=1)
    return fig


def render():
    st.caption('US Equity Research · XNYS · 15-minute candles · no orders / no live feed')
    st.warning('Educational, read-only inspection. Uploaded files are structurally checked, '
               'but their market-data origin, license, and historical availability are NOT verified.')
    c1, c2 = st.columns(2)
    symbol = c1.selectbox('Instrument', SYMBOLS, key='equity_symbol')
    mode = c2.radio('Data source', ['Synthetic teaching example', 'Upload my OHLCV CSV'],
                    horizontal=True, key='equity_mode')
    if mode == 'Upload my OHLCV CSV':
        st.caption('Required columns: timestamp,open,high,low,close,volume. '
                   'UTC/offset timestamps; full consecutive XNYS sessions, 15-minute bars, max 5 MB / 5,000 bars.')
        uploaded = st.file_uploader('Choose a local 15-minute OHLCV CSV', type=['csv'], key='equity_upload')
        if uploaded is None:
            st.info('UNAVAILABLE DATA · No file selected. No chart or market result is invented.')
            return
    try:
        if mode == 'Synthetic teaching example':
            frame, meta = synthetic_fixture(symbol)
        else:
            frame, meta = read_uploaded_csv(uploaded.getvalue(), symbol)
        st.error(meta['origin']) if meta['synthetic'] else st.warning(meta['origin'])
        if meta['synthetic']:
            st.caption('Synthetic price levels near 100 are NOT SPY/MSFT/QQQ quotes or historical returns.')
        count = st.slider('As-of replay · completed bars visible', min_value=1,
                          max_value=len(frame), value=len(frame), step=1,
                          key='equity_cursor')
        prefix, features = analyze_prefix(frame, count)
        last = features['snapshots'][-1]
        a,b,c,d = st.columns(4)
        a.metric('Visible bars', str(len(prefix)))
        b.metric('Latest close', f'{prefix.close.iloc[-1]:.3f}')
        c.metric('ATR (research engine)', f'{last["atr"]:.3f}' if last['atr'] is not None else 'N/A')
        d.metric('Active S/R zones', len(last['zones']))
        st.plotly_chart(equity_chart(prefix, features, symbol), width='stretch', key='equity_candles')
        st.caption('Only confirmed pivots and currently active zones are shown. '
                   'The research engine is recalculated using only bars visible at the selected replay cursor. '
                   'Uploaded history has no independently established point-in-time availability.')
        st.subheader('Observed S/R research signals')
        signals = [s for s in features['signals'] if s['signal_index'] < len(prefix)]
        if not signals:
            st.info('No qualifying signals at the current cursor; this is not a zero-return result.')
        else:
            st.dataframe(pd.DataFrame(signals[-25:]), hide_index=True, width='stretch')
        with st.expander('Latest causal snapshot and data provenance'):
            st.json({'source':meta, 'cursor_known_at_utc':str(prefix.bar_end.iloc[-1]),
                     'latest_snapshot':last, 'signal_count_to_cursor':len(signals),
                     'limits':['OHLCV cannot identify institutional traders or resting order-book liquidity',
                               'No real-data feed authenticity or redistribution rights are verified',
                               'No trading fills, backtest returns or future evaluation are produced']})
    except (ValueError, TypeError, KeyError, DataQualityError, pd.errors.ParserError) as exc:
        st.error('EQUITY DATA REJECTED · '+str(exc))
        st.info('A rejected or incomplete dataset is not automatically repaired or shown as real prices.')
