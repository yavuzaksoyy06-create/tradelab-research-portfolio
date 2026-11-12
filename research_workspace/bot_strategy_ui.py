"""Local strategy plan freezing, verified historical preview and draft export."""

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from research_workspace.bot_rehearsal import build_report, run_rehearsal, verify_report
from research_workspace.equity_data import synthetic_fixture
from research_workspace.equity_ui import get_loaded_alpaca_snapshot


PLAN_KEY = "bot_strategy_frozen_plan"
EDIT_KEY = "bot_strategy_editor_seed"
RULE_LABELS = {"ema_trend": "EMA trendi", "channel_breakout": "Kanal kırılımı"}
FIELDS = (
    ("fast", "Kısa pencere (mum)", 9),
    ("slow", "Uzun pencere (mum)", 21),
    ("max_position_bps", "Pozisyon sınırı (bp)", 1000),
    ("planned_risk_bps", "İşlem başına risk (bp)", 50),
    ("stop_bps", "Zarar durdur (bp)", 200),
    ("target_bps", "Kâr hedefi (bp)", 400),
    ("session_loss_bps", "Seans zarar sınırı (bp)", 200),
    ("max_holding_bars", "Azami bekleme (mum)", 4),
)
SIDE_LABELS = {"BUY": "Alış", "SELL": "Satış"}
SYNTHETIC_SOURCE = "Sentetik demo"
ALPACA_SOURCE = "Alpaca · Piyasa Terminali"


def _input_fields(strategy, seed, fields, column_count):
    columns = st.columns(column_count)
    settings = {}
    for i, (field, label, default) in enumerate(fields):
        minimum, maximum = strategy.STRATEGY_BOUNDS[field]
        settings[field] = columns[i % column_count].number_input(
            label, min_value=minimum, max_value=maximum, value=seed.get(field, default),
            step=1, key="bot_plan_" + field,
        )
    return settings


def _editor(strategy):
    seed = {}
    previous = st.session_state.get(EDIT_KEY)
    if previous is not None:
        try:
            seed = strategy.decode_strategy_plan(previous)["content"]
        except (ValueError, TypeError):
            st.session_state.pop(EDIT_KEY, None)

    with st.form("bot_plan_editor"):
        st.markdown("#### 1. Planı oluştur")
        name_col, symbol_col, rule_col = st.columns([1.6, 1, 1.3])
        name = name_col.text_input(
            "Plan adı", value=seed.get("name", "EMA rehearsal"), max_chars=64, key="bot_plan_name",
            help="Latin harfleri, rakamlar, boşluk ve ._- kullanılabilir.",
        )
        symbol = symbol_col.selectbox(
            "Sembol", strategy.STRATEGY_SYMBOLS,
            index=strategy.STRATEGY_SYMBOLS.index(seed.get("symbol", "SPY")), key="bot_plan_symbol",
        )
        rule = rule_col.selectbox(
            "Strateji kuralı", strategy.STRATEGY_RULES,
            index=strategy.STRATEGY_RULES.index(seed.get("rule", "ema_trend")),
            format_func=RULE_LABELS.__getitem__, key="bot_plan_rule",
        )
        settings = _input_fields(strategy, seed, FIELDS[:2], 2)
        st.caption("EMA için bu değerler ortalama dönemidir. Kanal kuralı uzun pencereyi giriş, "
                   "kısa pencereyi çıkış için kullanır.")
        with st.expander("Risk ve çıkış ayarları"):
            st.caption("100 baz puan (bp) %1’e eşittir.")
            settings.update(_input_fields(strategy, seed, FIELDS[2:], 3))
        submitted = st.form_submit_button("Planı doğrula ve sabitle", key="bot_plan_freeze", type="primary")
    if not submitted:
        return
    try:
        envelope = strategy.make_strategy_plan(name, symbol, rule=rule, **settings)
        payload = strategy.encode_strategy_plan(envelope)
    except (ValueError, TypeError):
        st.error("Plan sabitlenemedi. Adı ve risk sınırlarını kontrol edin. "
                 "Kısa pencere uzun pencereden küçük olmalı. (BOT_PLAN_REJECTED)")
        return
    st.session_state[PLAN_KEY] = payload
    st.session_state.pop(EDIT_KEY, None)
    st.rerun()


def _preview(envelope, source):
    try:
        from research_workspace.bot_order_draft import build_order_drafts

        symbol = envelope["content"]["symbol"]
        if source == ALPACA_SOURCE:
            loaded = get_loaded_alpaca_snapshot(symbol)
            if loaded is None:
                st.info(f"{symbol} için Piyasa Terminali’nde Alpaca verisini yükleyin, ardından provayı yeniden başlatın.")
                return
            frame, metadata = loaded
            if (metadata.get("synthetic") is not False or metadata.get("provider_api_response") is not True
                    or metadata.get("symbol") != symbol):
                raise ValueError("Verified Alpaca source required")
        else:
            frame, metadata = synthetic_fixture(symbol)
            if metadata.get("synthetic") is not True:
                raise ValueError("Synthetic fixture required")
        summary, curve, journal = run_rehearsal(frame, metadata, plan=envelope)
        report = build_report(summary, curve, journal)
        checked = verify_report(report)["summary"]
        if checked["synthetic"] is not (source == SYNTHETIC_SOURCE):
            raise ValueError("Report source changed")
        drafts = build_order_drafts(report, envelope)
        rows = [{
            "Yön": SIDE_LABELS[item["content"]["side"]],
            "Adet": item["content"]["quantity"],
            "Sinyal (UTC)": pd.Timestamp(item["content"]["signal_at"]),
            "Varsayımsal gerçekleşme (UTC)": pd.Timestamp(item["content"]["simulated_at"]),
        } for item in drafts]
        draft_payload = json.dumps(drafts, sort_keys=True, allow_nan=False).encode("utf-8")
    except Exception:
        st.error("BOT_PLAN_PREVIEW_REJECTED · Veri kaynağı, plan veya taslak kanıtı doğrulanamadı.")
        return

    st.markdown("#### 3. Prova sonuçları")
    source_tag = "synthetic" if checked["synthetic"] else "alpaca"
    st.badge("Sentetik veri" if checked["synthetic"] else f"Alpaca · {metadata['feed'].upper()}",
             color="orange" if checked["synthetic"] else "green")
    st.caption(f"{symbol} · {len(curve)} görünür mum · {curve.timestamp.iloc[0]:%d.%m.%Y}–{curve.timestamp.iloc[-1]:%d.%m.%Y} · UTC")
    draft_count, closing_value, value_change = st.columns(3)
    draft_count.metric("Doğrulanan taslak", len(rows), border=True)
    closing_value.metric("Hesap son değeri", f"{checked['ending_equity']:,.2f} USD", border=True)
    change = checked["ending_equity"] - checked["starting_cash"]
    value_change.metric("Varsayımsal değişim", f"{change:+,.2f} USD", border=True)
    fig = go.Figure(go.Scatter(
        x=curve.timestamp, y=curve.equity, mode="lines", line=dict(color="#45D9AA", width=2.2),
        hovertemplate="%{x|%d.%m.%Y %H:%M} UTC<br>%{y:,.2f} USD<extra></extra>",
    ))
    fig.update_layout(
        height=275, margin=dict(l=12, r=16, t=18, b=12),
        xaxis_title=None, yaxis_title="Hesap değeri (USD)", hovermode="x",
    )
    st.plotly_chart(fig, width="stretch", key="bot_plan_equity")
    suffix = envelope["sha256"][:12]
    report_col, drafts_col = st.columns(2)
    report_col.download_button("Prova raporunu indir", report,
                               file_name=f"tradelab-plan-{source_tag}-rehearsal-{suffix}.json", mime="application/json",
                               key="bot_plan_download_report", on_click="ignore", width="stretch")
    if rows:
        drafts_col.download_button("İşlem taslaklarını indir", draft_payload,
                                   file_name=f"tradelab-{source_tag}-drafts-{suffix}.json", mime="application/json",
                                   key="bot_plan_download_drafts", on_click="ignore", width="stretch")
        st.markdown("**İşlem taslakları**")
        st.caption("Sinyallerin varsayımsal gerçekleşmelerini gösterir. Koruyucu çıkışları olay kaydında inceleyin.")
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, width="stretch",
            column_config={
                name: st.column_config.DatetimeColumn(format="DD.MM.YYYY HH:mm", timezone="UTC")
                for name in ("Sinyal (UTC)", "Varsayımsal gerçekleşme (UTC)")
            },
        )
    else:
        st.info("Seçilen kuralla bu provada işlem taslağı oluşmadı.")
    with st.expander("Olay kaydı ve teknik rapor"):
        st.json(checked)
        st.dataframe(pd.DataFrame(journal), hide_index=True, width="stretch")


def render():
    st.caption("Bir işlem kuralı ve risk sınırları belirleyin. Sabitlenen planı seçtiğiniz geçmiş mumlarla prova edin.")
    if st.get_option("server.address") not in ("127.0.0.1", "::1"):
        st.session_state.pop(PLAN_KEY, None)
        st.session_state.pop(EDIT_KEY, None)
        st.info("Bu ekranı kullanmak için uygulamayı --server.address 127.0.0.1 ile başlatın.")
        return
    st.badge("Çevrimdışı araştırma", color="blue")

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

    content = envelope["content"]
    with st.container(border=True):
        st.markdown("#### 2. Sabit planı prova et")
        st.badge("Plan sabitlendi", color="green")
        st.text(content["name"])
        identity, risk, exit_plan = st.columns(3)
        identity.markdown(f"**{content['symbol']} · {RULE_LABELS[content['rule']]}**")
        identity.caption(f"{content['fast']} / {content['slow']} mum")
        risk.markdown(f"**%{content['planned_risk_bps'] / 100:.2f} risk**")
        risk.caption(f"Pozisyon sınırı %{content['max_position_bps'] / 100:.2f}")
        exit_plan.markdown(f"**{content['max_holding_bars']} mum**")
        exit_plan.caption("Azami pozisyon süresi")
        available = get_loaded_alpaca_snapshot(content["symbol"])
        source = st.radio("Prova veri kaynağı", (SYNTHETIC_SOURCE, ALPACA_SOURCE),
                          index=1 if available is not None else 0, horizontal=True,
                          key="bot_plan_source")
        if source == ALPACA_SOURCE:
            if available is None:
                st.info(f"{content['symbol']} için Piyasa Terminali’nde Alpaca verisini yükleyin.")
            else:
                loaded_frame, loaded_meta = available
                st.caption(f"{content['symbol']} · Alpaca {loaded_meta['feed'].upper()} · "
                           f"{len(loaded_frame)} doğrulanmış mum · Aynı oturumdaki veri kullanılır.")
        else:
            st.caption("Eğitim amaçlı üretilmiş fiyat ve hacim serisi.")
        preview_col, export_col, edit_col = st.columns([1.5, 1, 1])
        preview = preview_col.button(
            "Provayı başlat", key="bot_plan_preview", type="primary", width="stretch",
        )
        export_col.download_button(
            "Planı indir", payload, file_name=f"tradelab-strategy-{envelope['sha256'][:12]}.json",
            mime="application/json", key="bot_plan_download", on_click="ignore", width="stretch",
        )
        edit = edit_col.button("Planı düzenle", key="bot_plan_edit", width="stretch")
    with st.expander("Plan kimliği ve tüm ayarlar"):
        st.caption("Plan SHA-256 " + envelope["sha256"])
        st.json(content)
    if edit:
        st.session_state[EDIT_KEY] = payload
        st.session_state.pop(PLAN_KEY, None)
        st.rerun()
    if preview:
        _preview(envelope, source)
