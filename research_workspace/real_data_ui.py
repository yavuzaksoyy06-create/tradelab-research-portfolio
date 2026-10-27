"""Read-only daily reference data presentation; never invokes the collector."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import sqlite3
from research_workspace.real_sources import catalog
from research_workspace.catalog_sql import reports, COVERAGE_SQL

def render():
    st.info('GERÇEK KAYNAK VERİSİ · Günlük referans değerleri · Yerel, sürümlenmiş anlık görüntü')
    st.caption('Canlı fiyat, OHLCV veya işlem sinyali değildir. V4.1 değerlendirmesine aktarılmaz.')
    entries = catalog()
    with st.expander('SQL katalog raporu · kaynak, sürüm ve seri kapsamı'):
        st.caption('Bellekteki ilişkisel tablolar kullanılır; kaynak dosyalar değiştirilmez. '
                   'Rapor istendiğinde hash ve erişilebilirlik kontrolleri yeniden çalışır.')
        if st.button('SQL raporunu doğrula ve göster', key='sql_catalog_report'):
            try:
                report = reports()
                st.dataframe(pd.DataFrame(report['reconciliation']), hide_index=True, width='stretch')
                st.dataframe(pd.DataFrame(report['coverage']), hide_index=True, width='stretch')
                st.caption('Gözlem tarih aralığı beklenen işlem takviminin eksiksiz olduğunu kanıtlamaz. '
                           'Reddedilen sürümlerin fiyatları rapora alınmaz.')
                st.markdown('**Veri kalitesi · gözlenen tarihlere göre kapsam**')
                st.dataframe(pd.DataFrame(report['quality']), hide_index=True, width='stretch')
                st.caption('Sıfır/negatif sayıları tanımlayıcıdır; tek başına hata değildir. '
                           'Yayın takvimi ve beklenen seri listesi doğrulanmadığı için takvim eksiksizliği bilinmiyor.')
                st.markdown('**Diğer serilerin bulunduğu tarihlerde bulunmayan gözlemler**')
                st.dataframe(pd.DataFrame(report['missing_observations']), hide_index=True, width='stretch')
                st.caption(f"Toplam: {report['missing_observations_total']} · İlk {report['detail_limit']} kayıt gösterilir. "
                           'Serinin o tarihte yayımlanması gerektiği kanıtlanmış değildir; boşluklar doldurulmaz.')
                st.markdown('**Gözlemler arasındaki takvim aralıkları**')
                st.dataframe(pd.DataFrame(report['calendar_gaps']), hide_index=True, width='stretch')
                st.caption(f"Toplam: {report['calendar_gaps_total']} · İlk {report['detail_limit']} aralık gösterilir. "
                           'Hafta sonu ve tatil içerebilir; bu aralıklar veri kaybı olarak sınıflandırılmaz. '
                           'Hiç gözlenmemiş seri ve tüm serilerde kayıp günler eksiksizlik kontrolüyle saptanamaz.')
                st.markdown('**Kaynağa özel yayın referansı karşılaştırması**')
                st.dataframe(pd.DataFrame(report['publication_summary']), hide_index=True, width='stretch')
                st.dataframe(pd.DataFrame(report['publication_missing']), hide_index=True, width='stretch')
                st.caption(f"Toplam eksik: {report['publication_missing_total']} · İlk 500 kayıt gösterilir. "
                           'Yalnızca gözlenen aralık ile doğrulanmış referans aralığının kesişimi incelenir. '
                           'ECB: TARGET takvimi. Treasury: 2025 yayımlanmış tarih referansı; geleceğe yönelik takvim değildir. '
                           'Eksik sonuç, sağlayıcı hatası veya geçmişte bilinen bilgi iddiası değildir.')
                st.code(COVERAGE_SQL, language='sql')
            except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
                st.error('SQL raporu doğrulanamadı: ' + str(exc))
    if not entries:
        st.warning('Doğrulanmış veri sürümü yok. Veri indirme yalnızca ayrı toplama komutuyla yapılır.')
        return
    valid = [e for e in entries if e['status'] == 'verified']
    for e in entries:
        if e['status'] != 'verified':
            st.error('Reddedilen sürüm: ' + e['version'] + ' · ' + e['error'])
    if not valid:
        return
    chosen = st.selectbox('Kaynak ve değişmez sürüm', [e['version'] for e in valid], key='real_version')
    entry = next(e for e in valid if e['version'] == chosen)
    m, source = entry['manifest'], entry['source']
    st.markdown('Kaynak: [' + source['publisher'] + '](' + source['documentation'] + ')')
    st.caption('Birim: ' + source['unit'] + ' · Sıklık: ' + source['frequency'])
    a, b, c = st.columns(3)
    a.metric('Doğrulanan gözlem', m['rows'])
    b.metric('İlk gözlem tarihi', m['first_date'])
    c.metric('Son gözlem tarihi', m['last_date'])
    st.caption('İndirildi / yerel erişilebilirlik: ' + m['collected_at'])
    st.warning('Bu indirme geçmiş yayın sürümlerini kanıtlamaz. Gözlem tarihi yayın zamanı değildir; '
               'tüm satırlar en erken yukarıdaki toplama anında yerel olarak bilinir. Eksik günler doldurulmaz.')
    frame = pd.DataFrame(entry['rows'])
    series = st.selectbox('Seri', sorted(frame['series'].unique()), key='real_series')
    shown = frame[frame.series == series]
    fig = go.Figure(go.Scatter(x=shown.date, y=shown.value, mode='markers', marker=dict(color='#4bd6b0', size=6),
                              hovertemplate='%{x}<br>%{y}<extra></extra>'))
    fig.update_layout(template='plotly_dark', paper_bgcolor='#0b1322', plot_bgcolor='#0b1322',
                      title=source['publisher'] + ' · ' + series, xaxis_title='Gözlem tarihi (gün)',
                      yaxis_title=source['unit'], height=420, showlegend=False)
    st.plotly_chart(fig, width='stretch', key='real_plot')
    st.dataframe(shown, hide_index=True, width='stretch')
    with st.expander('Kaynak kaydı ve hash manifesti'):
        st.caption('SHA-256 yerel bütünlük kontrolüdür; yayıncı imzası veya bağımsız doğrulama değildir. '
                   'Kayıt ve pin birlikte değiştirilirse yerel hash koruması yeterli olmaz.')
        st.json({'manifest_sha256': entry['pin'], 'manifest': m, 'source': source}, expanded=False)
    st.caption('Ücretsiz kamu uç noktaları; hesap/API anahtarı kullanılmaz. Orijinal kaynak gösterilir; '
               'bu aşama ticari yeniden dağıtım hakkı onayı vermez. Strateji getirisi hesaplanmaz.')
