"""Read-only US equity inspection from synthetic or user-supplied complete bars."""
from __future__ import annotations

from datetime import date, timedelta
import json
import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from research_sr_v4.data import DataQualityError
from research_workspace.equity_data import SYMBOLS, analyze_prefix, read_uploaded_csv, synthetic_fixture
from research_workspace.equity_provenance import manifest_json
from research_workspace.equity_provider import read_alpaca_history
from research_workspace.equity_indicators import EMA_PERIODS, indicator_frame
from research_workspace.equity_zones import historical_zone_bands
from research_workspace.equity_volume import volume_frame
from research_workspace.equity_structure import confirmed_swing_events, confirmed_trendline_segments
from research_workspace.equity_commentary import commentary_report
from research_workspace.stage7_ui import render_research
from research_workspace.stage7_events import replay_limit, validated_history


def _session_axis(visible):
    """Give every completed bar one adjacent category; no off-session time slots.

    NY-local labels are unique during regular XNYS hours (including DST changes).
    Raw UTC timestamps and the causal feature engine are never changed.
    """
    bar_labels = [stamp.tz_convert('America/New_York').strftime('%Y-%m-%d %H:%M')
                  for stamp in visible.timestamp]
    tickvals, ticktext = [], []
    previous_session = None
    for bar_label, session in zip(bar_labels, visible.session):
        if session != previous_session:
            tickvals.append(bar_label)
            ticktext.append(pd.Timestamp(session).strftime('%d %b'))
            previous_session = session
    return bar_labels, tickvals, ticktext


def equity_chart(prefix, features, symbol, *, ema_periods=(), show_rsi=False,
                 show_volume_average=False, show_trendlines=False,
                 show_structure=False):
    if any(period not in EMA_PERIODS for period in ema_periods):
        raise ValueError('Unsupported EMA period')
    visible = prefix.tail(130)
    bar_labels, day_ticks, day_labels = _session_axis(visible)
    rows = 3 if show_rsi else 2
    heights = [0.62, 0.19, 0.19] if show_rsi else [0.78, 0.22]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.045,
                        row_heights=heights)
    indicators = indicator_frame(prefix) if (ema_periods or show_rsi) else None
    fig.add_trace(go.Candlestick(x=bar_labels, open=visible.open,
                                  high=visible.high, low=visible.low, close=visible.close,
                                  increasing_line_color='#43d6a6', decreasing_line_color='#f27d88',
                                  name='OHLC'), row=1, col=1)
    colors = ['#43d6a6' if c >= o else '#f27d88' for c, o in zip(visible.close, visible.open)]
    fig.add_trace(go.Bar(x=bar_labels, y=visible.volume, marker_color=colors,
                         name='Volume', opacity=0.7), row=2, col=1)
    if show_volume_average:
        volume_analytics = volume_frame(prefix).tail(len(visible))
        fig.add_trace(go.Scatter(
            x=bar_labels, y=volume_analytics['prior_volume_mean_20'],
            mode='lines', name='Prior 20-bar mean',
            line=dict(color='#e8bd72', width=1.6, dash='dash'),
            connectgaps=False,
        ), row=2, col=1)
    if indicators is not None:
        visible_indicator_rows = indicators.tail(len(visible))
        ema_colors = {9: '#39d7bf', 21: '#a788fa', 50: '#f4ae67', 200: '#71a9ee'}
        for period in ema_periods:
            fig.add_trace(go.Scatter(
                x=bar_labels, y=visible_indicator_rows[f'ema_{period}'],
                mode='lines', name=f'EMA {period}',
                line=dict(width=1.8, color=ema_colors[period]),
                connectgaps=False,
            ), row=1, col=1)
        if show_rsi:
            fig.add_trace(go.Scatter(
                x=bar_labels, y=visible_indicator_rows['rsi_14'],
                mode='lines', name='RSI 14', line=dict(width=1.8, color='#f59e57'),
                connectgaps=False,
            ), row=3, col=1)
            for threshold in (30, 70):
                fig.add_hline(y=threshold, row=3, col=1,
                              line_dash='dot', line_color='#748094',
                              opacity=0.6)
    # Draw each zone only across bars where its state is actually present in a
    # completed-bar snapshot. Never extend the final snapshot backwards.
    first_index = len(prefix) - len(visible)
    for band in historical_zone_bands(features['snapshots'], visible_start=first_index):
        first = band['start_index'] - first_index
        last = band['end_index'] - first_index
        fig.add_shape(
            type='rect', xref='x', yref='y',
            x0=bar_labels[first], x1=bar_labels[last],
            x0shift=-0.5, x1shift=0.5,
            y0=band['lower'], y1=band['upper'],
            fillcolor='#39cda1' if band['kind'] == 'support' else '#ee8f8f',
            opacity=0.13, line_width=0, layer='below',
        )
    # Mark the confirmation candle, NOT the earlier pivot candle: the latter
    # was not identifiable until the required right-hand candles had closed.
    pivots = [p for p in features['pivots']
              if first_index <= p['confirmed_index'] < len(prefix)]
    for kind, color, shape in [('support', '#59e6b7', 'triangle-up'),
                               ('resistance', '#f3a2a5', 'triangle-down')]:
        selected = [p for p in pivots if p['kind'] == kind]
        if selected:
            fig.add_trace(go.Scatter(x=[prefix.iloc[p['confirmed_index']].timestamp.tz_convert(
                                         'America/New_York').strftime('%Y-%m-%d %H:%M')
                                         for p in selected],
                                     y=[p['price'] for p in selected], mode='markers',
                                     marker=dict(symbol=shape, size=9, color=color),
                                     customdata=[[p['pivot_at'], p['confirmed_at']] for p in selected],
                                     hovertemplate=('Pivot bar: %{customdata[0]}'
                                                    '<br>Confirmed: %{customdata[1]}'
                                                    '<extra>'+kind+'</extra>'),
                                     name=kind, showlegend=False), row=1, col=1)
    if show_trendlines:
        displayed = set()
        for segment in confirmed_trendline_segments(features, len(prefix)):
            if segment['end_index'] < first_index:
                continue
            start = max(segment['start_index'], first_index)
            end = segment['end_index']
            values = segment['values'][start - segment['start_index']:]
            kind = segment['kind']
            legend_label = ('Confirmed low trendline' if kind == 'support'
                            else 'Confirmed high trendline')
            fig.add_trace(go.Scatter(
                x=bar_labels[start - first_index:end - first_index + 1],
                y=values, mode='lines+markers' if len(values) == 1 else 'lines',
                line=dict(width=1.8, dash='dot',
                          color='#64edb8' if kind == 'support' else '#f5b087'),
                marker=dict(size=5), name=legend_label,
                legendgroup=kind + '-trend', showlegend=kind not in displayed,
                hovertemplate='%{y:.3f} · confirmed-pivot line<extra>' + legend_label + '</extra>',
                connectgaps=False,
            ), row=1, col=1)
            displayed.add(kind)
    if show_structure:
        events = [event for event in confirmed_swing_events(features, len(prefix))
                  if event['confirmed_index'] >= first_index
                  and event['label'] not in ('H0', 'L0')]
        for kind, color in (('support', '#64edb8'), ('resistance', '#f5b087')):
            selected = [event for event in events if event['kind'] == kind]
            if selected:
                fig.add_trace(go.Scatter(
                    x=[bar_labels[e['confirmed_index'] - first_index] for e in selected],
                    y=[e['price'] for e in selected],
                    mode='markers+text', text=[e['label'] for e in selected],
                    textposition='top center',
                    marker=dict(size=6, color=color),
                    textfont=dict(size=10, color=color),
                    customdata=[e['confirmed_at'] for e in selected],
                    hovertemplate='%{text} at %{customdata}<br>Pivot: %{y:.3f}<extra></extra>',
                    name='Confirmed swing '+kind, showlegend=False,
                ), row=1, col=1)
    fig.update_layout(template='plotly_dark', paper_bgcolor='#0b1322', plot_bgcolor='#0b1322',
                      height=570, margin=dict(l=18,r=18,t=54,b=20),
                      title=f'{symbol} · completed 15-minute bars · read-only',
                      xaxis_rangeslider_visible=False, hovermode='x unified',
                      showlegend=bool(ema_periods or show_rsi or show_volume_average or show_trendlines))
    # Ordinal categories compress non-trading periods without inserting prices.
    # Explicit ordering keeps candles, volume and confirmed pivots aligned.
    fig.update_xaxes(type='category', categoryorder='array', categoryarray=bar_labels)
    fig.update_xaxes(tickmode='array', tickvals=day_ticks, ticktext=day_labels,
                     title_text='XNYS sessions · overnight/weekend gaps hidden',
                     row=rows, col=1)
    fig.update_yaxes(title_text='Price (source units)', row=1, col=1)
    fig.update_yaxes(title_text='Volume', row=2, col=1)
    if show_rsi:
        fig.update_yaxes(title_text='RSI (14)', range=[0, 100], row=3, col=1)
    return fig


def render():
    st.caption('US Equity Research · XNYS · 15-minute candles · no orders / no live feed')
    st.warning('Educational, read-only inspection. Uploaded files are structurally checked, '
               'but their market-data origin, license, and historical availability are NOT verified.')
    c1, c2 = st.columns(2)
    symbol = c1.selectbox('Instrument', SYMBOLS, key='equity_symbol')
    mode = c2.radio('Data source', ['Synthetic teaching example', 'Upload my OHLCV CSV', 'Alpaca historical (read-only)'],
                    horizontal=True, key='equity_mode')
    if mode == 'Upload my OHLCV CSV':
        st.caption('Required columns: timestamp,open,high,low,close,volume. '
                   'UTC/offset timestamps; full consecutive XNYS sessions, 15-minute bars, max 5 MB / 5,000 bars.')
        uploaded = st.file_uploader('Choose a local 15-minute OHLCV CSV', type=['csv'], key='equity_upload')
        if uploaded is None:
            st.info('UNAVAILABLE DATA · No file selected. No chart or market result is invented.')
            return
    if mode == 'Alpaca historical (read-only)':
        st.caption('Explicit historical GET only, no broker orders, no disk cache. Local API credentials are read '
                   'from environment variables; never enter them into GitHub or a shared Streamlit deployment.')
        feed = st.selectbox('Alpaca feed', ['iex', 'sip'], key='equity_feed')
        st.caption('IEX contains trades from one exchange; SIP may require additional entitlement. '
                   'Full 15-minute XNYS sessions are required; incomplete provider coverage is rejected.')
        latest = date.today() - timedelta(days=4)
        start_date = st.date_input('First session date', value=latest-timedelta(days=8), key='equity_start')
        end_date = st.date_input('Last session date', value=latest, key='equity_end')
        request_identity = (symbol, feed, str(start_date), str(end_date))
    try:
        if mode == 'Synthetic teaching example':
            frame, meta = synthetic_fixture(symbol)
        elif mode == 'Upload my OHLCV CSV':
            frame, meta = read_uploaded_csv(uploaded.getvalue(), symbol)
        else:
            if st.button('Load historical candles (read-only GET)', key='equity_load_provider'):
                # Credentials are not placed in session state, URL params, or manifests.
                key = os.getenv('ALPACA_API_KEY') or os.getenv('APCA_API_KEY_ID')
                secret = os.getenv('ALPACA_SECRET_KEY') or os.getenv('APCA_API_SECRET_KEY')
                frame, meta = read_alpaca_history(
                    symbol, str(start_date), str(end_date), feed=feed,
                    api_key=key, api_secret=secret,
                )
                st.session_state['equity_provider_snapshot'] = (request_identity, frame, meta)
            snapshot = st.session_state.get('equity_provider_snapshot')
            if snapshot is None or snapshot[0] != request_identity:
                st.info('NO PROVIDER DATA LOADED · Choose historical dates and select Load. No network request runs automatically.')
                return
            _, frame, meta = snapshot
        st.error(meta['origin']) if meta['synthetic'] else st.warning(meta['origin'])
        if meta['synthetic']:
            st.caption('Synthetic price levels near 100 are NOT SPY/MSFT/QQQ quotes or historical returns.')
        frame = validated_history(frame, meta)
        limit = replay_limit(frame)
        if limit < len(frame):
            st.info('Son 20 seans araştırma için ayrılmıştır; grafik, yorum ve sonuçlarda gösterilmez.')
        count = st.slider('As-of replay · completed bars visible', min_value=1,
                          max_value=limit, value=limit, step=1,
                          key='equity_cursor')
        prefix, features = analyze_prefix(frame, count)
        last = features['snapshots'][-1]
        volumes = volume_frame(prefix)
        rvol = volumes['relative_volume_20'].iloc[-1]
        a,b,c,d,e = st.columns(5)
        a.metric('Visible bars', str(len(prefix)))
        b.metric('Latest close', f'{prefix.close.iloc[-1]:.3f}')
        c.metric('ATR (research engine)', f'{last["atr"]:.3f}' if last['atr'] is not None else 'N/A')
        d.metric('Active S/R zones', len(last['zones']))
        e.metric('RVOL / prior 20 bars', f'{rvol:.2f}x' if pd.notna(rvol) else 'N/A')
        ema_selection = st.multiselect(
            'Moving averages · EMA (15-minute bars)',
            options=list(EMA_PERIODS), default=[9, 21], key='equity_ema_overlays'
        )
        show_rsi = st.checkbox('RSI (14) · Wilder smoothing', value=False, key='equity_show_rsi')
        show_volume_average = st.checkbox('Volume baseline · 20 prior bars',
                                          value=True, key='equity_show_volume_average')
        c_trend, c_structure = st.columns(2)
        show_trendlines = c_trend.checkbox('Confirmed trendlines · no hindsight',
                                           value=True, key='equity_show_trendlines')
        show_structure = c_structure.checkbox('Market structure · HH/HL/LH/LL',
                                               value=True, key='equity_show_structure')
        st.plotly_chart(equity_chart(prefix, features, symbol,
                                    ema_periods=tuple(ema_selection), show_rsi=show_rsi,
                                    show_volume_average=show_volume_average,
                                    show_trendlines=show_trendlines,
                                    show_structure=show_structure),
                        width='stretch', key='equity_candles')
        st.caption('Relative volume = current 15-minute bar volume / mean of the previous '
                   '20 completed 15-minute bars. This is NOT time-of-day adjusted; it is '
                   'not evidence of an institutional trader. A missing or zero baseline '
                   'is shown as N/A. IEX and SIP volumes cover different markets.')
        st.caption('HH = Higher High (daha yüksek tepe), HL = Higher Low (daha yüksek dip); '
                   'LH = Lower High, LL = Lower Low. EH/EL = yaklaşık eşit; H0/L0 = ilk onaylı '
                   'tepe/dip. Etiketler pivotun bulunduğu değil, onaylandığı mumda görünür.')
        st.caption('Trendlines use the two most recent confirmed same-kind pivots; each segment '
                   'begins at the second confirmation bar, and stops when a newer pivot changes '
                   'the pair. HH/HL/LH/LL labels appear at confirmation, never at a future-known '
                   'earlier pivot. These are mechanical descriptions, not price targets.')
        render_research(frame, meta, count)
        report = commentary_report(prefix, features, meta)
        st.subheader('Otomatik grafik yorumu · kurala dayalı')
        st.caption('Türkçe analiz sadece replay anında tamamlanan mumları kullanır. '
                   'Tahmin modeli, yatırım tavsiyesi veya canlı işlem sinyali değildir.')
        for section in report['sections']:
            st.markdown('**' + section['heading'] + '** — ' + section['text'])
        with st.expander('Yorumun sayısal dayanakları ve veri sınırları'):
            st.json({'as_of_utc': report['as_of_utc'], 'method': report['method'],
                     'structure': report['structure'], 'evidence': report['evidence']})
        st.download_button('Yorumu ve sayısal dayanakları JSON indir',
                           data=json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                           mime='application/json',
                           file_name=f'equity_{symbol.lower()}_commentary.json',
                           key='equity_commentary_export')
        st.caption('Indicators are descriptive, calculated only from the completed replay prefix. '
                   'EMA 9/21/50/200 require that many available bars; RSI(14) requires 15 closes. '
                   'Insufficient history is shown as unavailable, never backfilled.')
        st.caption('Chart display compresses nights, weekends and holidays. Each candle still represents '
                   'one actual completed 15-minute XNYS bar; hover timestamps are New York local time. '
                   'No missing market data is filled or fabricated.')
        st.caption('S/R bands now show the zone state recorded at each completed candle: '
                   'no zone is projected backward before its confirmation, and updated/invalidated '
                   'levels do not overwrite their history. Pivot triangles are placed at the '
                   'confirmation candle, not at the earlier pivot candle. '
                   'These are bar-close states, not intrabar trade signals.')
        st.caption('The V4 research engine is recalculated using only bars visible at the selected '
                   'replay cursor. Uploaded history has no independently established point-in-time availability.')
        with st.expander('S/R lifecycle events · audit trail'):
            if features['lifecycle']:
                st.dataframe(pd.DataFrame(features['lifecycle'][-50:]),
                             hide_index=True, width='stretch')
            else:
                st.info('No confirmed S/R lifecycle events at this replay cursor.')
        st.subheader('Observed S/R research signals')
        signals = [s for s in features['signals'] if s['signal_index'] < len(prefix)]
        if not signals:
            st.info('No qualifying signals at the current cursor; this is not a zero-return result.')
        else:
            st.dataframe(pd.DataFrame(signals[-25:]), hide_index=True, width='stretch')
        st.download_button('Download replay provenance (JSON)',
                           data=manifest_json(prefix, meta),
                           file_name=f'equity_{symbol.lower()}_replay_manifest.json',
                           mime='application/json', key='equity_manifest_download')
        with st.expander('Latest causal snapshot and data provenance'):
            st.json({'source':meta, 'cursor_known_at_utc':str(prefix.bar_end.iloc[-1]),
                     'latest_snapshot':last, 'signal_count_to_cursor':len(signals),
                     'limits':['OHLCV cannot identify institutional traders or resting order-book liquidity',
                               'No real-data feed authenticity or redistribution rights are verified',
                               'No trading fills, backtest returns or future evaluation are produced']})
    except (ValueError, TypeError, KeyError, DataQualityError, pd.errors.ParserError) as exc:
        st.error('EQUITY DATA REJECTED · '+str(exc))
        st.info('A rejected or incomplete dataset is not automatically repaired or shown as real prices.')
