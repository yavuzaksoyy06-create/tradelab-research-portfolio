"""Run original suites in isolated processes to avoid same-named module collisions."""
from pathlib import Path
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent

def run():
    results=[]
    env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}
    for label,folder in [
        ("root","tests"),("v1","research_sr/tests"),("v2","research_sr_v2/tests"),
        ("v3","research_sr_v3/tests"),("v4","research_sr_v4/tests")]:
        cmd=[sys.executable,"-B","-m","unittest","discover","-s",folder,"-v"]
        p=subprocess.run(cmd,cwd=PROJECT,env=env,text=True,capture_output=True)
        output=p.stdout+"\n"+p.stderr
        (ROOT/"out"/f"tests_{label}.log").write_text(output,encoding="utf-8")
        count=re.search(r"Ran (\d+) tests?",output)
        skipped=re.search(r"skipped=(\d+)",output)
        row={"suite":label,"exit_code":p.returncode,"tests":int(count.group(1)) if count else None,
             "skipped":int(skipped.group(1)) if skipped else 0}
        results.append(row)
        print(json.dumps(row),flush=True)
    before=json.loads((ROOT/"out/protected_hashes_before.json").read_text(encoding="utf-8-sig"))
    changed=[name for name,h in before.items()
             if not (PROJECT/name).exists() or hashlib.sha256((PROJECT/name).read_bytes()).hexdigest()!=h]
    report={"suites":results,"protected_files_checked":len(before),"protected_files_changed":changed,
            "total_tests":sum(r["tests"] or 0 for r in results),
            "total_skipped":sum(r["skipped"] for r in results),
            "passed":not changed and all(r["exit_code"]==0 and r["tests"] is not None for r in results)}
    (ROOT/"out/test_summary.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report),flush=True)
    return 0 if report["passed"] else 1

if __name__=="__main__":
    raise SystemExit(run())

