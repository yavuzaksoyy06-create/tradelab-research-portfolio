"""TradeLab Research Workspace 0.3.0 Preview — local, read-only UI."""
from pathlib import Path
import sys
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataclasses import asdict,replace
from datetime import date,datetime,timedelta,timezone
import pandas as pd
import streamlit as st
from research_workspace import __version__
from research_workspace.adapters import (DEMO,PROFILE,CASES,ZONES,SYMBOLS,FX_SCENARIOS,MACRO_SCENARIOS,
    forex_view,macro_case,macro_view,time_labels,utc,SCHEMA_VERSION)
from research_workspace.charts import forex_chart,event_chart
from research_workspace.evidence import stored_tests,protected_artifacts,prospective_restrictions,historical_status
from research_workspace.learning import TOPICS
from research_workspace.real_data_ui import render as render_real_data
from research_workspace.financial_ui import render as render_financial

st.set_page_config(page_title='TradeLab · Research Workspace',page_icon='◈',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
.stApp {background:#080f1b;color:#dce5f3;} [data-testid="stSidebar"]{background:#0e1829;border-right:1px solid #26334a;}
.block-container{padding-top:2rem;max-width:1500px;} h1{font-size:2.2rem!important;letter-spacing:-.03em;}
[data-testid="stMetric"]{background:#101c2e;border:1px solid #24344c;border-radius:10px;padding:15px;}
[data-testid="stMetricValue"]{font-size:1.8rem;} .eyebrow{color:#80a5c9;letter-spacing:.15em;font-size:12px;}
.hero{border-bottom:1px solid #25324a;padding-bottom:14px;margin-bottom:24px;}
</style>''',unsafe_allow_html=True)
st.sidebar.markdown('## ◈ TRADELAB')
st.sidebar.caption('RESEARCH WORKSPACE\n\n0.3.0 Preview · localhost')
page=st.sidebar.radio('Çalışma alanı',['Genel Bakış','Gerçek Veri','Financial Analytics','Forex Takvimi','Makro Laboratuvarı','Araştırma Denetimi'],key='page')
learning=st.sidebar.toggle('Öğrenme modu',value=False,key='learning')
st.sidebar.divider()
st.sidebar.info('Salt okunur araştırma\n\nCanlı veri bağlantısı ve emir işlevi yok.')
st.sidebar.caption('Terminal 0.2.0 ayrı uygulamadır. Bu önizleme mevcut deneyleri değiştirmez.')
st.markdown('<div class="hero"><div class="eyebrow">MULTI-MARKET RESEARCH · 0.3.0 PREVIEW</div></div>',unsafe_allow_html=True)
st.title(page)

@st.cache_data(ttl=60,show_spinner=False)
def cached_integrity():return protected_artifacts()

STATUS={'passed':'GEÇTİ','failed':'BAŞARISIZ','stale':'KAYNAK DEĞİŞMİŞ','not_run':'ÇALIŞTIRILMADI','unavailable':'ERİŞİLEMİYOR'}
def status_text(value):return STATUS.get(value,value)

def show_tests(evidence):
    st.caption('Durum: '+status_text(evidence['status'])+' · '+evidence.get('message',''))
    if not evidence['records']:
        st.warning('Test kanıtı bulunamadı veya doğrulanamadı. Başarılı kabul edilmedi.');return
    for record in evidence['records']:
        st.markdown('**'+record['label']+' · '+status_text(record['status'])+'**')
        st.caption(record['recorded_at']+' · '+record.get('time_basis',''))
        rows=[]
        for name,item in record['suites'].items():
            rows.append({'Paket':name,'Test':item['tests'],'Hata':item['failures']+item['errors'],
                         'Atlanan':item['skipped'],'Çıkış':item['exit_code']})
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
        if record['changed_sources']:st.error('Kanıtla eşleşmeyen kaynaklar: '+', '.join(record['changed_sources']))

if page=='Genel Bakış':
    st.caption('Doğrulanmış yazılım yetenekleri, sentetik öğretici deneyler ve donmuş araştırma kayıtları ayrı gösterilir.')
    a,b,c=st.columns(3)
    a.metric('Makro kayıt şeması',str(SCHEMA_VERSION));b.metric('Forex öğretici parite','3');c.metric('Emir / canlı veri','Kapalı')
    st.subheader('Araştırma motorları')
    st.dataframe(pd.DataFrame([
        ['V4 / V4.1','Donmuş tarihsel hisse araştırması','Ayrı Terminal 0.2.0; burada yalnızca durum'],
        ['Crypto','24/7 takvim + manifest','Gerçek veri adaptörü bu arayüzde yok'],
        ['Macro Schema 3','Belge baytları, kaynak uyumu, zaman kontrolleri','Sentetik öğretici belgeler'],
        ['Forex','NY DST, seans, rollover ve mum doğrulama','Varsayımsal sağlayıcı profili'],
        ['Event Study','Tam pencere ve ham betimsel getiri','Sentetik; alpha veya nedensellik sonucu değil']
    ],columns=['Motor','Uygulanan kapsam','Veri / sınır']),hide_index=True,width='stretch')
    historical=historical_status()
    st.subheader('Donmuş tarihsel araştırma · ayrı kanıt alanı')
    if historical['status']=='unavailable':st.warning('Tarihsel kayıt bulunamıyor. Sentetik ekranlar kullanılabilir.')
    else:st.info(historical['message']+' Bu ekranda performans yeniden hesaplanmaz.')
    st.subheader('Saklanmış test kanıtı')
    show_tests(stored_tests())
    st.info('Gerçek Veri: ECB günlük referans kurları ve ABD Hazinesi 2025 faiz serileri; yerel hash doğrulamalı sürümler.')
    st.caption('Planlanan: gerçek 15 dakikalık OHLCV ve geçmiş yayın sürümleri. Henüz uygulanmadı.')

elif page=='Financial Analytics':
    render_financial()

elif page=='Gerçek Veri':
    render_real_data()

elif page=='Forex Takvimi':
    st.warning(DEMO)
    st.caption('Burada fiyat tahmini değil, hangi 15 dakikalık mumların beklenmesi gerektiği incelenir.')
    presets={'Rollover örneği':(date(2026,1,28),date(2026,1,29)),
             'DST · Mart':(date(2026,3,6),date(2026,3,10)),
             'DST · Kasım':(date(2026,10,30),date(2026,11,3)),
             'Hafta sonu':(date(2026,1,31),date(2026,2,1)),
             'Özel tarihler':(date(2026,1,28),date(2026,1,29))}
    c1,c2,c3=st.columns(3)
    symbol=c1.selectbox('Parite',SYMBOLS,key='fx_symbol')
    preset=c2.selectbox('Tarih örneği',list(presets),key='fx_preset')
    zone=c3.selectbox('Açıklama saat dilimi',list(ZONES),key='fx_zone')
    start_day,end_day=presets[preset]
    if preset=='Özel tarihler':
        d1,d2=st.columns(2);start_day=d1.date_input('Başlangıç günü · UTC',start_day,key='fx_start')
        end_day=d2.date_input('Bitiş günü · UTC (hariç)',end_day,key='fx_end')
    scenario=st.selectbox('Veri bütünlüğü deneyi',FX_SCENARIOS,key='fx_scenario')
    partial=st.checkbox('Pazar açılışını 17:05 NY yap · kısmi mum örneği',key='partial_open')
    profile=replace(PROFILE,sunday_open_minute=17*60+5,version='demo-partial-open-1') if partial else PROFILE
    st.info(profile.assumptions+' Profil: '+profile.version)
    try:
        start=datetime.combine(start_day,datetime.min.time(),timezone.utc);end=datetime.combine(end_day,datetime.min.time(),timezone.utc)
        view=forex_view(start,end,symbol=symbol,profile=profile,scenario=scenario)
        report=view['report'];a,b,c,d=st.columns(4)
        st.caption('Sentetik doğrulama kesim anı: '+str(view['as_of'])+' · seçilen pencere sonu, gerçek zamanlı veri değildir.')
        a.metric('Beklenen tam mum',report.expected_count);b.metric('Eksik gözlem',len(report.missing))
        c.metric('Tekrarlı gözlem',len(report.duplicates));d.metric('Geçersiz / erişilemez',len(report.invalid))
        st.plotly_chart(forex_chart(view,zone),width='stretch',key='fx_plot')
        st.caption('Kısmen kesintiye denk gelen mum bütünüyle dışlanır. Kapalı seans, eksik veri değildir. Turuncu/kırmızı durumlar doldurulmaz.')
        st.dataframe(view['frame'][['UTC','New York','İstanbul','status','expected','partial']],hide_index=True,width='stretch',height=300)
        with st.expander('Motor doğrulaması ve profil hash’i'):
            st.json({'validation':asdict(report),'profile_sha256':profile.digest,'as_of':str(view['as_of']),
                     'fixture_note':'OHLCV değerleri yalnızca doğrulama amaçlı varsayımsaldır.'},expanded=False)
    except ValueError as exc:st.error(str(exc))

elif page=='Makro Laboratuvarı':
    st.warning(DEMO)
    st.caption('Tüm olaylar ve fiyatlar öğretici senaryodur. Tarihler gerçek bir duyuru takviminin doğrulaması değildir.')
    c1,c2,c3=st.columns(3)
    case=c1.selectbox('Öğretici olay',list(CASES),key='macro_case')
    symbol=c2.selectbox('Gösterim paritesi',SYMBOLS,key='macro_symbol')
    scenario=c3.selectbox('Senaryo',MACRO_SCENARIOS,key='macro_scenario')
    c1,c2,c3=st.columns(3)
    before=c1.select_slider('Duyuru öncesi · dakika',[15,30,60],value=30,key='before')
    after=c2.select_slider('Duyuru sonrası · dakika',[15,30,60],value=30,key='after')
    clock=c3.selectbox('Bilgi kesim anı',['Pencere sonu','Duyurudan hemen önce','Duyuru anı','Pencere ortası','Pencere sonundan 1 saat sonra'],key='macro_clock')
    fixture=macro_case(case,before=before,after=after,scenario=scenario,symbol=symbol)
    event=fixture['event'];release=utc(event.actual_release_ts);end=fixture['grid'].end
    clocks={'Pencere sonu':end,'Duyurudan hemen önce':release-timedelta(seconds=1),'Duyuru anı':release,
            'Pencere ortası':release+timedelta(minutes=15),'Pencere sonundan 1 saat sonra':end+timedelta(hours=1)}
    cutoff=clocks[clock]
    st.caption('Kesim anı: '+cutoff.strftime('%Y-%m-%d %H:%M:%S UTC'))
    st.caption('Duyuru · '+'  |  '.join(name+': '+value for name,value in time_labels(release).items()))
    try:
        view=macro_view(fixture,cutoff);result=view['result']
        explanations={'available':'Tam pencere gözlenebilir. Ham betimsel getiriler aşağıdadır.',
            'not_yet_available':'Pencere veya veri erişilebilirliği tamamlanmadı. Getiri etiketi üretilmedi.',
            'missing_observations':'Beklenen gözlemler eksik. Getiri hesaplanmadı.',
            'session_closure':'Pencere seans kesintisi içeriyor. Kesinti üzerinden getiri uydurulmadı.'}
        st.info(explanations.get(result.status,result.status))
        a,b,c=st.columns(3)
        a.metric('Gözlenebilir mum',view['visible_count']);b.metric('Henüz erişilemeyen mum',view['hidden_count'])
        c.metric('Olay örnekleme uygun mu?','Evet' if view['event_eligible'] else 'Hayır',help='Duyuru ve bilgi erişimi kesim anına kadar gerçekleşmiş olmalı. Tam getiri penceresi ayrıca denetlenir.')
        st.plotly_chart(event_chart(view,release),width='stretch',key='event_plot')
        st.caption('Mavi: duyuru öncesi. Yeşil: duyuru sonrası. Yalnızca kesim anına kadar erişilebilir gözlemler gösterilir; eksik aralıklar birleştirilmez.')
        if result.raw_return is not None:
            st.warning(DEMO+' · Maliyet öncesi ham fiyat getirisi; işlem getirisi değildir.')
            a,b,c=st.columns(3)
            for col,label,value in [(a,'Tam pencere',result.raw_return),(b,'Duyuru öncesi',result.pre_release_return),(c,'Duyuru sonrası',result.post_release_return)]:
                col.metric(label,'Kullanılamıyor' if value is None else f'{value:.3%}',help='Motorun ham fiyat getirisi yüzde olarak gösterilir. Maliyet, gerçekleşmiş işlem kârı veya nedensel etki değildir.')
        else:st.warning('Getiri: kullanılamıyor. Sıfır getiri olarak yorumlanmamalı.')
        st.dataframe(view['frame'],hide_index=True,width='stretch')
        with st.expander('Kaynak, zaman ve hash kanıtı'):
            st.warning('Sentetik senaryo tanımı ve geriye dönük yerel inceleme. Gerçek yayıncı belgesi veya kullanım hakkı kanıtı değildir.')
            st.json({'source':asdict(event.source),'document':asdict(event.document),'verification':view['evidence'],
                'event_eligible':view['event_eligible'],'label_temporally_available':view['label_temporally_available'],
                'result_provenance':result.provenance,'limitations':result.limitations},expanded=False)
        st.caption('Ham getiri = son kapanış / ilk açılış − 1. Spread, slippage, carry, funding ve istatistiksel anlamlılık dahil değildir.')
    except ValueError as exc:
        st.error('Belge / motor doğrulaması başarısız: '+str(exc))
        st.info('Doğrulama geçmeden grafik veya getiri sunulmadı.')

elif page=='Araştırma Denetimi':
    st.caption('Eksik kayıt başarıya çevrilmez. Geçmiş test kanıtı ve şu anki dosya kontrolü ayrı gösterilir.')
    if st.button('Bütünlük kontrolünü yenile',key='refresh_integrity'):cached_integrity.clear()
    with st.spinner('Korunan dosyalar kontrol ediliyor…'):integrity=cached_integrity()
    st.subheader('Korunan araştırma dosyaları')
    st.metric('Bütünlük durumu',status_text(integrity['status']))
    st.caption('Son kontrol '+integrity.get('checked_at','kullanılamıyor')+' · Sonuç en fazla 60 saniye önbellekte tutulur.')
    st.json(integrity,expanded=False)
    st.subheader('İleri dönem kısıtı')
    restriction=prospective_restrictions()
    st.warning('İleri dönem değerlendirmesi bu uygulamada çalıştırılamaz. Donmuş zaman kapısı ve veri denetimleri korunur.')
    st.json(restriction,expanded=False)
    st.subheader('Test çalıştırma kayıtları')
    show_tests(stored_tests())
    st.caption('Şemalar: Macro 3 · Workspace 0.3.0 Preview + gerçek günlük kaynaklar. Şema 2 kayıtları otomatik dönüştürülmez. Bağımsız yayıncı imzası ve istatistiksel çıkarım mevcut değildir.')

if learning:
    st.divider();st.subheader('Öğrenme modu · araştırma kanıtından ayrı')
    st.info('HİPOTETİK ÖRNEKLER · işlem önerisi veya ölçülmüş performans değildir.')
    topic=st.selectbox('Kavram',list(TOPICS),key='learning_topic')
    st.markdown(TOPICS[topic])
    st.caption('R, varsayımsal birim risktir. Örnek olasılıklar gözlenmiş veri değildir.')
