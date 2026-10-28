"""Offline Treasury v2 derivatives; legacy verifier and snapshots remain unchanged."""
from pathlib import Path
import json
import math
import re
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import date
from research_workspace import real_sources as old

STORE=Path(__file__).parent/'real_data_v2'
REVISION='treasury-explicit-tenors-2'
TENORS={'BC_1MONTH':1,'BC_1_5MONTH':1.5,'BC_2MONTH':2,'BC_3MONTH':3,
        'BC_4MONTH':4,'BC_6MONTH':6,'BC_1YEAR':12,'BC_2YEAR':24,'BC_3YEAR':36,
        'BC_5YEAR':60,'BC_7YEAR':84,'BC_10YEAR':120,'BC_20YEAR':240,'BC_30YEAR':360}
M='http://schemas.microsoft.com/ado/2007/08/dataservices/metadata'
D='http://schemas.microsoft.com/ado/2007/08/dataservices'

def parse(raw):
    old.require(0<len(raw)<=old.LIMIT,'Empty or oversized XML')
    old.require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),'XML declarations forbidden')
    root=ET.fromstring(raw);old.require(root.tag=='{http://www.w3.org/2005/Atom}feed','Unexpected Treasury schema')
    rows=[];missing=[];keys=set();days=set()
    for prop in root.iter('{'+M+'}properties'):
        dt=prop.find('{'+D+'}NEW_DATE');old.require(dt is not None and dt.text,'Missing date')
        day=date.fromisoformat(dt.text[:10]).isoformat()
        old.require(day.startswith('2025-') and day not in days,'Invalid or duplicate date');days.add(day)
        seen=set()
        for item in prop:
            field=item.tag.split('}')[-1]
            if field in {'NEW_DATE','Id','ID','BC_30YEARDISPLAY'}:continue
            if field.startswith('BC_'):old.require(field in TENORS,'Unknown Treasury tenor')
            if field not in TENORS:continue
            old.require(field not in seen,'Duplicate tenor');seen.add(field)
            active=field!='BC_1_5MONTH' or day>='2025-02-18'
            null=item.attrib.get('{'+M+'}null')=='true'
            if null:
                if active:missing.append({'date':day,'series':field,'reason':'publisher_null'})
                continue
            old.require(active,'Tenor before activation')
            value=float(item.text);old.require(math.isfinite(value) and value>=0,'Invalid rate')
            key=(day,field);old.require(key not in keys,'Duplicate observation');keys.add(key)
            rows.append({'date':day,'series':field,'value':value})
        for field in TENORS:
            if field not in seen and (field!='BC_1_5MONTH' or day>='2025-02-18'):
                missing.append({'date':day,'series':field,'reason':'publisher_field_absent'})
    old.require(rows,'No observations')
    return sorted(rows,key=lambda r:(r['date'],r['series'])),sorted(missing,key=lambda r:(r['date'],r['series']))

def code_hashes():
    return {'normalizer':old.sha(Path(__file__).read_bytes()),'legacy_verifier':old.sha(Path(old.__file__).read_bytes())}

def review(directory,pin,as_of=None):
    directory=Path(directory);old.identifier(directory.name)
    raw=old.checked_bytes(directory/'manifest.json');old.require(old.sha(raw)==pin,'Manifest pin mismatch');m=json.loads(raw)
    old.require(m['schema']==2 and m['revision']==REVISION and m['version']==directory.name,'Revision mismatch')
    old.require(m['source']=='treasury_2025' and m['source_url']==old.SOURCES['treasury_2025']['url'],'Source mismatch')
    old.require(m['unit']=='percent annualized par yield','Unit mismatch')
    old.require(m['code_sha256']==code_hashes(),'Collector changed; explicit migration review required')
    old.require(m['evaluation_enabled'] is False and m['point_in_time_history'] is False,'Scope mismatch')
    names={'raw.xml','observations.csv','missing.json','parent_manifest.json','registry.json'}
    old.require(set(m['files'])==names and {p.name for p in directory.iterdir()}==names|{'manifest.json'},'File set mismatch')
    files={n:old.checked_bytes(directory/n) for n in names}
    old.require(all(old.sha(b)==m['files'][n] for n,b in files.items()),'File hash mismatch')
    old.require(files['registry.json']==old.encoded(old.REGISTRY),'Registry mismatch')
    parent=json.loads(files['parent_manifest.json'])
    old.require(old.sha(files['parent_manifest.json'])==m['parent_manifest_sha256'],'Parent pin mismatch')
    old.require(parent['schema']==1 and parent['source']=='treasury_2025' and parent['source_url']==m['source_url'],'Parent source mismatch')
    old.require(parent['collector_sha256']==code_hashes()['legacy_verifier'],'Parent collector mismatch')
    old.require(parent['files']['raw.xml']==old.sha(files['raw.xml']),'Parent raw mismatch')
    collected=old.aware(m['collected_at']);derived=old.aware(m['available_at'])
    old.require(m['collected_at']==parent['collected_at'] and collected<=derived<=old.now(),'Availability mismatch')
    cutoff=old.now() if as_of is None else old.aware(as_of);old.require(cutoff<=old.now(),'Future as-of forbidden')
    rows,missing=parse(files['raw.xml'])
    old.require(rows[-1]['date']<=collected.date().isoformat(),'Future observation')
    old.require((m['rows'],m['first_date'],m['last_date'])==(len(rows),rows[0]['date'],rows[-1]['date']),'Coverage mismatch')
    old.require(files['observations.csv']==old.normalized(rows,m['available_at']) and files['missing.json']==old.encoded(missing),'Derived data mismatch')
    return {'manifest':m,'source':old.SOURCES['treasury_2025'],'rows':rows if cutoff>=derived else [],
            'missing':missing,'verified':True,'available':cutoff>=derived,'evaluation_enabled':False}

def derive(parent_directory,parent_pin,store=STORE):
    """Explicit offline derivation of a legacy verified snapshot; no download."""
    parent_directory=Path(parent_directory);parent=old.review(parent_directory,parent_pin)
    old.require(parent['manifest']['source']=='treasury_2025','Treasury only')
    raw=old.checked_bytes(parent_directory/'raw.xml');rows,missing=parse(raw)
    available=old.now().isoformat();version='treasury_v2_'+old.now().strftime('%Y%m%dT%H%M%S%fZ')
    files={'raw.xml':raw,'observations.csv':old.normalized(rows,available),'missing.json':old.encoded(missing),
           'parent_manifest.json':old.checked_bytes(parent_directory/'manifest.json'),'registry.json':old.encoded(old.REGISTRY)}
    old.require(old.sha(files['parent_manifest.json'])==parent_pin,'Parent changed during derivation')
    old.require(old.sha(raw)==parent['manifest']['files']['raw.xml'],'Parent raw changed')
    m={'schema':2,'revision':REVISION,'version':version,'source':'treasury_2025','source_url':old.SOURCES['treasury_2025']['url'],
       'unit':old.SOURCES['treasury_2025']['unit'],'collected_at':parent['manifest']['collected_at'],'available_at':available,
       'parent_manifest_sha256':parent_pin,'code_sha256':code_hashes(),'files':{n:old.sha(b) for n,b in files.items()},
       'rows':len(rows),'first_date':rows[0]['date'],'last_date':rows[-1]['date'],'evaluation_enabled':False,'point_in_time_history':False}
    store=Path(store).absolute();old.require(not any(p.is_symlink() or p.is_junction() for p in (store,*store.parents)),'Linked store forbidden')
    old.require(os.name=='nt','No-replace publication requires Windows');store.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.stage-',dir=store) as temp:
        stage=Path(temp)/version;stage.mkdir()
        for n,b in files.items():
            with (stage/n).open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        old.write_json(stage/'manifest.json',m);pin=old.sha((stage/'manifest.json').read_bytes());review(stage,pin)
        os.rename(stage,store/version)
    old.write_json(store/(version+'.pin.json'),{'version':version,'manifest_sha256':pin})
    return {'version':version,'manifest_sha256':pin}

def catalog(store=STORE):
    result=[]
    for p in sorted(Path(store).glob('*.pin.json')):
        try:
            receipt=json.loads(old.checked_bytes(p));v=old.identifier(receipt['version'])
            old.require(p.name==v+'.pin.json','Receipt mismatch')
            result.append({'version':v,'pin':receipt['manifest_sha256'],'status':'verified',**review(p.parent/v,receipt['manifest_sha256'])})
        except (ValueError,KeyError,TypeError,OSError,ET.ParseError) as exc:
            result.append({'version':p.name,'status':'rejected','error':str(exc),'rows':[]})
    return result
