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
from research_workspace.ise_ml_ui import _report_digest
from research_workspace.stage7_events import replay_limit, validated_history
from research_workspace.bot_stress import run_stress_suite, verify_stress_report

DATA_KEY = "bot_rehearsal_loaded_data"
SYNTHETIC = "Sentetik eğitim örneği"
UPLOADED = "Yerel OHLCV CSV"


def render():
    st.subheader("Bot Provası · Çevrimdışı İşlem Akışı")
    st.info("Tamamlanmış mum → araştırma sinyali → risk kontrolü → varsayımsal gerçekleşme → denetim kaydı. "
            "Bu sayfada broker bağlantısı veya gerçek / paper emir gönderme işlevi yoktur.")
    st.warning("V2 modelinin güvenilir üstünlüğü gösterilmedi; ML skorları işlem talimatına çevrilmez. "
               "V4.1, zaman kapısı ve ayrılmış 108 ISE gözlemi korunur.")
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
    with st.expander("Gerçek işlem öncesi eksik kanıtlar ve korunan sınırlar"):
        st.json(readiness)
    mode = st.radio("Veri kaynağı", [SYNTHETIC, UPLOADED], key="bot_source")
    symbol = st.selectbox("Sembol", SYMBOLS, key="bot_symbol")
    upload = None
    if mode == UPLOADED:
        upload = st.file_uploader("Tam seanslı 15 dakika OHLCV CSV · en çok 5 MB", type=["csv"],
                                  max_upload_size=5, key="bot_upload")
        st.caption("timestamp,open,high,low,close,volume · saat dilimi zorunludur. "
                   "Yükleme kaynak doğruluğunu veya kullanım hakkını bağımsız olarak doğrulamaz. "
                   "26 Ekim 2026 ve sonrası kapalıdır; kayıtlı araştırma holdout sınırı uygulanır.")
    else:
        st.warning("SENTETİK VERİ · Gerçek piyasa fiyatı, backtest başarı kanıtı veya beklenen kazanç değildir.")
    try:
        payload = upload.getvalue() if upload is not None else None
        if payload is not None and (not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES):
            raise ValueError("Invalid upload size")
        identity = (mode, symbol, hashlib.sha256(payload).hexdigest() if payload is not None else None)
    except Exception:
        st.session_state.pop(DATA_KEY, None)
        st.error("BOT_SOURCE_REJECTED · Dosya boyutu veya yükleme okunamadı.")
        return
    if st.button("1 · Veriyi kontrol et", key="bot_prepare"):
        st.session_state.pop(DATA_KEY, None)
        try:
            if mode == SYNTHETIC:
                frame, metadata = synthetic_fixture(symbol)
            elif payload is not None:
                frame, metadata = read_uploaded_csv(payload, symbol)
            else:
                raise ValueError("Upload required")
            clean = validated_history(frame, metadata)
            st.session_state[DATA_KEY] = (identity, clean, metadata,
                                          _report_digest(identity, metadata, clean))
        except Exception:
            st.error("BOT_SOURCE_REJECTED · OHLCV yapısı, tam seans kapsamı ve kapalı tarih sınırını kontrol edin.")
            return
    cached = st.session_state.get(DATA_KEY)
    if cached is None:
        st.caption("Veri hazırlanmadı. Prova ve otomatik indirme çalıştırılmadı.")
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
    count = st.slider("Görünür tamamlanmış mum", min_value=2, max_value=maximum, value=maximum,
                      key="bot_cursor")
    halt = st.checkbox("Durdurma kontrolünü prova et", key="bot_halt_enabled")
    halt_at = None
    if halt:
        halt_at = int(st.number_input("Durdurulacak mum indeksi · sıfırdan başlar", min_value=0,
                                     max_value=count - 1, value=min(40, count - 1), step=1,
                                     key="bot_halt_at"))
    st.caption("Tam veri kaydının araştırma sınırı korunur. Prova yalnızca seçilen görünür öneki kullanır. "
               "Sonuçlar bir sonraki etkileşimde temizlenir; yeniden çalıştırma açık bir eylemdir.")
    run = st.button("2 · Çevrimdışı provayı çalıştır", key="bot_run")
    stress = st.button("3 · Maliyet, gecikme ve nedensellik denetimini çalıştır", key="bot_stress")
    st.caption("Stres denetimi aynı sabit kuralı dört maliyet/gecikme varsayımında inceler. "
               "Geçmiş kararları gelecek mumlarla değiştirme ve durdurma sonrası giriş kontrollerini uygular. "
               "En iyi senaryo seçilmez; strateji onayı verilmez.")
    if stress:
        try:
            stress_report = run_stress_suite(frame, metadata, visible_count=count)
            content = verify_stress_report(stress_report)
        except Exception:
            st.error("BOT_STRESS_REJECTED · Veri, zaman sınırları veya denetim bütünlüğü doğrulanamadı.")
            return
        st.subheader("Sabit senaryolar · yürütme stres denetimi")
        if content["status"] == "PASSED_DIAGNOSTICS":
            st.success("Uygulanan teknik denetimler geçti. Bu sonuç strateji başarısı veya işlem izni değildir.")
        else:
            st.warning("Denetim sonucu: " + content["status"] + ". Eksik veya başarısız kontroller geçilmiş sayılmaz.")
        st.dataframe(pd.DataFrame(content["comparison"]), hide_index=True, width="stretch")
        fig = go.Figure()
        for scenario, points in content["equity_curves"].items():
            fig.add_trace(go.Scatter(x=[p["timestamp"] for p in points], y=[p["equity"] for p in points], name=scenario))
        fig.update_layout(xaxis_title="Tamamlanmış mum · UTC", yaxis_title="Varsayımsal hesap değeri")
        st.plotly_chart(fig, width="stretch", key="bot_stress_curves")
        with st.expander("Nedensellik, kaynak hataları, hesap kurtarma ve durdurma kanıtları", expanded=True):
            st.json(content["diagnostics"])
        payload = json.dumps(stress_report, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
        st.download_button("Hash doğrulamalı stres raporunu indir", payload,
                           file_name="tradelab-execution-stress.json", mime="application/json",
                           key="bot_stress_report", on_click="ignore")
        return
    if not run:
        return
    try:
        summary, curve, journal = run_rehearsal(frame, metadata, visible_count=count, halt_at=halt_at)
        report = build_report(summary, curve, journal)
        verify_report(report)
    except Exception:
        st.error("BOT_REHEARSAL_REJECTED · Veri, zaman sınırı, risk kontrolü veya rapor bütünlüğü doğrulanamadı.")
        return
    st.success("Çevrimdışı prova tamamlandı. Broker veya hesap emri gönderilmedi.")
    st.caption("Varsayımsal nakit ve pozisyon muhasebesi; gerçek işlem performansı değildir.")
    if not curve.empty:
        fig = go.Figure(go.Scatter(x=curve.timestamp, y=curve.equity, name="Varsayımsal toplam değer"))
        fig.update_layout(xaxis_title="Tamamlanmış mum · UTC", yaxis_title="Simüle değer")
        st.plotly_chart(fig, width="stretch", key="bot_equity")
        fig = go.Figure(go.Scatter(x=curve.timestamp, y=curve.position, name="Varsayımsal adet", mode="lines"))
        fig.update_layout(xaxis_title="Tamamlanmış mum · UTC", yaxis_title="Simüle pozisyon adedi")
        st.plotly_chart(fig, width="stretch", key="bot_position")
    st.subheader("Risk kararları ve olay kaydı")
    st.dataframe(pd.DataFrame(journal), hide_index=True, width="stretch")
    with st.expander("Prova özeti"):
        st.json(summary)
    st.caption("İndirilebilir rapor SHA-256: " + hashlib.sha256(report).hexdigest())
    st.download_button("Hash doğrulamalı prova raporunu indir", report,
                       file_name="tradelab-offline-rehearsal.json", mime="application/json",
                       key="bot_report", on_click="ignore")
