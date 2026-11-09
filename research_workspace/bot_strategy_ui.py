"""Local strategy plan freezing, synthetic preview and draft export."""

import json

import pandas as pd
import streamlit as st

from research_workspace.bot_rehearsal import build_report, run_rehearsal, verify_report
from research_workspace.equity_data import synthetic_fixture


PLAN_KEY = "bot_strategy_frozen_plan"
EDIT_KEY = "bot_strategy_editor_seed"
RULE_LABELS = {"ema_trend": "EMA trendi", "channel_breakout": "Kanal kırılımı"}
FIELDS = (
    ("fast", "Kısa pencere · mum", 9),
    ("slow", "Uzun pencere · mum", 21),
    ("max_position_bps", "Azami pozisyon · baz puan", 1000),
    ("planned_risk_bps", "Planlanan azami risk · baz puan", 50),
    ("stop_bps", "Zarar durdurma mesafesi · baz puan", 200),
    ("target_bps", "Hedef mesafesi · baz puan", 400),
    ("session_loss_bps", "Seans zarar sınırı · baz puan", 200),
    ("max_holding_bars", "Azami pozisyon süresi · mum", 4),
)


def _editor(strategy):
    seed = {}
    previous = st.session_state.get(EDIT_KEY)
    if previous is not None:
        try:
            seed = strategy.decode_strategy_plan(previous)["content"]
        except (ValueError, TypeError):
            st.session_state.pop(EDIT_KEY, None)

    with st.form("bot_plan_editor"):
        name = st.text_input("Plan adı", value=seed.get("name", "EMA rehearsal"),
                             max_chars=64, key="bot_plan_name")
        symbol = st.selectbox("Sembol", strategy.STRATEGY_SYMBOLS,
                              index=strategy.STRATEGY_SYMBOLS.index(seed.get("symbol", "SPY")),
                              key="bot_plan_symbol")
        rule = st.selectbox("Strateji kuralı", strategy.STRATEGY_RULES,
                            index=strategy.STRATEGY_RULES.index(seed.get("rule", "ema_trend")),
                            format_func=RULE_LABELS.__getitem__, key="bot_plan_rule")
        st.caption("Kısa ve uzun pencere EMA dönemlerini belirler. Kanal kuralında kısa pencere "
                   "çıkışı, uzun pencere girişi izler. Kanal sınırları önceki kapanışlardan hesaplanır.")
        columns = st.columns(2)
        settings = {}
        for i, (field, label, default) in enumerate(FIELDS):
            minimum, maximum = strategy.STRATEGY_BOUNDS[field]
            settings[field] = columns[i % 2].number_input(
                label, min_value=minimum, max_value=maximum, value=seed.get(field, default),
                step=1, key="bot_plan_" + field,
            )
        st.caption("100 baz puan %1’e eşittir. Plan adında Latin harfleri, rakamlar, boşluk ve ._- kullanılabilir.")
        submitted = st.form_submit_button("Planı doğrula ve sabitle", key="bot_plan_freeze")
    if not submitted:
        return
    try:
        envelope = strategy.make_strategy_plan(name, symbol, rule=rule, **settings)
        payload = strategy.encode_strategy_plan(envelope)
    except (ValueError, TypeError):
        st.error("BOT_PLAN_REJECTED · Plan adını, kısa/uzun pencere sırasını ve risk sınırlarını kontrol edin.")
        return
    st.session_state[PLAN_KEY] = payload
    st.session_state.pop(EDIT_KEY, None)
    st.rerun()


def _preview(envelope):
    try:
        from research_workspace.bot_order_draft import build_order_drafts

        symbol = envelope["content"]["symbol"]
        frame, metadata = synthetic_fixture(symbol)
        if metadata.get("synthetic") is not True:
            raise ValueError("Synthetic fixture required")
        summary, curve, journal = run_rehearsal(frame, metadata, plan=envelope)
        report = build_report(summary, curve, journal)
        checked = verify_report(report)["summary"]
        if checked["synthetic"] is not True:
            raise ValueError("Synthetic report required")
        drafts = build_order_drafts(report, envelope)
        rows = [{
            "Sembol": item["content"]["symbol"],
            "Yön": item["content"]["side"],
            "Adet": item["content"]["quantity"],
            "Sinyal · UTC": item["content"]["signal_at"],
            "Varsayımsal gerçekleşme · UTC": item["content"]["simulated_at"],
            "Taslak kimliği": item["content"]["client_order_id"],
        } for item in drafts]
        draft_payload = json.dumps(drafts, sort_keys=True, allow_nan=False).encode("utf-8")
    except Exception:
        st.error("BOT_PLAN_PREVIEW_REJECTED · Sentetik veri, plan veya taslak kanıtı doğrulanamadı.")
        return

    st.success("Sentetik prova ve taslak denetimi tamamlandı.")
    st.metric("Doğrulanan çevrimdışı taslak", len(rows))
    st.caption("Taslaklar prova sırasında gerçekleşen sinyal niyetlerinden üretilir. "
               "Koruyucu çıkışlar ve henüz gerçekleşmemiş niyetler olay kaydında izlenir.")
    suffix = envelope["sha256"][:12]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.download_button("Doğrulanmış taslakları indir", draft_payload,
                           file_name=f"tradelab-drafts-{suffix}.json", mime="application/json",
                           key="bot_plan_download_drafts", on_click="ignore")
    else:
        st.info("Bu prova, taslağa dönüşen bir gerçekleşme üretmedi.")
    with st.expander("Prova özeti ve olay kaydı"):
        st.json(checked)
        st.dataframe(pd.DataFrame(journal), hide_index=True, width="stretch")
    st.download_button("Doğrulanmış prova raporunu indir", report,
                       file_name=f"tradelab-plan-rehearsal-{suffix}.json", mime="application/json",
                       key="bot_plan_download_report", on_click="ignore")


def render():
    st.subheader("Strateji Planlayıcı")
    st.info("Planı sabitleyin, sentetik mumlarla prova edin ve çevrimdışı işlem taslaklarını inceleyin.")
    if st.get_option("server.address") not in ("127.0.0.1", "::1"):
        st.session_state.pop(PLAN_KEY, None)
        st.session_state.pop(EDIT_KEY, None)
        st.info("Bu ekranı kullanmak için uygulamayı --server.address 127.0.0.1 ile başlatın.")
        return
    st.warning("Çevrimdışı araştırma. Sentetik prova kullanılır ve strateji durumu doğrulanmamış olarak kalır.")

    try:
        from research_workspace import bot_strategy as strategy
    except ImportError:
        st.error("BOT_PLAN_UNAVAILABLE · Strateji doğrulama bileşeni yüklenemedi.")
        return

    payload = st.session_state.get(PLAN_KEY)
    if payload is None:
        _editor(strategy)
        return
    try:
        envelope = strategy.decode_strategy_plan(payload)
    except (ValueError, TypeError):
        st.session_state.pop(PLAN_KEY, None)
        st.session_state.pop(EDIT_KEY, None)
        st.error("BOT_PLAN_CACHE_REJECTED · Sabitlenen plan doğrulanamadı. Planı yeniden oluşturun.")
        _editor(strategy)
        return

    st.success("Plan sabitlendi.")
    st.caption("Plan SHA-256 " + envelope["sha256"])
    st.json(envelope["content"])
    st.download_button("Sabit planı indir", payload,
                       file_name=f"tradelab-strategy-{envelope['sha256'][:12]}.json", mime="application/json",
                       key="bot_plan_download", on_click="ignore")
    if st.button("Planı düzenle", key="bot_plan_edit"):
        st.session_state[EDIT_KEY] = payload
        st.session_state.pop(PLAN_KEY, None)
        st.rerun()
    if st.button("Sabit planı sentetik veride prova et", key="bot_plan_preview"):
        _preview(envelope)
