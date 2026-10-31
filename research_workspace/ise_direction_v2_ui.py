"""Explicit, identity-bound display of the separately registered direction experiment."""
import os
import hmac
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from research_workspace.ise_source import read_snapshot
from research_workspace.ise_ml import validate_registration
from research_workspace.ise_ml_ui import _report_digest
from research_workspace.ise_direction_v2 import evaluate_v2, experiment_specification, experiment_sha256
from research_workspace.stage7_preparation_ui import _local_directory

SNAPSHOT_KEY, REPORT_KEY = "ise_v2_loaded_snapshot", "ise_v2_cached_report"


def _clear():
    st.session_state.pop(SNAPSHOT_KEY, None)
    st.session_state.pop(REPORT_KEY, None)


def render():
    st.subheader("İstanbul ML v2 · Kayıtlı Yön Deneyi")
    st.info("Beş geçmiş özellik · düzenlileştirilmiş lojistik model · eğitim içinde zaman sıralı seçim. "
            "Eski model ve son 108 ayrılmış gözlem korunur.")
    st.warning("Bu doğrulama dönemi daha önce incelendi. Sonuç keşif amaçlıdır; bağımsız yeni test değildir. "
               "Model skorları kalibre değildir. Araştırma sınıfları emir veya kâr tahmini değildir.")
    try:
        spec = experiment_specification()
    except Exception:
        _clear()
        st.error("V2_SPEC_REJECTED · Kayıtlı deney tanımı değişmiş veya doğrulanamamış.")
        return
    if st.get_option("server.address") not in ("127.0.0.1", "::1"):
        _clear()
        st.info("Özel veri yüklemek için uygulamayı --server.address 127.0.0.1 ile başlatın.")
        return
    with st.form("ise_v2_load_form"):
        path = st.text_input("Mevcut hash doğrulamalı UCI klasörü",
                             value=os.environ.get("TRADELAB_ISE_SNAPSHOT", ""), key="ise_v2_path")
        submitted = st.form_submit_button("Kaydı v2 için doğrula ve yükle", key="ise_v2_load")
    if submitted:
        _clear()
        try:
            if not _local_directory(path):
                raise ValueError("Local path required")
            frame, meta = read_snapshot(path)
            st.session_state[SNAPSHOT_KEY] = (path, frame, meta)
        except Exception:
            st.error("V2_LOAD_REJECTED · Yerel yol, kaynak ve kayıt hash'lerini kontrol edin.")
            return
    snapshot = st.session_state.get(SNAPSHOT_KEY)
    if snapshot is None or snapshot[0] != path:
        st.session_state.pop(REPORT_KEY, None)
        st.info("Veri yüklenmedi; model veya sonuç üretilmedi. Otomatik indirme yapılmaz.")
        return
    _, frame, meta = snapshot
    try:
        validate_registration(frame, meta)
        experiment = experiment_sha256(meta)
    except Exception:
        _clear()
        st.error("V2_CACHE_REJECTED · Veri veya deney kimliği değişti; kaydı yeniden yükleyin.")
        return
    count = st.slider("V2 tarihsel replay · görünür gözlem", min_value=spec["validation_start"],
                      max_value=spec["holdout_start"], value=spec["holdout_start"], key="ise_v2_cursor")
    identity = (experiment, meta["validation_binding_sha256"], count)
    cached = st.session_state.get(REPORT_KEY)
    if cached is not None:
        try:
            if not isinstance(cached, tuple) or len(cached) != 4:
                raise ValueError("Invalid report")
            if cached[0] != identity:
                st.session_state.pop(REPORT_KEY, None)
                cached = None
            elif not hmac.compare_digest(cached[3], _report_digest(identity, cached[1], cached[2])):
                raise ValueError("Report changed")
        except Exception:
            _clear()
            st.error("V2_CACHE_REJECTED · Bellekteki rapor değişti; kaydı yeniden yükleyin.")
            return
    st.caption("Seçim yalnızca geçmiş eğitim pencerelerindedir. Güncel veya gelecekteki dış pencere etiketleri "
               "seçime girmez; sonraki pencereler önceki tamamlanmış gözlemleri kullanabilir.")
    if st.button("Kayıtlı v2 deneyini görünür dönem için çalıştır", key="ise_v2_evaluate"):
        st.session_state.pop(REPORT_KEY, None)
        try:
            summary, curve = evaluate_v2(frame, meta, visible_count=count)
            cached = (identity, summary, curve, _report_digest(identity, summary, curve))
            st.session_state[REPORT_KEY] = cached
        except Exception:
            st.error("V2_EVALUATION_REJECTED · Deney tanımı, zaman sınırları veya sayısal yakınsama doğrulanamadı.")
            return
    if cached is None:
        return
    _, summary, curve, _ = cached
    st.caption("Deney kimliği: " + summary["experiment_sha256"])
    if curve.empty:
        st.info("Görünür doğrulama gözlemi yok.")
        return
    st.subheader("Kayıtlı referans karşılaştırması")
    metrics = [{"model": name, **{k: values.get(k) for k in
               ("brier", "logloss", "balanced_accuracy", "directional_accuracy", "positive_prediction_share", "ece_5bins")}}
               for name, values in summary["metrics"].items()]
    st.dataframe(pd.DataFrame(metrics), hide_index=True, width="stretch")
    interval = summary["brier_improvement_95_block_interval"]
    delta = summary["mean_brier_improvement_vs_train_prior"]
    st.write(f"Eğitim frekansına göre Brier iyileşmesi: {delta:.6f}. Pozitif değer daha iyidir.")
    if interval is None:
        st.info("En az 20 görünür sonuç olmadan blok belirsizlik aralığı hesaplanmaz.")
    elif interval[0] <= 0:
        st.warning("Birincil ölçütte güvenilir üstünlük gösterilmedi; fark aralığının alt sınırı pozitif değil.")
    else:
        st.info("Bu tekrar incelenen örneklemde aralık pozitif; bu durum bağımsız doğrulama veya işlem onayı değildir.")
    st.caption("v1 Ridge yalnızca yön referansıdır; regresyon tahmini olasılığa çevrilmez. "
               "Kesin 0/1 referansların log-loss değeri kayıtlı sayısal kırpmayla hesaplanır.")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=curve.date, y=curve.score, name="Kalibre edilmemiş lojistik skor"))
    fig.add_trace(go.Scatter(x=curve.date, y=curve.threshold, name="Yalnızca eğitimden seçilen eşik", line=dict(dash="dash")))
    fig.add_trace(go.Scatter(x=curve.date, y=curve.actual_up, name="Gerçekleşen yön (1/0)", mode="markers", marker=dict(size=5)))
    fig.update_layout(yaxis_title="Araştırma skoru / yön sınıfı", yaxis_range=[-.05, 1.05])
    st.plotly_chart(fig, key="ise_v2_scores", width="stretch")
    folds = pd.DataFrame(summary["fold_fit_diagnostics"])
    fig = go.Figure()
    for col in ("train_brier", "selected_inner_brier", "outer_brier"):
        fig.add_trace(go.Scatter(x=folds.fold + 1, y=folds[col], name=col, mode="lines+markers"))
    fig.update_layout(xaxis_title="Sabit dış pencere", yaxis_title="Brier hatası")
    st.plotly_chart(fig, key="ise_v2_fit_gap", width="stretch")
    choices = curve.origin_index.tolist()
    selected = st.selectbox("V2 tarihsel sınıf inceleyicisi", choices, index=len(choices)-1,
                            format_func=lambda i: curve.loc[curve.origin_index == i, "date"].iloc[0].date().isoformat(),
                            key="ise_v2_inspector")
    row = curve.loc[curve.origin_index == selected].iloc[0]
    st.write(f"{row.date.date().isoformat()}: {row.research_label}; skor {row.score:.4f}, eşik {row.threshold:.2f}. "
             f"Eğitim sonu {row.training_end}, özellik sonu {row.feature_cutoff}.")
    contributions = row.logit_contributions
    fig = go.Figure(go.Bar(x=[v["contribution"] for v in contributions], y=[v["feature"] for v in contributions], orientation="h"))
    fig.update_layout(xaxis_title="Logit katkısı · olasılık puanı değildir")
    st.plotly_chart(fig, key="ise_v2_contributions", width="stretch")
    st.caption("Katkılar doğrusal logit hesabıdır; ekonomik neden veya kalibre olasılık açıklaması değildir.")
    st.dataframe(folds, hide_index=True, width="stretch")
    with st.expander("İç seçim ve kayıt kanıtları"):
        st.json(summary)
