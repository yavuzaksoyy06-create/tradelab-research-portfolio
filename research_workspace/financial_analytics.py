"""Descriptive transforms only: no strategy, orders, or historical vintage claims."""
from datetime import date
from pathlib import Path
import hashlib
import math
import sqlite3
import pandas as pd
from research_workspace import real_sources as old, treasury_v2
from research_workspace.publication_calendar import load_profiles, REFERENCE_SHA256

def frame(entry,source):
    if entry.get('status')!='verified' or not entry.get('verified') or not entry.get('available'):
        raise ValueError('UNVERIFIED OR REJECTED DATA')
    m=entry['manifest']
    if m['source']!=source or entry['source']['unit']!=old.SOURCES[source]['unit']:raise ValueError('Source/unit mismatch')
    old.require(old.aware(m['collected_at'])<=old.aware(m['available_at'])<=old.now(),'Invalid collection/availability ordering')
    df=pd.DataFrame(entry['rows'],columns=['date','series','value'])
    if df.empty:raise ValueError('UNAVAILABLE DATA')
    if df.duplicated(['date','series']).any():raise ValueError('Duplicate observations')
    for row in df.itertuples():
        if date.fromisoformat(row.date).isoformat()!=row.date or row.date>old.aware(m['collected_at']).date().isoformat():raise ValueError('Invalid date')
        if not math.isfinite(row.value) or (row.value<=0 if source=='ecb_fx' else row.value<0):raise ValueError('Invalid value')
    return df.sort_values(['date','series']).reset_index(drop=True)

def metadata(entry):
    m=entry['manifest']
    return {'version':entry['version'],'source':m['source'],'source_url':m['source_url'],
            'manifest_sha256':entry['pin'],'collected_at':m['collected_at'],
            'available_at':m['available_at'],'unit':entry['source']['unit'],
            'point_in_time_history':False,'evaluation_enabled':False,
            'synthetic':bool(entry.get('synthetic',False)),
            'analytics_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'publication_reference_sha256':REFERENCE_SHA256}

def interval_assessment(previous,current,profile):
    if previous is None or pd.isna(previous):return 'no_previous_observation'
    if not (profile['from']<=previous<=current<=profile['through']):return 'unreviewed_calendar'
    between=pd.date_range(previous,current)[1:-1]
    if profile['calendar_basis']=='TARGET_2026':
        missing=any(d.weekday()<5 and d.strftime('%Y-%m-%d') not in profile['target_closures'] for d in between)
    else:
        missing=any(previous<d<current for d in profile['published_dates'])
    return 'known_missing_publication' if missing else 'consecutive_reference_observations'


def treasury(entry):
    df=frame(entry,'treasury_2025')
    if not set(df.series)<=set(treasury_v2.TENORS):raise ValueError('Unknown maturity')
    wide=df.pivot(index='date',columns='series',values='value').sort_index()
    summary=pd.DataFrame(index=wide.index)
    for short,label in [('BC_2YEAR','10y_minus_2y_bp'),('BC_3MONTH','10y_minus_3m_bp')]:
        summary[label]=(wide['BC_10YEAR']-wide[short])*100 if {'BC_10YEAR',short}<=set(wide.columns) else float('nan')
        summary[label+'_inverted']=summary[label].map(lambda x:None if pd.isna(x) else bool(x<0))
    changes=wide.diff()*100  # no implicit fill; each cell requires consecutive observed dates
    summary['previous_observed_date']=pd.Series(wide.index,index=wide.index).shift()
    summary['interval_calendar_days']=pd.to_datetime(pd.Series(wide.index,index=wide.index)).diff().dt.days
    profile=load_profiles()['treasury_2025']
    summary['interval_assessment']=[interval_assessment(prev,day,profile) for day,prev in zip(wide.index,summary.previous_observed_date)]
    summary['known_missing_interval']=summary.interval_assessment.eq('known_missing_publication')
    changes.loc[summary.known_missing_interval,:]=float('nan')
    for column in ['previous_observed_date','interval_calendar_days','interval_assessment','known_missing_interval']:
        changes[column]=summary[column]
    curves=df.copy();curves['maturity_months']=curves.series.map(treasury_v2.TENORS)
    curves=curves.sort_values(['date','maturity_months'])
    return {'curves':curves,'spreads':summary.reset_index(),'changes_bp':changes.reset_index(),
            'coverage':sql_summary(df),'metadata':metadata(entry)}

def sql_summary(df):
    db=sqlite3.connect(':memory:')
    try:
        db.execute('CREATE TABLE observations(day TEXT,series TEXT,value REAL,PRIMARY KEY(day,series))')
        db.executemany('INSERT INTO observations VALUES (?,?,?)',df[['date','series','value']].itertuples(index=False,name=None))
        db.execute('PRAGMA query_only=ON')
        return pd.read_sql_query('SELECT series,COUNT(*) AS observations,MIN(day) AS first_date,MAX(day) AS last_date,MIN(value) AS minimum,MAX(value) AS maximum FROM observations GROUP BY series ORDER BY series',db)
    finally:db.close()

def fx(entry,series='EUR/USD',window=20,start=None):
    if not isinstance(window,int) or isinstance(window,bool) or window<2:raise ValueError('Window must be at least 2 observations')
    df=frame(entry,'ecb_fx');series_df=df[df.series==series].copy().sort_values('date')
    if series_df.empty:raise ValueError('Unavailable currency series')
    if not series.startswith('EUR/'):raise ValueError('Unsupported quotation direction')
    start=start or series_df.date.iloc[0]
    if start not in set(series_df.date):raise ValueError('Starting date must be observed')
    series_df=series_df[series_df.date>=start].reset_index(drop=True)
    out=series_df[['date','value']].rename(columns={'value':'quote_per_eur'})
    prev=out.quote_per_eur.shift();out['previous_observed_date']=out.date.shift()
    out['interval_calendar_days']=pd.to_datetime(out.date).diff().dt.days
    out['simple_return_pct']=(out.quote_per_eur/prev-1)*100
    out['log_return']=out.quote_per_eur.map(math.log)-prev.map(lambda x:math.log(x) if pd.notna(x) else float('nan'))
    # A known missing scheduled observation breaks the rolling estimate, never fills it.
    profile=load_profiles()['ecb_fx'];days=set(df.date);selected_days=set(series_df.date)
    assessments=[]
    for row in out.itertuples():
        assessment=interval_assessment(row.previous_observed_date,row.date,profile)
        if pd.notna(row.previous_observed_date):
            if any(row.previous_observed_date<d<row.date and d not in selected_days for d in days):
                assessment='known_missing_publication'
        assessments.append(assessment)
    out['interval_assessment']=assessments
    out['known_missing_interval']=out.interval_assessment.eq('known_missing_publication')
    out.loc[out.known_missing_interval,['simple_return_pct','log_return']]=float('nan')
    eligible=out.log_return.where(out.interval_assessment.eq('consecutive_reference_observations'))
    out['rolling_log_volatility']=eligible.rolling(window,min_periods=window).std(ddof=1)
    out['cumulative_change_pct']=(out.quote_per_eur/out.quote_per_eur.iloc[0]-1)*100
    return {'table':out,'coverage':sql_summary(df[df.series==series]),'metadata':{**metadata(entry),
            'series':series,'rolling_window_observations':window,'volatility_ddof':1,'annualized':False,
            'return_basis':'adjacent observed reference dates; known missing intervals excluded',
            'volatility_interval_policy':'reviewed consecutive reference observations only',
            'start_date':start,'quotation':'quote currency units per EUR; positive change means EUR appreciation'}}

def compatibility(left,right):
    # Verified overlap is necessary but never sufficient for PIT research.
    a=frame(left,left['manifest']['source']);b=frame(right,right['manifest']['source'])
    overlap=sorted(set(a.date)&set(b.date))
    return {'status':'INSUFFICIENT OVERLAPPING VERIFIED DATES' if len(overlap)<2 else 'DEFINITION AND AVAILABILITY REVIEW REQUIRED',
            'overlap_dates':overlap,'joint_analysis_enabled':False,'point_in_time_enabled':False}

def export_csv(table,meta):
    result=table.copy()
    for key,value in meta.items():result['meta_'+key]=str(value)
    # Guard spreadsheet formula execution in exported text fields.
    for column in result.columns:
        result[column]=result[column].map(lambda x:"'"+x if isinstance(x,str) and (x.lstrip().startswith(('=','+','-','@')) or x.startswith(('\t','\r','\n'))) else x)
    return result.to_csv(index=False).encode('utf-8')
