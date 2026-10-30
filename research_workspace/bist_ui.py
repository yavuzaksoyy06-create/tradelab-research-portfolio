"""Local, explicit BIST daily research on entitled user data; no downloads."""
import hashlib
import json

import plotly.graph_objects as go
import streamlit as st
from research_workspace.bist_research import load_csv, analyze


def render():
    st.subheader("BIST · Günlük Araştırma")
    st.info("Sabit araştırma: THYAO / GARAN / ASELS · günlük XIST · TRY · EMA20/60 long/cash. "
            "Geliştirme 2020–2022, değerlendirme 2023–2024. Ayrılmış 2025 verisi yüklenmez ve değerlendirilmez.")
    st.warning("Gerçek grafik ve backtest yalnızca kullanım hakkınız olan, doğrulamadan geçen veriden üretilir. "
               "Henüz veri yüklenmediyse sonuç yoktur. Bugünkü seçilmiş hisseler tüm BIST evrenini temsil etmez; "
               "fiyat düzeltmeleri tarihsel olarak bilinen veriyle aynı olmayabilir.")
    st.caption("25 baz puan devir maliyeti; 10/50 bp duyarlılık. Sinyal kapanıştan sonraki seans kapanışında uygulanır. "
               "Nakit getirisi sıfır; enflasyon, vergi, lot, fiyat limiti ve piyasa etkisi modellenmez. "
               "Model araması, yatırım önerisi veya emir işlevi yoktur.")
    if st.get_option("server.address") not in ("127.0.0.1", "::1"):
        st.warning("Özel veri yükleme kapalı. Yerel uygulamayı --server.address 127.0.0.1 ile başlatın.")
        return
    with st.form("bist_run_form"):
        uploaded = st.file_uploader("Yetkili günlük OHLCV CSV · en çok 2 MB", type=["csv"],
                                    max_upload_size=2, key="bist_csv")
        symbol = st.selectbox("BIST hissesi", ["THYAO", "GARAN", "ASELS"], key="bist_symbol")
        provider = st.text_input("Veri sağlayıcısı", max_chars=200, key="bist_provider")
        url = st.text_input("Kaynak HTTPS referansı · anahtar veya sorgu parametresi olmadan",
                            max_chars=2048, key="bist_source_url")
        license_ref = st.text_input("Lisans / kullanım hakkı referansı · gizli bilgi girmeyin",
                                    max_chars=200, key="bist_license_reference")
        rights = st.checkbox("Bu veriyi yerel araştırmada kullanma hakkım var; adjusted_close sağlayıcı tarafından düzeltilmiştir.",
                             key="bist_usage_rights")
        submitted = st.form_submit_button("Veriyi doğrula ve sabit backtesti çalıştır", key="bist_run")
    st.caption("Sütunlar: date,open,high,low,close,volume,adjusted_close. 2020–2024 XIST seansları eksiksiz olmalı. "
               "Veri veya geçmiş performans uydurulmaz; rapor bir sonraki ekran çalıştırmasında temizlenir.")
    if not submitted:
        return
    if uploaded is None or not rights:
        st.error("DATA_AND_RIGHTS_REQUIRED · Yetkili CSV ve kullanım hakkı beyanı gerekli.")
        return
    try:
        payload = uploaded.getvalue()
        manifest = {"symbol": symbol, "provider": provider, "source_url": url,
                    "license_reference": license_ref, "usage_rights": "user_confirmed_local_research",
                    "source_independently_verified": False, "exchange": "XIST", "currency": "TRY",
                    "timeframe": "1d", "adjustment": "provider_adjusted_close",
                    "csv_sha256": hashlib.sha256(payload).hexdigest()}
        frame, meta = load_csv(payload, manifest)
        summary, curve = analyze(frame, meta)
    except Exception:
        st.error("BIST_REJECTED · Kaynak kaydı, veri kapsamı, fiyat yapısı, hash ve ayrılmış tarih sınırlarını kontrol edin.")
        return
    st.success("Veri yapısı ve sabit protokol doğrulandı. Kaynak bağımsız olarak doğrulanmış değildir.")
    st.subheader("Gerçek geçmiş veri · ham günlük OHLC")
    observed = frame.loc[frame.date >= "2023-01-01"]
    fig = go.Figure(go.Candlestick(x=observed.date, open=observed.open, high=observed.high,
                                 low=observed.low, close=observed.close, name=symbol))
    fig.update_layout(xaxis_rangeslider_visible=False, yaxis_title="Ham fiyat · TRY")
    st.plotly_chart(fig, key="bist_ohlc", width="stretch")
    fig = go.Figure()
    for column in ("adjusted_close", "ema20", "ema60"):
        fig.add_trace(go.Scatter(x=curve.date, y=curve[column], name=column))
    fig.update_layout(yaxis_title="Sağlayıcı düzeltmeli fiyat · TRY")
    st.plotly_chart(fig, key="bist_features", width="stretch")
    fig = go.Figure()
    for column in ("net_equity", "buyhold_equity"):
        fig.add_trace(go.Scatter(x=curve.date, y=curve[column], name=column))
    fig.update_layout(yaxis_title="Başlangıç 1 · maliyet sonrası endeks")
    st.plotly_chart(fig, key="bist_backtest", width="stretch")
    st.subheader("İstatistiksel tanılama · 2023–2024")
    st.json(summary)
    st.download_button("Fiyatsız kaynak manifestini indir", json.dumps(meta, ensure_ascii=False, indent=2),
                       file_name="bist_manifest.json", mime="application/json", key="bist_manifest")
