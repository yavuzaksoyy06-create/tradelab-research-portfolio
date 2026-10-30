"""Historical Istanbul index-return predictions and research signals, no orders."""
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from research_workspace.ise_ml import evaluate, VALIDATION_START, HOLDOUT_START
from research_workspace.ise_source import read_snapshot
from research_workspace.stage7_preparation_ui import _local_directory

SNAPSHOT_KEY = "ise_loaded_snapshot"


def render():
    st.subheader("İstanbul Endeksi · Makine Öğrenmesi")
    st.info("Gerçek tarihsel endeks getirileri · UCI 247 · Akbilgic (2013) · CC BY 4.0. "
            "Bu kaynak THYAO/GARAN/ASELS fiyatları, OHLC mumları veya güncel piyasa verisi değildir.")
    st.caption("Sabit Ridge modeli: 22 gecikmeli özellik, yalnızca eğitimden standardizasyon, "
               "20 gözlemde bir genişleyen eğitim. 321 geliştirme / 107 doğrulama / 108 ayrılmış gözlem. "
               "Son 108 gözlem grafik, model ve skorlara alınmaz.")
    st.warning("LONG / WATCH / CASH tarihsel araştırma etiketleridir; emir veya kalibre olasılık değildir. "
               "0.005 eşiği kaynak biriminde sabittir. Getirinin basit/log tanımı doğrulanmadığı için P&L hesaplanmaz. "
               "Kaynak yabancı endekslerde önceki değerle doldurma uygulamıştır; yayın zamanı bağımsız doğrulanmamıştır.")
    if st.get_option("server.address") not in ("127.0.0.1", "::1"):
        st.session_state.pop(SNAPSHOT_KEY, None)
        st.info("Yerel kayıt yükleme kapalı. Uygulamayı --server.address 127.0.0.1 ile başlatın.")
        return
    with st.form("ise_load_form"):
        path = st.text_input("Hash doğrulamalı UCI kayıt klasörü · mutlak yerel yol",
                             value=os.environ.get("TRADELAB_ISE_SNAPSHOT", ""), key="ise_snapshot_path")
        submitted = st.form_submit_button("Kaydı doğrula ve yükle", key="ise_load")
    if submitted:
        st.session_state.pop(SNAPSHOT_KEY, None)
        try:
            if not _local_directory(path):
                raise ValueError("Local path required")
            frame, meta = read_snapshot(path)
            st.session_state[SNAPSHOT_KEY] = (path, frame, meta)
        except Exception:
            st.error("ISE_LOAD_REJECTED · Yerel yol, kaynak hash'i ve veri kaydını kontrol edin.")
            return
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    if snapshot is None or snapshot[0] != path:
        st.info("Doğrulanmış veri yüklenmedi. Grafik veya sonuç uydurulmaz; otomatik indirme yapılmaz.")
        return
    _, frame, meta = snapshot
    st.caption("Yüklenen kayıt: " + meta["registration_sha256"] +
               " · Bellekteki doğrulanmış kopya kullanılır; dosyayı yeniden incelemek için tekrar yükleyin.")
    visible_count = st.slider("Tarihsel replay · görünür gözlem", min_value=VALIDATION_START,
                              max_value=HOLDOUT_START, value=HOLDOUT_START, step=1, key="ise_cursor")
    st.caption("Sonuçlar yalnızca aşağıdaki düğmeyle hesaplanır ve başka bir ekran çalıştırmasında temizlenir. "
               "Grafikte gösterilen hedef tarihinin özellikleri en az iki gözlem öncesinde biter.")
    if not st.button("Görünür dönem için modeli ve sinyalleri değerlendir", key="ise_evaluate"):
        return
    try:
        summary, curve = evaluate(frame, meta, visible_count=visible_count)
    except Exception:
        st.error("ISE_EVALUATION_REJECTED · Kayıt bütünlüğü veya hesaplama doğrulanamadı.")
        return
    st.json(summary)
    if curve.empty:
        st.info("Henüz görünür doğrulama gözlemi yok.")
        return
    fig = go.Figure()
    for column, label in (("actual_return", "Gerçekleşen endeks getirisi"), ("prediction", "Önceden üretilen tahmin")):
        fig.add_trace(go.Scatter(x=curve.date, y=curve[column], name=label, mode="lines"))
    for name, color, shape in (("LONG", "#38bd91", "triangle-up"), ("WATCH", "#e2ac48", "circle"),
                               ("CASH", "#7b9fc9", "square")):
        rows = curve.loc[curve.signal == name]
        fig.add_trace(go.Scatter(x=rows.date, y=rows.prediction, name=name, mode="markers",
                                 marker=dict(color=color, symbol=shape, size=7)))
    fig.update_layout(yaxis_title="Kaynağın getiri birimi", xaxis_title="Tarihsel hedef günü")
    st.plotly_chart(fig, key="ise_predictions", width="stretch")
    errors = curve.actual_return - curve.prediction
    fig = go.Figure(go.Bar(x=curve.date, y=errors, name="Gerçekleşen − tahmin"))
    fig.update_layout(yaxis_title="Tahmin hatası · kaynak birimi")
    st.plotly_chart(fig, key="ise_errors", width="stretch")
    latest = curve.iloc[-1]
    st.subheader("Son görünür tarihsel sinyalin açıklaması")
    st.write(f"{latest.date.date().isoformat()}: {latest.signal}. Tahmin {latest.prediction:.6f} kaynak birimi. "
             f"Özellik sınırı {latest.feature_cutoff}; eğitim sınırı {latest.training_end}.")
    top = latest.top_contributions
    fig = go.Figure(go.Bar(x=[v["contribution"] for v in top], y=[v["feature"] for v in top], orientation="h"))
    fig.update_layout(xaxis_title="İmzalı tahmin katkısı · kaynak birimi")
    st.plotly_chart(fig, key="ise_contributions", width="stretch")
    st.caption("Yalnızca en büyük üç doğrusal katkı gösterilir; bunlar toplam açıklama veya ekonomik nedensellik değildir. "
               "Model doğruluğu ve referans modellere üstünlük ayrı ölçülür; zayıf sonuçlar gizlenmez.")
    st.dataframe(curve[["date", "signal", "prediction", "actual_return", "training_end", "feature_cutoff"]],
                 hide_index=True, width="stretch")
