"""Stage 7 presentation, computed solely from the selected visible replay prefix."""
import json
import pandas as pd
import streamlit as st
from research_workspace.stage7_events import event_dataset, safe_summary, INSUFFICIENT
from research_workspace.stage7_scenarios import scenarios
from research_workspace.stage7_validation import evaluate_history


def render_research(frame, metadata, visible_count):
    st.subheader("Piyasa Durumu")
    try:
        dataset = event_dataset(frame, metadata, visible_count=visible_count)
    except ValueError:
        st.warning("Stage 7 verisi uygun değil: tam seans, kaynak ve 26 Ekim 2026 öncesi tarih sınırları gerekli.")
        return
    records = dataset["records"]
    if not records:
        st.info("EMA ve hacim için en az 21 tamamlanmış mum gerekli.")
        return
    report = scenarios(records[-1]["features"])
    st.write(report["observed_fact"])
    st.subheader("Olası Senaryolar")
    for item in report["scenarios"]:
        st.markdown("**" + item["name"] + "**")
        st.write("Koşul: " + item["condition"])
        st.write("Geçersizlik: " + item["invalidation"])
        st.caption(item["evidence"] + " Ufuk: 4 veya 16 tamamlanan işlem mumu.")
    st.caption(report["uncertainty"])
    st.subheader("Tarihsel Kanıt")
    st.info("Otomatik tarihsel model değerlendirmesi yapılmaz. Gösterilen kayıt sayıları model başarı ölçüsü değildir.")
    summary = safe_summary(dataset)
    st.write({"Görünen kayıt": summary["records"], "Ufku tamamlanan": summary["completed_outcomes"],
              "Sentetik örnek": summary["synthetic"]})
    if st.button("Görünen tam seanslarla tarihsel tanılamayı çalıştır", key="stage7_evaluate"):
        visible = frame.iloc[:visible_count]
        complete = visible.loc[visible.session_close <= visible.bar_end.iloc[-1]]
        if complete.empty:
            st.info("Henüz tamamlanmış seans yok.")
        else:
            diagnostic = evaluate_history(frame, metadata, visible_count=visible_count)
            st.json(diagnostic)
            st.caption("Bu tanılama gerçek veri kaynağının bağımsız doğrulanması veya olasılık yayın onayı değildir. "
                       "Test dönemi tam veri kümesine sabittir; replay ilerleyince sınırı kaymaz.")
    st.subheader("Tahmin ve Gerçekleşen Sonuç")
    # Never include hidden suffix outcomes. This table contains conditional observations,
    # not a retroactively fitted numerical prediction.
    rows = []
    for row in records[-24:]:
        f, out = row["features"], row["outcome"]
        then = scenarios(f)
        rows.append({"Gözlem zamanı": f["observed_at"], "Ufuk": row["horizon"],
                     "O zamanki koşul": f["event"]["type"],
                     "O zamanki yükseliş koşulu": then["scenarios"][0]["condition"],
                     "O zamanki düşüş koşulu": then["scenarios"][1]["condition"],
                     "Olasılık": "Doğrulanmadı",
                     "Sonuç zamanı": out["available_at"] or "Henüz görünür değil",
                     "Gerçekleşen getiri": out["return"],
                     "S/R sonucu": out["sr_outcome"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.subheader("Model Güvenilirliği")
    st.warning(INSUFFICIENT)
    st.caption("Kalibrasyon ve örneklem dışı üstünlük doğrulanmadı. Sayısal olasılıklar kapalı; "
               "son 20 seanslık tarihsel holdout değerlendirme koduna alınmaz. "
               "Sentetik testler yalnızca yazılım doğruluğunu sınar.")
    st.subheader("Araştırma Kaydı")
    st.caption("Varsayılan dışa aktarım yalnızca protokol, hash ve sayaçları içerir; fiyat/getiri satırı içermez.")
    st.download_button("Stage 7 araştırma özeti JSON", json.dumps(summary, ensure_ascii=False, indent=2),
                       file_name="stage7_research_summary.json", mime="application/json", key="stage7_json")
    st.download_button("Stage 7 araştırma özeti CSV", pd.DataFrame([summary]).to_csv(index=False),
                       file_name="stage7_research_summary.csv", mime="text/csv", key="stage7_csv")
