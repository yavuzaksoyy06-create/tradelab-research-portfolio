"""Read-only evidence inspection. Missing/stale records never become a pass."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=Path(__file__).resolve().parent/'evidence'
CODE_PACKAGES={'research_macro','research_fx','research_crypto','research_terminal','research_workspace',
               'research_sr','research_sr_v2','research_sr_v3','research_sr_v4','research_sr_v4_1','tests'}

def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def stored_tests(directory=EVIDENCE,root=ROOT):
    directory,root=Path(directory),Path(root).resolve()
    index=directory/'index.json'
    if not index.is_file():return {'status':'not_run','message':'Saklanmış test kaydı yok.','records':[]}
    try:
        entries=json.loads(index.read_text(encoding='utf-8'))['records'];records=[]
        if not entries:return {'status':'not_run','message':'Test listesi boş.','records':[]}
        for item in entries:
            name=item['file']
            if Path(name).name!=name or not name.endswith('.json'):raise ValueError('Geçersiz kanıt yolu')
            path=directory/name
            if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):raise ValueError('Kanıt yolu dışarı çıkıyor')
            if sha256(path)!=item['sha256']:raise ValueError('Test kanıtı hash uyuşmazlığı')
            record=json.loads(path.read_text(encoding='utf-8'));stale=[]
            if not isinstance(record.get('label'),str) or not record['label'].strip():raise ValueError('Test kaydı etiketi eksik')
            recorded=datetime.fromisoformat(record['recorded_at'])
            if recorded.tzinfo is None:raise ValueError('Test kayıt zamanı saat dilimi eksik')
            for name,digest in record['source_sha256'].items():
                rel=Path(name)
                if rel.is_absolute() or '..' in rel.parts or rel.parts[0] not in CODE_PACKAGES or rel.suffix!='.py':
                    raise ValueError('Yalnızca ilgili paketlerin Python kaynakları doğrulanabilir')
                target=(root/rel).resolve()
                if not target.is_relative_to(root):raise ValueError('Kaynak yolu dışarı çıkıyor')
                if not target.is_file() or sha256(target)!=digest:stale.append(name)
            suites=record['suites']
            if not suites or not record['source_sha256']:raise ValueError('Eksik test/kaynak kanıtı')
            for suite in suites.values():
                for key in ('tests','failures','errors','skipped','exit_code'):
                    if type(suite.get(key)) is not int or suite[key]<0:raise ValueError('Eksik veya geçersiz test sayısı')
                if not suite['tests'] or suite['failures']+suite['errors']+suite['skipped']>suite['tests']:
                    raise ValueError('Tutarsız test sayıları')
            passed=all(s['exit_code']==0 and s['failures']==s['errors']==0 for s in suites.values())
            records.append({**record,'status':'stale' if stale else 'passed' if passed else 'failed','changed_sources':stale})
        status='passed' if all(r['status']=='passed' for r in records) else 'stale' if any(r['status']=='stale' for r in records) else 'failed'
        return {'status':status,'records':records,'message':'Yerel hash kontrolü; bağımsız imza veya yayıncı doğrulaması değildir.'}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {'status':'unavailable','message':str(exc),'records':[]}

def protected_artifacts(root=ROOT):
    root=Path(root)
    try:
        manifest=json.loads((root/'research_terminal/out/protected_manifest.json').read_text(encoding='utf-8-sig'))
        protected={n:h for n,h in manifest.items() if n.startswith(('research_sr','tests'))}
        changed=[]
        for name,digest in protected.items():
            p=(root/name).resolve()
            if not p.is_relative_to(root.resolve()):raise ValueError('Koruma yolu geçersiz')
            if not p.is_file() or sha256(p)!=digest:changed.append(name)
        return {'status':'passed' if len(protected)==1393 and not changed else 'failed',
                'checked':len(protected),'changed':changed,'checked_at':datetime.now(timezone.utc).isoformat()}
    except (OSError,ValueError,TypeError) as exc:return {'status':'unavailable','checked':0,'changed':[],'message':str(exc)}

def prospective_restrictions(root=ROOT):
    try:
        p=Path(root)/'research_sr_v4_1/PORTFOLIO_EXPERIMENT_CONFIG.json'
        window=json.loads(p.read_text(encoding='utf-8-sig'))['future_window']
        end=datetime.fromisoformat(window['complete_after'])
        if end.tzinfo is None:raise ValueError('Kapı saat dilimi eksik')
        return {'status':'known','window':window,'time_gate_passed':datetime.now(timezone.utc)>=end,
                'evaluation_enabled':False,'message':'Bu çalışma alanı performans değerlendirmesi çalıştırmaz. Saatin geçmesi tek başına izin değildir.'}
    except (OSError,ValueError,KeyError,TypeError) as exc:
        return {'status':'unavailable','time_gate_passed':False,'evaluation_enabled':False,'message':str(exc)}

def historical_status(root=ROOT):
    files=['research_sr_v4_1/out/comparison_results.json','research_sr_v4_1/PORTFOLIO_EXPERIMENT_CONFIG.json']
    missing=[p for p in files if not (Path(root)/p).is_file()]
    return {'mode':'FROZEN HISTORICAL EQUITY RESEARCH','status':'unavailable' if missing else 'stored',
            'missing':missing,'message':'Saklanmış V4/V4.1 araştırması; canlı veri veya doğrulanmış kârlılık iddiası değil.'}
