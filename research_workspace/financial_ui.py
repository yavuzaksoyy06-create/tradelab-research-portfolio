"""Read-only Financial Analytics UI; collection is never invoked here."""
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from research_workspace import real_sources,treasury_v2
from research_workspace.financial_analytics import treasury,fx,compatibility,export_csv
from research_workspace.publication_calendar import publication_reports
from research_workspace.catalog_sql import _database

def entries():
    store=Path(os.environ.get('TRADELAB_REFERENCE_STORE',str(real_sources.STORE)))
    return real_sources.catalog(store)+treasury_v2.catalog()

def render():
    st.caption('Descriptive financial analytics · no orders, no return predictions, no prospective evaluation')
    all_entries=entries();valid=[e for e in all_entries if e.get('status')=='verified' and e.get('available')]
    view=st.selectbox('Analytical view',['US Treasury Analytics','ECB FX Analytics','Data Integrity & Analytical Evidence'],key='financial_view')
    for e in all_entries:
        if e['status']!='verified':st.error('UNVERIFIED OR REJECTED DATA · '+e['version']+' · '+e['error'])
    if not valid:
        st.warning('UNAVAILABLE DATA · No verified snapshots. No charts or synthetic market results are substituted.');return
    if view=='Data Integrity & Analytical Evidence':
        st.dataframe(pd.DataFrame([{'version':e['version'],'source':e['manifest']['source'],'status':e['status'],
            'collected_at':e['manifest']['collected_at'],'available_at':e['manifest']['available_at'],
            'first_date':e['manifest']['first_date'],'last_date':e['manifest']['last_date'],'observations':len(e['rows'])} for e in valid]),hide_index=True)
        db=_database(valid)
        try:report=publication_reports(db)
        finally:db.close()
        st.dataframe(pd.DataFrame(report['publication_summary']),hide_index=True)
        left=[e for e in valid if e['manifest']['source']=='treasury_2025'];right=[e for e in valid if e['manifest']['source']=='ecb_fx']
        if left and right:st.warning(compatibility(left[-1],right[-1])['status'])
        else:st.warning('INSUFFICIENT OVERLAPPING VERIFIED DATES')
        st.info('Collection time is not historical publication time. Joint analysis and point-in-time backtests remain disabled.')
        return
    source='treasury_2025' if view.startswith('US Treasury') else 'ecb_fx'
    options=[e for e in valid if e['manifest']['source']==source]
    if not options:st.warning('UNAVAILABLE DATA · No verified snapshot for this source.');return
    chosen=st.selectbox('Verified dataset version',[e['version'] for e in options],index=len(options)-1,key='financial_version')
    entry=next(e for e in options if e['version']==chosen)
    st.info('SYNTHETIC TEST DATA' if entry.get('synthetic') else 'REAL VERIFIED REFERENCE DATA')
    st.markdown('Source: ['+entry['source']['publisher']+']('+entry['source']['documentation']+')')
    try:
        if source=='treasury_2025':
            result=treasury(entry);curves=result['curves'];dates=sorted(curves.date.unique())
            chosen_dates=st.multiselect('Observed dates to compare',dates,default=dates[-2:],key='curve_dates')
            shown=curves[curves.date.isin(chosen_dates)]
            st.plotly_chart(px.scatter(shown,x='maturity_months',y='value',color='date',hover_data=['series'],labels={'value':'Annualized par yield (%)','maturity_months':'Maturity (months)'},title='Treasury par yield curves · observed points only'),width='stretch',key='yield_curve')
            st.caption('No curve interpolation. 10Y minus 2Y / 3M < 0 defines inversion. Rate changes are not bond total returns.')
            st.dataframe(result['spreads'],hide_index=True,key='spread_table')
            st.dataframe(result['changes_bp'],hide_index=True,key='bp_table')
            st.caption('Basis-point change = 100 × difference in percent yields, versus the preceding observed date. Missing cells remain missing; intervals may span non-publication days.')
            for name in ['curves','spreads','changes_bp']:
                st.download_button('Export '+name,export_csv(result[name],{**result['metadata'],'transformation':name}),file_name=name+'.csv',mime='text/csv',key='export_'+name)
        else:
            series=st.selectbox('EUR base / quote currency',sorted({r['series'] for r in entry['rows']}),key='currency_series')
            dates=sorted({r['date'] for r in entry['rows'] if r['series']==series})
            start=st.selectbox('Observed starting date',dates,key='return_start')
            window=st.number_input('Rolling window · observed returns',min_value=2,max_value=252,value=20,step=1,key='vol_window')
            result=fx(entry,series,int(window),start);table=result['table']
            st.plotly_chart(px.scatter(table,x='date',y='quote_per_eur',title=series+' · reference rates'),width='stretch',key='reference_rates')
            st.plotly_chart(px.histogram(table,x='simple_return_pct',title='Observed reference-rate change distribution (%)'),width='stretch',key='return_distribution')
            st.dataframe(table,hide_index=True,key='fx_results')
            st.caption('Quote currency units per EUR: a positive change means EUR appreciation. Simple = 100×(q/q_prev−1); log = ln(q/q_prev). Volatility is sample standard deviation of log changes, not annualized; requires a full window. Known missing intervals break the estimate. Reference changes are not executable trading returns.')
            st.download_button('Export FX analytics',export_csv(table,result['metadata']),file_name='fx_analytics.csv',mime='text/csv',key='export_fx')
        st.subheader('SQL observation coverage')
        st.dataframe(result['coverage'],hide_index=True)
        with st.expander('Reproducibility metadata'):st.json(result['metadata'])
    except (ValueError,KeyError,TypeError) as exc:st.error('Analysis unavailable: '+str(exc))
