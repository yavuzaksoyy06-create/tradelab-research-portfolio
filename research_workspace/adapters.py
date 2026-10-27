"""Teaching fixtures and presentation adapters; all validation uses existing engines."""
from dataclasses import asdict, replace
from datetime import timedelta
from zoneinfo import ZoneInfo
import hashlib
import pandas as pd
from research_fx.calendar import HoursProfile, Bar, SYMBOLS, utc, expected_grid, validate_bars
from research_macro.events import build_macro_event, is_in_sample, SCHEMA_VERSION
from research_macro.documents import registry_digest, verify_document_bytes
from research_macro.availability import response_label_available
from research_macro.event_study import Instrument, Observation, fx_session_grid, study_event

DEMO = 'SYNTHETIC RESEARCH DEMO — NOT REAL MARKET DATA'
ZONES = {'UTC':'UTC', 'New York':'America/New_York', 'İstanbul':'Europe/Istanbul'}
PROFILE = HoursProfile('TEACHING-ONLY / not a broker', 'demo-1',
    'Varsayımsal saatler: Pazar 17:00–Cuma 17:00 New York; Pzt–Per 17:00–17:05 bakım. Resmî sağlayıcı saati değildir.')
CASES = {
    'FOMC': ('FOMC_STATEMENT', 'FRB_FOMC', 'Federal Reserve Board', '2026-01-28T19:00:00Z',
             'https://www.federalreserve.gov/aboutthefed/contact-us-topics.htm', 'https://www.federalreserve.gov/example/synthetic-fomc.htm'),
    'CPI': ('CPI_RELEASE', 'BLS_CPI', 'Bureau of Labor Statistics', '2026-01-14T13:30:00Z',
            'https://www.bls.gov/bls/linksite.htm', 'https://www.bls.gov/example/synthetic-cpi.htm'),
    'NFP': ('NFP_RELEASE', 'BLS_NFP', 'Bureau of Labor Statistics', '2026-01-09T13:30:00Z',
            'https://www.bls.gov/bls/linksite.htm', 'https://www.bls.gov/example/synthetic-nfp.htm'),
}
FX_SCENARIOS = ('Tam sentetik ızgara', 'Eksik mum', 'Tekrarlı mum', 'Geçersiz OHLC', 'Gecikmiş erişim')
MACRO_SCENARIOS = ('Tam pencere', 'Eksik gözlem', 'Seans kesintisi', 'Gecikmiş fiyat', 'Bozuk belge')

def time_labels(value):
    t=utc(value)
    return {name:t.astimezone(ZoneInfo(zone)).strftime('%Y-%m-%d %H:%M %Z') for name,zone in ZONES.items()}

def forex_view(start, end, *, symbol='EUR/USD', profile=PROFILE, scenario=FX_SCENARIOS[0]):
    start,end=utc(start),utc(end)
    if not timedelta(0)<end-start<=timedelta(days=7):
        raise ValueError('Aralık 1 dakika ile 7 gün arasında olmalı.')
    if scenario not in FX_SCENARIOS:raise ValueError('Bilinmeyen senaryo')
    step=timedelta(minutes=15)
    valid=expected_grid(start,end,symbol=symbol,profile=profile)
    weekly=set(expected_grid(start,end,symbol=symbol,profile=replace(profile,maintenance_minutes=0,closures=())))
    maintenance=set(expected_grid(start,end,symbol=symbol,profile=replace(profile,closures=())))
    fine=set(expected_grid(start,end,symbol=symbol,profile=profile,minutes=1))
    valid_set=set(valid)
    bars=[Bar(t,100.,101.,99.,100.5,100.,t+step) for t in valid]
    if bars:
        if scenario=='Eksik mum':bars.pop(0)
        elif scenario=='Tekrarlı mum':bars.insert(0,bars[0])
        elif scenario=='Geçersiz OHLC':bars[0]=replace(bars[0],high=98.)
        elif scenario=='Gecikmiş erişim':bars[0]=replace(bars[0],available_at=end+step)
    report=validate_bars(bars,start,end,symbol=symbol,profile=profile,as_of=end)
    invalid_times={utc(bars[i].timestamp) for i,_ in report.invalid}
    rows=[];cursor=start
    while cursor<end:
        partial=0<sum(cursor+timedelta(minutes=i) in fine for i in range(15))<15
        if cursor not in weekly:status='Kısmi seans' if partial else 'Hafta sonu / seans kapalı'
        elif cursor not in maintenance:status='Kısmi rollover bakımı' if partial else 'Rollover bakımı'
        elif cursor not in valid_set:status='Kısmi özel kesinti' if partial else 'Özel kesinti'
        elif cursor in report.missing:status='Eksik gözlem'
        elif cursor in report.duplicates:status='Tekrarlı gözlem'
        elif cursor in invalid_times:status='Geçersiz / henüz erişilemez'
        else:status='Beklenen tam mum'
        rows.append({'timestamp':cursor,'status':status,'expected':cursor in valid_set,
                     'partial':partial,**time_labels(cursor)})
        cursor+=step
    return {'frame':pd.DataFrame(rows),'report':report,'profile':profile,'bars':tuple(bars),
            'expected':valid,'as_of':end,'synthetic':True,'label':DEMO}

def macro_case(case='FOMC', *, before=30, after=30, scenario='Tam pencere', symbol='EUR/USD'):
    if case not in CASES or before not in (15,30,60) or after not in (15,30,60):
        raise ValueError('Geçersiz öğretici olay veya pencere')
    if scenario not in MACRO_SCENARIOS:raise ValueError('Bilinmeyen senaryo')
    kind,source_id,publisher,release_text,terms,url=CASES[case]
    release=utc(release_text);start=release-timedelta(minutes=before);end=release+timedelta(minutes=after)
    data=f'SYNTHETIC teaching document for {case}; not a publisher document.'.encode()
    digest=hashlib.sha256(data).hexdigest()
    # These are fixed, synthetic review timestamps, not real publisher verification.
    reviewed='2026-02-01T00:00:00Z'
    source=dict(source_id=source_id,publisher=publisher,license_class='US-GOV-PD',verification='catalog_verified',
                access_terms_url=terms,verified_at=reviewed,usage_policy='local_descriptive_research')
    document=dict(source_id=source_id,url=url,fetched_at=release+timedelta(minutes=2),
        fetch_authorized=True,sha256=digest,bytes_size=len(data),integrity_verified=False,content_type='text/plain',
        role='announcement',published_at=release_text)
    event=build_macro_event(event_id='SYNTHETIC-'+case,event_type=kind,meeting_kind='regular' if case=='FOMC' else 'not_applicable',
        research_mode='explanatory_event_study',source=source,document=document,scheduled_event_ts=release,
        actual_release_ts=release,information_available_ts=release+timedelta(seconds=1),
        response_window_start=start,response_window_end=end)
    registry={'schema_version':1,'documents':{url:{'source_id':source_id,'sha256':digest,'bytes_size':len(data),
        'reviewer':'SYNTHETIC fixture reviewer','review_reference':'teaching-fixture-v1 (not real review)',
        'reviewed_at':reviewed,'terms_url':terms,'allowed_uses':['local_descriptive_research']}}}
    verification=dict(document_bytes=data,trust_registry=registry,registry_sha256=registry_digest(registry),verified_at=reviewed)
    profile=PROFILE
    if scenario=='Seans kesintisi':profile=replace(PROFILE,version='demo-closure-1',closures=((release,release+timedelta(minutes=5)),))
    grid=fx_session_grid(start,end,symbol=symbol,profile=profile)
    # Deterministic hypothetical index levels. Never described as historical FX prices.
    full=expected_grid(start,end,symbol=symbol,profile=PROFILE)
    indices={t:i for i,t in enumerate(full)}
    bars=[Observation(t,100+indices[t]*.25,100+indices[t]*.25+(.35 if t>=release else -.1),t+timedelta(minutes=15)) for t in grid.opens]
    if scenario=='Eksik gözlem' and bars:bars.pop(0)
    if scenario=='Gecikmiş fiyat' and bars:bars[-1]=replace(bars[-1],available_at=end+timedelta(hours=1))
    if scenario=='Bozuk belge':verification['document_bytes']=data+b' altered'
    return dict(event=event,bars=tuple(bars),grid=grid,verification=verification,profile=profile,
                instrument=Instrument(symbol,'fx','JPY' if symbol=='USD/JPY' else 'USD','synthetic index; base 100'),
                synthetic=True,label=DEMO)

def macro_view(fixture, as_of):
    """Filter both plots AND returned data tables before the cutoff; engine gates labels."""
    cutoff=utc(as_of);event=fixture['event']
    evidence=verify_document_bytes(event,**fixture['verification'])
    visible=tuple(b for b in fixture['bars'] if utc(b.available_at)<=cutoff)
    eligible=is_in_sample(event,cutoff)
    temporal=response_label_available(event,cutoff,observations_available_at=[b.available_at for b in fixture['bars']])
    # Full fixture is passed only to a fail-closed engine; future prices are never returned by this adapter.
    result=study_event(event,fixture['bars'],instrument=fixture['instrument'],grid=fixture['grid'],as_of=cutoff,
        source_reference='SYNTHETIC teaching fixture v1',synthetic=True,verification_inputs=fixture['verification'])
    release=utc(event.actual_release_ts)
    frame=pd.DataFrame([{'timestamp':utc(b.timestamp),'available_at':utc(b.available_at),
        'open':b.open,'close':b.close,'phase':'Duyuru öncesi' if utc(b.timestamp)<release else 'Duyuru sonrası',
        **time_labels(b.timestamp)} for b in visible],columns=['timestamp','available_at','open','close','phase',*ZONES])
    # Do not expose a future-data hash in UI as if it were an as-of observation snapshot.
    provenance=dict(result.provenance)
    if len(visible)!=len(fixture['bars']):
        provenance.pop('observations_sha256',None)
        provenance['observations_note']='Full fixture hash hidden: not all observations are available as of the cursor.'
    return dict(frame=frame,result=replace(result,provenance=provenance),evidence=asdict(evidence),
                event_eligible=eligible,label_temporally_available=temporal,
                visible_count=len(visible),hidden_count=len(fixture['bars'])-len(visible),as_of=cutoff,
                label=DEMO,synthetic=True)
