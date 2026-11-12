"""Turkish market terminal for completed US-equity bars and causal research."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from research_sr_v4.data import DataQualityError, schedule
from research_workspace.equity_data import SYMBOLS, analyze_prefix, read_uploaded_csv, synthetic_fixture
from research_workspace.equity_provenance import manifest_json
from research_workspace.equity_provider import (
    EquityProviderError, alpaca_credentials_status, read_configured_alpaca_history,
)
from research_workspace.equity_indicators import EMA_PERIODS, indicator_frame
from research_workspace.equity_zones import historical_zone_bands
from research_workspace.equity_volume import volume_frame
from research_workspace.equity_structure import confirmed_swing_events, confirmed_trendline_segments
from research_workspace.equity_commentary import commentary_report
from research_workspace.stage7_ui import render_research
from research_workspace.stage7_preparation_ui import render_preparation
from research_workspace.stage7_events import SEALED_START, fingerprint, replay_limit, validated_history


_ALPACA = 'Alpaca historical (read-only)'
_CSV = 'Upload my OHLCV CSV'
_SYNTHETIC = 'Synthetic teaching example'
_SOURCE_LABELS = {_ALPACA: 'Alpaca', _CSV: 'CSV dosyası', _SYNTHETIC: 'Sentetik demo'}
_INSTRUMENTS = {'SPY': 'S&P 500 ETF', 'MSFT': 'Microsoft', 'QQQ': 'Nasdaq-100 ETF'}
_SNAPSHOT_KEY = 'equity_provider_snapshot'
_LOOPBACK = ('127.0.0.1', '::1', 'localhost')
_UP, _DOWN = '#45D9AA', '#FF8292'
_CHART_BG, _TEXT, _MUTED, _GRID = '#0D131D', '#EAF0F7', '#9BAFC5', '#243347'
_LEGEND_LABELS = {
    'Prior 20-bar mean': '20 mumluk hacim ort.',
    'Confirmed low trendline': 'Dip trend çizgisi',
    'Confirmed high trendline': 'Tepe trend çizgisi',
}


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
            ticktext.append(pd.Timestamp(session).strftime('%d.%m'))
            previous_session = session
    return bar_labels, tickvals, ticktext


def equity_chart(prefix, features, symbol, *, ema_periods=(), show_rsi=False,
                 show_volume_average=False, show_trendlines=False,
                 show_structure=False, currency=None):
    if any(period not in EMA_PERIODS for period in ema_periods):
        raise ValueError('Unsupported EMA period')
    visible = prefix.tail(130)
    bar_labels, day_ticks, day_labels = _session_axis(visible)
    rows = 3 if show_rsi else 2
    heights = [0.66, 0.17, 0.17] if show_rsi else [0.82, 0.18]
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.035,
                        row_heights=heights)
    indicators = indicator_frame(prefix) if (ema_periods or show_rsi) else None
    candle_details = [
        f'Açılış {o:.2f} · Kapanış {c:.2f}<br>Dip {l:.2f} · Tepe {h:.2f}'
        for o, h, l, c in zip(visible.open, visible.high, visible.low, visible.close)
    ]
    fig.add_trace(go.Candlestick(x=bar_labels, open=visible.open,
                                  high=visible.high, low=visible.low, close=visible.close,
                                  increasing_line_color=_UP, decreasing_line_color=_DOWN,
                                  hovertext=candle_details, hoverinfo='text',
                                  name='Fiyat', showlegend=False), row=1, col=1)
    colors = [_UP if c >= o else _DOWN for c, o in zip(visible.close, visible.open)]
    fig.add_trace(go.Bar(x=bar_labels, y=visible.volume, marker_color=colors,
                         name='Hacim', opacity=0.55, showlegend=False,
                         hovertemplate='%{y:,.0f}<extra>Hacim</extra>'), row=2, col=1)
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
                                     marker=dict(symbol=shape, size=7, color=color),
                                     customdata=[[p['pivot_at'], p['confirmed_at']] for p in selected],
                                     hovertemplate=('Dönüş mumu %{customdata[0]}'
                                                    '<br>Onay %{customdata[1]}'
                                                    '<extra>'+('Destek' if kind == 'support' else 'Direnç')+'</extra>'),
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
                hovertemplate='%{y:.2f}<extra>' + _LEGEND_LABELS[legend_label] + '</extra>',
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
                    hovertemplate='%{text} · %{customdata}<br>Seviye %{y:.2f}<extra></extra>',
                    name='Confirmed swing '+kind, showlegend=False,
                ), row=1, col=1)
    fig.update_layout(
        template='plotly_dark', paper_bgcolor=_CHART_BG, plot_bgcolor=_CHART_BG,
        font=dict(family='Segoe UI, sans-serif', size=12, color=_TEXT),
        height=590 if show_rsi else 510, margin=dict(l=12, r=18, t=42, b=16),
        title=dict(text=f'{symbol} · 15 dk', x=0.018, font=dict(size=15)),
        xaxis_rangeslider_visible=False, hovermode='x unified',
        hoverlabel=dict(bgcolor='#141E2B', bordercolor=_GRID, font_color=_TEXT),
        legend=dict(orientation='h', x=0, y=-0.12, xanchor='left', yanchor='top',
                    font=dict(size=10, color=_MUTED)),
        showlegend=bool(ema_periods or show_rsi or show_volume_average or show_trendlines),
    )
    # Ordinal categories compress non-trading periods without inserting prices.
    # Explicit ordering keeps candles, volume and confirmed pivots aligned.
    fig.update_xaxes(type='category', categoryorder='array', categoryarray=bar_labels,
                     showgrid=False, linecolor=_GRID, tickfont=dict(color=_MUTED))
    fig.update_xaxes(tickmode='array', tickvals=day_ticks, ticktext=day_labels,
                     row=rows, col=1)
    fig.update_yaxes(side='right', gridcolor=_GRID, zeroline=False,
                     tickfont=dict(color=_MUTED), automargin=True)
    fig.update_yaxes(title_text='USD' if currency == 'USD' else 'Fiyat',
                     tickformat='.2f', row=1, col=1)
    fig.update_yaxes(title_text='Hacim', tickformat='.2s', row=2, col=1)
    if show_rsi:
        fig.update_yaxes(title_text='RSI (14)', range=[0, 100], row=3, col=1)
    return fig


def _completed_session_window(now=None):
    """Use the five latest fully closed, eligible sessions in the calendar."""
    clock = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    if clock.tzinfo is None:
        raise ValueError('An aware session clock is required')
    last_allowed = date.fromisoformat(SEALED_START) - timedelta(days=1)
    candidate = min(clock.tz_convert('America/New_York').date(), last_allowed)
    calendar = schedule(candidate - timedelta(days=30), candidate)
    dates = calendar.index[calendar.close <= clock]
    if dates.empty:
        raise ValueError('No completed session available in the current window')
    return dates[-min(5, len(dates))].date(), dates[-1].date()


def _provider_message(code):
    messages = {
        'credentials_missing': 'Bu yerel oturumda Alpaca anahtarları bulunamadı.',
        'credentials_incomplete': 'Alpaca anahtar çifti eksik. Yerel yapılandırmayı kontrol edin.',
        'authentication': 'Alpaca bu anahtar çiftini reddetti. Yerel Alpaca yapılandırmasını güncelleyip tekrar deneyin.',
        'entitlement': 'Alpaca hesabı bu veri akışına erişemiyor. IEX seçeneğini veya veri aboneliğini kontrol edin.',
        'rate_limit': 'Alpaca istek sınırına ulaşıldı. Bir süre sonra tekrar deneyin.',
        'unavailable': 'Alpaca şu anda yanıt vermiyor. Bağlantıyı kontrol edip tekrar deneyin.',
        'sealed_range': 'Bu araştırmada 26.10.2026 ve sonrası kapalı.',
        'coverage': 'Alpaca seçilen aralıkta tüm 15 dakikalık mumları sağlayamadı. Daha kısa bir seans aralığı veya yetkiniz varsa SIP seçin.',
        'invalid_data': 'Alpaca yanıtı tam seans veri kontrolünden geçemedi. Tarih aralığını ve veri akışını kontrol edin.',
        'http_error': 'Alpaca isteği kabul etmedi. Veri akışını ve tarih aralığını kontrol edin.',
    }
    return messages.get(code, messages['invalid_data'])


def _provider_snapshot_digest(identity, frame, metadata):
    proof = {'selection': identity, 'bars_sha256': fingerprint(frame), 'source': metadata}
    encoded = json.dumps(proof, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def get_loaded_alpaca_snapshot(symbol=None):
    """Return verified, detached data from this loopback session without a request."""
    if st.get_option('server.address') not in _LOOPBACK:
        return None
    saved = st.session_state.get(_SNAPSHOT_KEY)
    if saved is None:
        return None
    try:
        identity, frame, meta, expected_digest = saved
        bound_symbol, feed, first, last = identity
        if (not isinstance(frame, pd.DataFrame) or not isinstance(meta, dict)
                or meta.get('symbol') != bound_symbol or meta.get('feed') != feed
                or meta.get('provider_api_response') is not True or meta.get('synthetic') is not False
                or expected_digest != _provider_snapshot_digest(identity, frame, meta)):
            raise ValueError('Snapshot identity changed')
        if symbol is not None and symbol != bound_symbol:
            return None
        clean = validated_history(frame, meta)
        if not (first <= clean.session.iloc[0] <= clean.session.iloc[-1] <= last):
            raise ValueError('Snapshot window changed')
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
        st.session_state.pop(_SNAPSHOT_KEY, None)
        return None
    return clean.copy(deep=True), deepcopy(meta)


def _provider_source(symbol):
    if st.get_option('server.address') not in _LOOPBACK:
        st.info('Alpaca yüklemesi yalnızca bu bilgisayara bağlı yerel oturumda kullanılabilir.')
        st.session_state.pop(_SNAPSHOT_KEY, None)
        return None

    first, latest = _completed_session_window()
    feed_col, start_col, end_col, action_col = st.columns((1, 1, 1, 1.45),
                                                         vertical_alignment='bottom')
    feed = feed_col.selectbox('Veri akışı', ('iex', 'sip'), format_func=str.upper, key='equity_feed')
    start_date = start_col.date_input('İlk seans', value=first, min_value=date(2000, 1, 1),
                                      max_value=latest, format='DD.MM.YYYY', key='equity_start')
    end_date = end_col.date_input('Son seans', value=latest, min_value=date(2000, 1, 1),
                                  max_value=latest, format='DD.MM.YYYY', key='equity_end')
    if start_date is None or end_date is None:
        st.session_state.pop(_SNAPSHOT_KEY, None)
        st.caption('Yüklemek için iki seans tarihi seçin.')
        return None
    identity = (symbol, feed, start_date.isoformat(), end_date.isoformat())
    snapshot = st.session_state.get(_SNAPSHOT_KEY)
    if snapshot is not None and (not isinstance(snapshot, tuple) or len(snapshot) != 4 or snapshot[0] != identity):
        st.session_state.pop(_SNAPSHOT_KEY, None)
    ready = alpaca_credentials_status()
    load = action_col.button('Alpaca verisini yükle', key='equity_load_provider',
                             type='primary', width='stretch', disabled=ready != 'configured')
    st.caption('15 dk · 1–10 tam ABD seansı · IEX tek borsa, SIP hesap yetkisine bağlı. '
               'Araştırma dönemi 26.10.2026 öncesiyle sınırlı.')
    if ready != 'configured':
        st.session_state.pop(_SNAPSHOT_KEY, None)
        reason = 'credentials_incomplete' if ready == 'incomplete' else 'credentials_missing'
        st.warning(_provider_message(reason))
        return None
    if not load:
        return get_loaded_alpaca_snapshot(symbol)

    # A failed refresh must not leave an older success under the same identity.
    st.session_state.pop(_SNAPSHOT_KEY, None)
    if start_date > end_date or (end_date - start_date).days > 20:
        st.error('Kronolojik sırada en çok 21 takvim günü seçin.')
        return None
    try:
        with st.spinner(f'{symbol} için {feed.upper()} geçmiş mumları alınıyor…'):
            frame, meta = read_configured_alpaca_history(
                symbol, identity[2], identity[3], feed=feed,
            )
            if (meta.get('symbol') != symbol or meta.get('feed') != feed
                    or meta.get('synthetic') is not False
                    or meta.get('provider_api_response') is not True):
                raise ValueError('Unexpected source identity')
            frame = validated_history(frame, meta)
            if not (identity[2] <= frame.session.iloc[0] <= frame.session.iloc[-1] <= identity[3]):
                raise ValueError('Unexpected requested session window')
    except EquityProviderError as exc:
        st.error(_provider_message(getattr(exc, 'code', None)))
        return None
    except (ValueError, TypeError, KeyError, DataQualityError):
        st.error(_provider_message('invalid_data'))
        return None
    digest = _provider_snapshot_digest(identity, frame, meta)
    st.session_state[_SNAPSHOT_KEY] = (identity, frame.copy(deep=True), deepcopy(meta), digest)
    st.session_state.pop('equity_cursor', None)
    return frame, meta


def _load_source(mode, symbol):
    if mode == _ALPACA:
        return _provider_source(symbol)
    st.session_state.pop(_SNAPSHOT_KEY, None)
    if mode == _SYNTHETIC:
        st.caption('Eğitim amaçlı üretilmiş örnek seri.')
        return synthetic_fixture(symbol)
    st.caption('15 dk tam seanslar ve saat dilimli zaman damgaları gerekli. En fazla 5 MB.')
    uploaded = st.file_uploader('OHLCV dosyası seç', type=['csv'], max_upload_size=5,
                                key='equity_upload')
    return read_uploaded_csv(uploaded.getvalue(), symbol) if uploaded is not None else None


def _format_number(value, decimals=2):
    return f'{value:,.{decimals}f}'.translate(str.maketrans(',.', '.,'))


def _render_chart(prefix, features, meta, limit, holdout):
    symbol = meta['symbol']
    stamp = prefix.bar_end.iloc[-1].tz_convert('Europe/Istanbul')
    source = ('Sentetik demo' if meta['synthetic'] else
              f'Alpaca · {meta["feed"].upper()}' if meta.get('provider_api_response') is True else
              'Kullanıcı CSV')
    unit = 'USD' if meta.get('currency') == 'USD' else ''
    st.markdown(f'#### {symbol} · {_INSTRUMENTS[symbol]}')
    st.caption(f'{source} · 15 dk · Gözlem {stamp:%d.%m.%Y %H:%M} TSİ')
    if meta['synthetic']:
        st.warning('Sentetik veri · Fiyatlar ve hacimler eğitim amacıyla üretilmiştir.')
    if holdout:
        st.caption('Ayrılmış son 20 seans, grafik ve analiz dışında tutuluyor.')
    close = prefix.close.iloc[-1]
    previous = prefix.close.iloc[-2] if len(prefix) > 1 else None
    move = f'{_format_number((close / previous - 1) * 100)}%' if previous is not None else None
    rvol = volume_frame(prefix)['relative_volume_20'].iloc[-1]
    price, volume, relative, bars = st.columns(4)
    price.metric('Son kapanış', f'{_format_number(close)} {unit}'.strip(), delta=move,
                 help='Değişim bir önceki tamamlanmış 15 dakikalık muma göredir.')
    volume.metric('Son mum hacmi', _format_number(prefix.volume.iloc[-1], 0))
    relative.metric('Göreli hacim', f'{_format_number(rvol)}×' if pd.notna(rvol) else '—',
                    help='Önceki 20 tamamlanmış mumun ortalama hacmine göre.')
    bars.metric('Görünür mum', f'{len(prefix)} / {limit}')
    with st.expander('Gösterge ve grafik ayarları'):
        c1, c2, c3 = st.columns((2, 1, 1))
        periods = c1.multiselect('Üstel ortalamalar', options=list(EMA_PERIODS), default=[9, 21],
                                 key='equity_ema_overlays')
        show_rsi = c2.checkbox('RSI (14)', value=False, key='equity_show_rsi')
        show_volume_average = c2.checkbox('Hacim ortalaması', value=True,
                                          key='equity_show_volume_average')
        show_trendlines = c3.checkbox('Trend çizgileri', value=True, key='equity_show_trendlines')
        show_structure = c3.checkbox('Tepe ve dip etiketleri', value=True,
                                     key='equity_show_structure')
    figure = equity_chart(prefix, features, symbol, ema_periods=tuple(periods), show_rsi=show_rsi,
                          show_volume_average=show_volume_average, show_trendlines=show_trendlines,
                          show_structure=show_structure, currency=unit)
    figure.update_layout(title_text=f'{symbol} · 15 dk · {source}')
    for trace in figure.data:
        trace.name = _LEGEND_LABELS.get(trace.name, trace.name)
    st.plotly_chart(figure, width='stretch', theme=None, key='equity_candles',
                    config={'displaylogo': False, 'responsive': True,
                            'modeBarButtonsToRemove': ['lasso2d', 'select2d']})
    st.caption('Grafik saatleri New York yerel saatidir. Seans araları sıkıştırılır. '
               'Bölgeler ve dönüş etiketleri onaylandıkları mumdan itibaren gösterilir.')


def _render_analysis(prefix, features, meta):
    snapshot = features['snapshots'][-1]
    left, right = st.columns(2)
    left.metric('ATR · ortalama gerçek aralık',
                _format_number(snapshot['atr']) if snapshot['atr'] is not None else '—')
    right.metric('Aktif destek / direnç bölgeleri', len(snapshot['zones']))
    st.markdown('#### Grafiğin teknik okuması')
    st.caption('Kurala dayalı yorum, seçili gözlem anına kadar kapanmış mumları kullanır.')
    report = commentary_report(prefix, features, meta)
    for section in report['sections']:
        st.markdown(f'**{section["heading"]}**')
        st.write(section['text'])
    with st.expander('Hesaplama ayrıntıları ve kanıtlar'):
        st.caption('EMA için ilgili pencere kadar mum, RSI (14) için 15 kapanış gerekir. '
                   'Göreli hacim saat dilimi profiline göre normalize edilmez. '
                   'IEX ve SIP hacim kapsamları farklıdır.')
        st.json({'as_of_utc': report['as_of_utc'], 'method': report['method'],
                 'structure': report['structure'], 'evidence': report['evidence']})
    st.download_button('Teknik yorumu indir', data=json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                       mime='application/json', file_name=f'equity_{meta["symbol"].lower()}_commentary.json',
                       key='equity_commentary_export', on_click='ignore')


def _render_archive(frame, prefix, features, meta):
    render_research(frame, meta, len(prefix))
    with st.expander('Onaylanmış destek / direnç kayıtları'):
        if features['lifecycle']:
            st.dataframe(pd.DataFrame(features['lifecycle'][-50:]), hide_index=True, width='stretch')
        else:
            st.caption('Bu gözlem anında kayıt bulunmuyor.')
        signals = [signal for signal in features['signals'] if signal['signal_index'] < len(prefix)]
        if signals:
            st.dataframe(pd.DataFrame(signals[-25:]), hide_index=True, width='stretch')
        else:
            st.caption('Seçili anda araştırma koşullarına uyan sinyal bulunmuyor.')
    st.download_button('Veri kaynağı özetini indir', data=manifest_json(prefix, meta),
                       file_name=f'equity_{meta["symbol"].lower()}_replay_manifest.json',
                       mime='application/json', key='equity_manifest_download', on_click='ignore')
    with st.expander('Kaynak ve gözlem zamanı'):
        st.json({'source': meta, 'cursor_known_at_utc': prefix.bar_end.iloc[-1].isoformat(),
                 'latest_snapshot': features['snapshots'][-1], 'signal_count_to_cursor': len(signals)})


def render():
    with st.container(border=True):
        st.markdown('#### Veri ve seans')
        instrument_col, mode_col = st.columns((1, 3))
        symbol = instrument_col.selectbox('Enstrüman', SYMBOLS, key='equity_symbol')
        mode = mode_col.radio('Veri kaynağı', tuple(_SOURCE_LABELS), format_func=_SOURCE_LABELS.__getitem__,
                              horizontal=True, key='equity_mode')
        try:
            loaded = _load_source(mode, symbol)
            if loaded is not None:
                frame, meta = loaded
                frame = validated_history(frame, meta)
                limit = replay_limit(frame)
        except (ValueError, TypeError, KeyError, DataQualityError, pd.errors.ParserError):
            st.session_state.pop(_SNAPSHOT_KEY, None)
            st.error('Veri doğrulanamadı. Mum zamanlarını, dosya biçimini ve tam seans kapsamını kontrol edin.')
            loaded = None

    chart, analysis, archive = st.tabs(('Fiyat grafiği', 'Teknik analiz', 'Araştırma ve veri kaydı'))
    if loaded is None:
        with chart, st.container(border=True):
            st.markdown('#### Grafik verisi bekleniyor')
            st.info('Alpaca verisini yüklemek için enstrüman, veri akışı ve tarihleri seçin.'
                    if mode == _ALPACA else 'Grafiği görmek için uygun bir OHLCV dosyası seçin.')
        with analysis:
            st.caption('Teknik okuma, veri yüklendiğinde hazırlanır.')
    else:
        with chart:
            count = st.slider('Geçmişi incele · görünür tamamlanmış mumlar', min_value=1,
                              max_value=limit, value=limit, step=1, key='equity_cursor')
            prefix, features = analyze_prefix(frame, count)
            _render_chart(prefix, features, meta, limit, limit < len(frame))
        with analysis:
            _render_analysis(prefix, features, meta)
        with archive:
            _render_archive(frame, prefix, features, meta)
    with archive, st.expander('Veri hazırlama araçları'):
        render_preparation()
