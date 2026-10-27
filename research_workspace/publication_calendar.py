"""Offline, bounded publication reference comparisons; no collector changes."""
from datetime import date, timedelta
from pathlib import Path
import hashlib
import json

REFERENCE = Path(__file__).parent / 'reference_calendars' / 'review_20261028.json'
REFERENCE_SHA256 = 'b4a650d62039da107d2b98a66c47f3c7751d0f64d8c42d5dc38770975013bd76'

def load_profiles():
    raw=REFERENCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=REFERENCE_SHA256:
        raise ValueError('Publication reference hash mismatch')
    return json.loads(raw)

def publication_reports(db, limit=500):
    profiles=load_profiles(); summaries=[]; details=[]; total=0
    versions=db.execute("SELECT version_id,source_id FROM versions WHERE status='verified' ORDER BY version_id").fetchall()
    for version,source in versions:
        p=profiles.get(source)
        rows=db.execute('SELECT observation_date,series FROM observations WHERE version_id=?',(version,)).fetchall()
        actual={(d,s) for d,s in rows}
        summary={'version_id':version,'source':source,'status':'unknown','missing_expected':None,
                 'reference_sha256':REFERENCE_SHA256,'point_in_time':False}
        if not p or not rows:
            summary['reason']='No reviewed profile or no observations to bound the assessment'
            summaries.append(summary);continue
        first,last=min(d for d,s in rows),max(d for d,s in rows)
        start,end=max(first,p['from']),min(last,p['through'])
        summary.update(calendar_basis=p['calendar_basis'],reference_url=p['reference_url'],
                       review_date=p['reviewed_on'],scope_from=start,scope_through=end,
                       outside_reference_range=first<p['from'] or last>p['through'])
        if start>end:
            summary['reason']='Outside reviewed range';summaries.append(summary);continue
        if p['calendar_basis']=='TARGET_2026':
            day=date.fromisoformat(start);days=[]
            while day.isoformat()<=end:
                if day.weekday()<5 and day.isoformat() not in p['target_closures']:days.append(day.isoformat())
                day+=timedelta(days=1)
        else:
            days=[d for d in p['published_dates'] if start<=d<=end]
        expected={(d,s) for s,span in p['series'].items() for d in days if span['from']<=d<=span['through']}
        missing=sorted(expected-actual)
        absent=sorted({s for d,s in expected}-{s for d,s in actual})
        unexpected=sorted({s for d,s in actual if start<=d<=end}-set(p['series']))
        summary.update(status='bounded_reference_comparison',expected_observations=len(expected),
                       missing_expected=len(missing),entirely_absent_series=absent,unexpected_series=unexpected,
                       outside_expected_grid=sum(1 for pair in actual if start<=pair[0]<=end and pair not in expected))
        total+=len(missing)
        for day,series in missing:
            if len(details)<limit:details.append({'version_id':version,'observation_date':day,'series':series,
                                                'basis':p['calendar_basis'],'finding':'absent_from_normalized_snapshot'})
        summaries.append(summary)
    return {'publication_summary':summaries,'publication_missing':details,'publication_missing_total':total,
            'publication_missing_truncated':total>limit,'publication_reference_sha256':REFERENCE_SHA256}
