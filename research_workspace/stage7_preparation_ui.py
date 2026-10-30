"""Explicit offline planning and local read-only review; no model execution."""
from datetime import date
from pathlib import Path
import os

import streamlit as st
from research_workspace.stage7_history import collection_plan
from research_workspace.stage7_review import review_snapshot


def _local_directory(value):
    # Reject remote/relative paths before any filesystem inspection.
    if not value or value.startswith(("\\\\", "//")):
        return False
    folder = Path(value)
    if not folder.is_absolute():
        return False
    if os.name == "nt":
        import ctypes
        # Mapped network drives are not local snapshot destinations.
        if ctypes.windll.kernel32.GetDriveTypeW(str(folder.anchor)) not in (2, 3, 6):
            return False
    # Do not follow a symlink/junction to a different location or network share.
    components = [*reversed((folder, *folder.parents)),
                  folder / "manifest.json", folder / "bars.csv"]
    for component in components:
        if component.is_symlink() or component.is_junction():
            return False
    return True


def render_preparation():
    st.subheader("Stage 7 · Veri Hazırlığı")
    st.caption("Plan takvimi hesaplar; review mevcut kaydın yapısını ve hash değerlerini inceler. "
               "Bu alan veri indirmez, model çalıştırmaz ve emir göndermez. "
               "Rapor yalnızca gönderilen formun bu çalıştırmasına aittir; ekran yenilenince temizlenir.")
    with st.expander("1 · Veri toplama planı / plan"):
        with st.form("stage7_plan_form"):
            symbol = st.selectbox("Plan sembolü", ["SPY", "MSFT", "QQQ"], key="stage7_plan_symbol")
            feed = st.selectbox("Plan veri akışı", ["sip", "iex"], key="stage7_plan_feed")
            start = st.date_input("Plan başlangıç günü", date(2025, 1, 2),
                                  min_value=date(2000, 1, 1), max_value=date(2026, 10, 25),
                                  key="stage7_plan_start")
            end = st.date_input("Plan bitiş günü · dahil", date(2025, 6, 25),
                                min_value=date(2000, 1, 1), max_value=date(2026, 10, 25),
                                key="stage7_plan_end")
            planned = st.form_submit_button("Planı hesapla", key="stage7_plan_submit")
        st.caption("XNYS · 15 dakika · en çok 200 takvim günü / 120 tam seans. "
                   "26 Ekim 2026 ve sonrası kapalıdır. Feed aboneliği ve veri erişimi ayrıca doğrulanmalıdır.")
        if planned:
            try:
                report = collection_plan(symbol, start.isoformat(), end.isoformat(), feed=feed)
            except Exception:
                st.error("PLAN_REJECTED · Tarih sırasını, süreyi ve tam seans sınırlarını kontrol edin.")
            else:
                st.success("Takvim planı hazır. Veri erişimi veya abonelik doğrulanmış değildir.")
                st.json(report)

    with st.expander("2 · Yerel veri kaydını incele / review"):
        local = st.get_option("server.address") in ("127.0.0.1", "::1")
        with st.form("stage7_review_form"):
            if local:
                directory = st.text_input("Mevcut özel veri klasörü · mutlak yerel yol",
                                          key="stage7_review_path")
            else:
                directory = ""
                st.info("Yerel dosya incelemesi kapalı. Uygulamayı --server.address 127.0.0.1 ile başlatın.")
            submitted = st.form_submit_button("Kaydı salt okunur incele", disabled=not local,
                                              key="stage7_review_submit")
        st.caption("manifest.json ve bars.csv dosyaları incelenir; fiyat veya sonuç satırları gösterilmez. "
                   "Yapısal doğrulama, bağımsız kaynak doğrulaması veya model başarı kanıtı değildir.")
        if submitted and local:
            try:
                if not _local_directory(directory):
                    st.error("LOCAL_PATH_REQUIRED · Bağlantı veya ağ paylaşımı içermeyen mutlak yerel klasör seçin.")
                    return
                report = review_snapshot(directory)
            except Exception:
                st.error("REVIEW_FAILED · Kayıt incelenemedi; dosyalar ve erişim izinlerini kontrol edin.")
                return
            if report["status"] == "rejected":
                st.error("Kayıt reddedildi. Hash, kapsam, kaynak ve tarih sınırlarını kontrol edin.")
            elif not report["diagnostic_eligible"]:
                st.warning("Yapı doğrulandı; kayıtlı ayrım veya yeterli seans bulunmadığından tarihsel tanılamaya uygun değil.")
            else:
                st.success("Yapı ve kayıtlı holdout ayrımı doğrulandı. Model değerlendirmesi ayrı bir işlemdir.")
            st.json(report)
