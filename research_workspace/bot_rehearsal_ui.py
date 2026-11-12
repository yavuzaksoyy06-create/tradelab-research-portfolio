"""Explicit offline bot rehearsal; in-memory bars and reports, never a broker."""
import hashlib
import hmac
import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from research_workspace.bot_rehearsal import (
    build_report, readiness_report, run_rehearsal, verify_report,
)
from research_workspace.equity_data import (
    MAX_BYTES, SYMBOLS, read_uploaded_csv, synthetic_fixture,
)
from research_workspace.equity_ui import get_loaded_alpaca_snapshot
from research_workspace.ise_ml_ui import _report_digest
from research_workspace.stage7_events import replay_limit, validated_history
from research_workspace.bot_stress import run_stress_suite, verify_stress_report

DATA_KEY = "bot_rehearsal_loaded_data"
SYNTHETIC = "Sentetik eğitim örneği"
UPLOADED = "Yerel OHLCV CSV"
ALPACA = "Alpaca · Piyasa Terminali"
SCENARIO_LABELS = {
    "baseline": "Temel",
    "high_cost": "Yüksek maliyet",
    "delay_1_bar": "1 mum gecikme",
    "high_cost_delay_1_bar": "Maliyet + gecikme",
}
SCENARIO_COLORS = ("#45D9AA", "#FF8292", "#A6B7FF", "#F6C784")


def _source_label(metadata):
    if metadata["synthetic"]:
        return "Sentetik veri", "synthetic"
    if metadata.get("provider_api_response") is True:
        return f"Alpaca · {metadata['feed'].upper()}", "alpaca"
    return "Yerel CSV", "csv"


def _style_chart(fig, yaxis_title, height):
    fig.update_layout(
        height=height, margin=dict(l=12, r=16, t=22, b=15), hovermode="x unified",
        xaxis_title=None, yaxis_title=yaxis_title,
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0, title=None),
    )
    return fig


def _render_stress(frame, metadata, count):
    try:
        stress_report = run_stress_suite(frame, metadata, visible_count=count)
        content = verify_stress_report(stress_report)
    except Exception:
        st.error("Stres raporu doğrulanamadı. Veri seçimini ve zaman sınırını kontrol edin. (BOT_STRESS_REJECTED)")
        return

    st.markdown("#### 3. Stres testi sonucu")
    source_label, source_tag = _source_label(metadata)
    st.caption(f"Veri kaynağı · {source_label}")
    status = content["status"]
    if status == "PASSED_DIAGNOSTICS":
        st.success("Teknik kontroller tamamlandı ve geçti.")
    elif status == "PARTIAL_DIAGNOSTICS":
        st.warning("Bazı teknik kontroller tamamlanamadı.")
    else:
        st.warning("Bir veya daha fazla teknik kontrol başarısız.")
    st.caption("Dört sabit koşulun varsayımsal hesap değeri karşılaştırılır. Zamanlar UTC’dir.")
    fig = go.Figure()
    for (scenario, points), color in zip(content["equity_curves"].items(), SCENARIO_COLORS):
        fig.add_trace(go.Scatter(
            x=[p["timestamp"] for p in points], y=[p["equity"] for p in points],
            name=SCENARIO_LABELS[scenario], mode="lines", line=dict(color=color, width=2),
            hovertemplate="%{y:,.2f} USD",
        ))
    st.plotly_chart(_style_chart(fig, "Hesap değeri (USD)", 310), width="stretch", key="bot_stress_curves")
    comparison = pd.DataFrame([{
        "Senaryo": SCENARIO_LABELS[row["scenario"]],
        "Net değişim (USD)": row["net_pnl"],
        "Komisyon (USD)": row["total_fees"],
        "Azami gerileme (%)": row["max_drawdown"] * 100,
        "Gerçekleşme": row["fill_count"],
    } for row in content["comparison"]])
    st.dataframe(
        comparison, hide_index=True, width="stretch",
        column_config={
            name: st.column_config.NumberColumn(format="%.2f")
            for name in ("Net değişim (USD)", "Komisyon (USD)", "Azami gerileme (%)")
        },
    )
    payload = json.dumps(stress_report, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    st.download_button("Stres raporunu indir", payload, file_name=f"tradelab-{source_tag}-execution-stress.json",
                       mime="application/json", key="bot_stress_report", on_click="ignore")
    with st.expander("Teknik kontrol kaydı"):
        st.json(content["diagnostics"])


def _render_rehearsal(frame, metadata, count, halt_at):
    try:
        summary, curve, journal = run_rehearsal(frame, metadata, visible_count=count, halt_at=halt_at)
        report = build_report(summary, curve, journal)
        verify_report(report)
    except Exception:
        st.error("Prova raporu doğrulanamadı. Veri seçimini ve prova sınırını kontrol edin. (BOT_REHEARSAL_REJECTED)")
        return

    st.markdown("#### 3. Prova sonucu")
    source_label, source_tag = _source_label(metadata)
    st.caption(f"Veri kaynağı · {source_label}")
    st.caption("Varsayımsal hesap ve pozisyon hareketleri. Zamanlar UTC’dir.")
    if not curve.empty:
        last = curve.iloc[-1]
        equity, cash, position = st.columns(3)
        equity.metric("Hesap son değeri", f"{last.equity:,.2f} USD", border=True)
        cash.metric("Kalan nakit", f"{last.cash:,.2f} USD", border=True)
        position.metric("Açık pozisyon", f"{last.position:,.0f} adet", border=True)
        balance_chart = go.Figure(go.Scatter(
            x=curve.timestamp, y=curve.equity, name="Hesap değeri", mode="lines",
            line=dict(color="#45D9AA", width=2.2), hovertemplate="%{y:,.2f} USD<extra></extra>",
        ))
        st.plotly_chart(_style_chart(balance_chart, "Hesap değeri (USD)", 275),
                        width="stretch", key="bot_equity")
        position_chart = go.Figure(go.Scatter(
            x=curve.timestamp, y=curve.position, name="Pozisyon", mode="lines",
            line=dict(color="#A6B7FF", width=2, shape="hv"), hovertemplate="%{y:,.0f} adet<extra></extra>",
        ))
        st.plotly_chart(_style_chart(position_chart, "Pozisyon (adet)", 195),
                        width="stretch", key="bot_position")
    st.download_button("Prova raporunu indir", report, file_name=f"tradelab-{source_tag}-rehearsal.json",
                       mime="application/json", key="bot_report", on_click="ignore")
    with st.expander("Olay kaydı ve teknik rapor"):
        st.caption("Rapor SHA-256 " + hashlib.sha256(report).hexdigest())
        st.dataframe(pd.DataFrame(journal), hide_index=True, width="stretch")
        st.json(summary)


def render():
    st.caption("Sinyalleri, risk kararlarını ve varsayımsal gerçekleşmeleri geçmiş mumlar üzerinde inceleyin.")
    if st.get_option("server.address") not in ("127.0.0.1", "::1"):
        st.session_state.pop(DATA_KEY, None)
        st.info("Bu yerel prova için uygulamayı --server.address 127.0.0.1 ile başlatın.")
        return
    try:
        readiness = readiness_report()
    except Exception:
        st.session_state.pop(DATA_KEY, None)
        st.error("BOT_READINESS_REJECTED · Korunan yapılandırma doğrulanamadı.")
        return
    st.badge("Çevrimdışı prova", color="blue")
    with st.expander("Araştırma sınırları ve hazırlık durumu"):
        st.caption("V4.1 zaman kapısı ve ayrılmış 108 ISE gözlemi araştırma sınırları arasında.")
        st.json(readiness)
    with st.container(border=True):
        st.markdown("#### 1. Veri kaynağını hazırla")
        source_col, symbol_col = st.columns([2, 1])
        symbol = symbol_col.selectbox("Sembol", SYMBOLS, key="bot_symbol")
        market_snapshot = get_loaded_alpaca_snapshot(symbol)
        mode = source_col.radio("Veri kaynağı", [SYNTHETIC, UPLOADED, ALPACA],
                                index=2 if market_snapshot is not None else 0, key="bot_source")
        upload = None
        if mode == UPLOADED:
            upload = st.file_uploader("15 dakikalık OHLCV dosyası (CSV, en çok 5 MB)",
                                      type=["csv"], max_upload_size=5, key="bot_upload")
            with st.expander("CSV biçimi ve tarih sınırı"):
                st.caption("Tam seans ve saat dilimi gerekli. Sütunlar timestamp, open, high, low, close ve volume. "
                           "Prova 26 Ekim 2026 öncesini ve kayıtlı araştırma aralığını kullanır.")
        elif mode == SYNTHETIC:
            st.warning("SENTETİK VERİ · Eğitim amaçlı örnek fiyatlar.")
        elif market_snapshot is None:
            st.info(f"{symbol} için Piyasa Terminali’nde Alpaca verisini yükleyin.")
        else:
            market_frame, market_meta = market_snapshot
            st.caption(f"{symbol} · Alpaca {market_meta['feed'].upper()} · "
                       f"{len(market_frame)} doğrulanmış mum · Aynı oturumdaki veri kullanılır.")
        prepare = st.button("Veriyi hazırla", key="bot_prepare", type="primary")
    if mode == ALPACA and market_snapshot is None:
        st.session_state.pop(DATA_KEY, None)
        return
    try:
        payload = upload.getvalue() if upload is not None else None
        if payload is not None and (not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES):
            raise ValueError("Invalid upload size")
        source_digest = None
        if mode == ALPACA:
            market_frame, market_meta = market_snapshot
            if (market_meta.get("synthetic") is not False or
                    market_meta.get("provider_api_response") is not True or
                    market_meta.get("symbol") != symbol):
                raise ValueError("Verified Alpaca source required")
            source_digest = _report_digest((mode, symbol), market_meta, market_frame)
        elif payload is not None:
            source_digest = hashlib.sha256(payload).hexdigest()
        identity = (mode, symbol, source_digest)
    except Exception:
        st.session_state.pop(DATA_KEY, None)
        st.error("BOT_SOURCE_REJECTED · Dosya boyutu veya yükleme okunamadı.")
        return
    if prepare:
        st.session_state.pop(DATA_KEY, None)
        try:
            if mode == SYNTHETIC:
                frame, metadata = synthetic_fixture(symbol)
            elif mode == ALPACA:
                frame, metadata = market_snapshot
            elif payload is not None:
                frame, metadata = read_uploaded_csv(payload, symbol)
            else:
                raise ValueError("Upload required")
            clean = validated_history(frame, metadata)
            st.session_state[DATA_KEY] = (identity, clean, metadata,
                                          _report_digest(identity, metadata, clean))
        except Exception:
            st.error("Veri hazırlanamadı. Mum biçimini, seans kapsamını ve tarih sınırını kontrol edin. (BOT_SOURCE_REJECTED)")
            return
    cached = st.session_state.get(DATA_KEY)
    if cached is None:
        st.caption("Prova ayarlarını açmak için veriyi hazırlayın.")
        return
    try:
        if not isinstance(cached, tuple) or len(cached) != 4:
            raise ValueError("Invalid data cache")
        if cached[0] != identity:
            st.session_state.pop(DATA_KEY, None)
            st.info("Veri seçimi değişti; yeni kaynağı açıkça kontrol edin. Önceki sonuç gösterilmez.")
            return
        _, frame, metadata, digest = cached
        if not hmac.compare_digest(digest, _report_digest(identity, metadata, frame)):
            raise ValueError("Changed source")
        frame = validated_history(frame, metadata)
        maximum = replay_limit(frame)
        if maximum < 2:
            raise ValueError("Insufficient bars")
    except Exception:
        st.session_state.pop(DATA_KEY, None)
        st.error("BOT_CACHE_REJECTED · Bellekteki veri veya kayıt değişti; kaynağı yeniden kontrol edin.")
        return
    with st.container(border=True):
        st.markdown("#### 2. Prova aralığını seç")
        count = st.slider("Provada kullanılacak mum sayısı", min_value=2, max_value=maximum, value=maximum,
                          key="bot_cursor")
        st.caption("Prova, kaydın başlangıcından itibaren bu sayıda tamamlanmış mumu kullanır.")
        with st.expander("Durdurma testi"):
            halt = st.checkbox("Durdurma kontrolünü prova et", key="bot_halt_enabled")
            halt_at = None
            if halt:
                halt_at = int(st.number_input("Durdurulacak mum (sıfırdan başlar)", min_value=0,
                                             max_value=count - 1, value=min(40, count - 1), step=1,
                                             key="bot_halt_at"))
        run_col, stress_col = st.columns(2)
        run = run_col.button("Provayı çalıştır", key="bot_run", type="primary", width="stretch")
        stress = stress_col.button("Stres testi çalıştır", key="bot_stress", width="stretch",
                                   help="Dört maliyet ve gecikme varsayımını, zaman sırasını ve durdurmayı denetler.")
    if stress:
        _render_stress(frame, metadata, count)
    elif run:
        _render_rehearsal(frame, metadata, count, halt_at)
