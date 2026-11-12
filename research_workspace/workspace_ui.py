"""Shared page chrome and the research terminal landing screen."""

from pathlib import Path

import streamlit as st


PAGES = {
    "Genel Bakış": ("Genel Bakış", "ARAŞTIRMA TERMİNALİ", ""),
    "Equity Research": ("Piyasa Terminali", "01  /  PİYASA VERİSİ", "ABD hisselerinde tamamlanmış mumlar, fiyat grafiği ve teknik analiz."),
    "Strateji Planlayıcı": ("Strateji Planlayıcı", "02  /  STRATEJİ TASARIMI", "Kurallarını ve risk sınırlarını sabitle, planını tekrar üretilebilir bir provada incele."),
    "Bot Provası": ("Bot Provası", "03  /  YÜRÜTME ARAŞTIRMASI", "Varsayımsal gerçekleşmeleri, maliyetleri ve durdurma kontrollerini test et."),
    "BIST Research": ("BIST Araştırması", "PİYASA ARAŞTIRMASI", "Yerel, doğrulanabilir BIST fiyat dosyalarıyla tarihsel inceleme."),
    "Istanbul ML": ("İstanbul ML · v1", "MODEL ARAŞTIRMASI", "Sabit tarihsel deney, karşılaştırmalar ve veri sınırları."),
    "Istanbul ML v2": ("İstanbul ML · v2", "MODEL ARAŞTIRMASI", "Ayrı kayıtlı yön deneyi ve zamana duyarlı doğrulama."),
    "Gerçek Veri": ("Veri Kataloğu", "KAYNAK VE KALİTE", "Kayıtlı veri sürümlerini, kapsamı ve eksik gözlemleri incele."),
    "Financial Analytics": ("Finansal Analiz", "FİNANS LABORATUVARI", "Faiz serileri ve referans kurlar üzerinden açıklanabilir analizler."),
    "Forex Takvimi": ("Forex Takvimi", "SEANS ARAŞTIRMASI", "Saat dilimleri, kapanışlar ve beklenen mumlar."),
    "Makro Laboratuvarı": ("Makro Laboratuvarı", "OLAY ARAŞTIRMASI", "Duyuru zamanını ve görünür veri penceresini test et."),
    "Araştırma Denetimi": ("Araştırma Denetimi", "KANIT VE BÜTÜNLÜK", "Kaynak hash’leri, test kanıtları ve araştırma sınırları."),
}

_STYLE = Path(__file__).with_name("assets") / "workspace.css"


def navigate(page):
    """Set the existing native route through a Streamlit widget callback."""
    st.session_state["page"] = page


def render_shell():
    st.markdown("<style>" + _STYLE.read_text(encoding="utf-8") + "</style>", unsafe_allow_html=True)
    with st.sidebar:
        st.markdown(
            '<div class="tl-brand"><span class="tl-brand-mark" aria-hidden="true">'
            '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M5 14v7m7-16v13m7-15v11M3 16h4v3H3zm7-7h4v5h-4zm7-4h4v5h-4z"/>'
            '</svg></span><div><strong>TradeLab</strong><small>Araştırma terminali</small></div></div>',
            unsafe_allow_html=True,
        )
        st.caption("ÇALIŞMA ALANI")
        page = st.radio("Çalışma alanı", tuple(PAGES), format_func=lambda key: PAGES[key][0],
                        key="page", label_visibility="collapsed")
        st.divider()
        learning = st.toggle("Öğrenme modu", value=False, key="learning")
        st.caption("Yerel oturum · Emir gönderimi kapalı")
    if page != "Genel Bakış":
        title, section, description = PAGES[page]
        st.markdown(f'<div class="tl-kicker">{section}</div>', unsafe_allow_html=True)
        st.title(title)
        st.caption(description)
    return page, learning


def render_home(provider_status):
    st.markdown(
        '<section class="tl-hero" aria-label="TradeLab araştırma terminali">'
        '<div><div class="tl-kicker">TRADELAB  /  ARAŞTIRMA ÇALIŞMA ALANI</div>'
        '<h1>Piyasayı incele.<br>Stratejini sına.</h1>'
        '<p>Geçmiş piyasa verisini aç, fiyat ve hacim davranışını incele, kurallarını risk kontrollü provada dene.</p></div>'
        '<ol class="tl-workflow"><li><b>01</b> Veri ve grafik</li>'
        '<li><b>02</b> Strateji planı</li><li><b>03</b> Çevrimdışı prova</li></ol></section>',
        unsafe_allow_html=True,
    )
    st.subheader("Nereden başlamak istersin?")
    st.caption("Piyasa Terminali, Alpaca üzerinden tamamlanmış 15 dakikalık ABD hisse mumlarını yükler.")
    source_label = {
        "configured": "Alpaca anahtarları tanımlı · bağlantı yükleme sırasında kontrol edilir",
        "incomplete": "Alpaca anahtar çifti eksik",
        "missing": "Alpaca anahtarları bu oturumda tanımlı değil",
    }.get(provider_status, "Alpaca bağlantı durumu doğrulanamadı")
    cards = (
        ("Piyasa Terminali", "Fiyat, hacim, destek ve direnç bölgeleri", source_label,
         "Grafiği aç", "Equity Research", "primary"),
        ("Strateji Planlayıcı", "EMA veya kanal kırılımı için kural ve risk sınırları",
         "Planı sabitle · Provayı incele", "Plan oluştur", "Strateji Planlayıcı", "secondary"),
        ("Bot Provası", "Maliyet, gecikme ve durdurma senaryoları",
         "Çevrimdışı · Rapor indirilebilir", "Provayı aç", "Bot Provası", "secondary"),
    )
    with st.container(key="tl_home_cards"):
        columns = st.columns(3, gap="medium")
        for column, (title, body, detail, action, route, kind) in zip(columns, cards):
            with column, st.container(border=True):
                st.markdown(f"**{title}**")
                st.write(body)
                st.caption(detail)
                st.button(action, key=f"tl_home_{kind}_{route}", type=kind, width="stretch",
                          on_click=navigate, args=(route,))
