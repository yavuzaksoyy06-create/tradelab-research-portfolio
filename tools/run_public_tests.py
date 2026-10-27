"""Offline selection; excludes historical-cache/checkpoint reproduction suites."""
from pathlib import Path
from datetime import datetime, timezone
import os, subprocess, sys, json, re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

root=Path(__file__).resolve().parents[1]
out=root/'evidence';out.mkdir(exist_ok=True)
results=[]
for package in ('research_macro','research_crypto','research_fx','research_workspace'):
    started=datetime.now(timezone.utc).isoformat()
    proc=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',package+'/tests','-v'],
                        cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',
                        env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1','STREAMLIT_BROWSER_GATHER_USAGE_STATS':'false'},timeout=300)
    log=proc.stdout+'\n'+proc.stderr
    (out/(package+'.log')).write_text(log,encoding='utf-8')
    match=re.search(r'Ran (\d+) tests?',log)
    skipped=re.search(r'skipped=(\d+)',log)
    result={'suite':package,'tests':int(match[1]) if match else 0,'skipped':int(skipped[1]) if skipped else 0,
            'exit_code':proc.returncode,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat()}
    results.append(result);print(json.dumps(result),flush=True)
    if proc.returncode:print(log[-4000:],flush=True)
summary={'scope':'public source selection, no original private data or checkpoints',
         'suites':results,'passed':all(r['exit_code']==0 and r['tests'] for r in results),
         'tests':sum(r['tests'] for r in results),'skipped':sum(r['skipped'] for r in results)}
(out/'public_test_results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
raise SystemExit(0 if summary['passed'] else 1)
