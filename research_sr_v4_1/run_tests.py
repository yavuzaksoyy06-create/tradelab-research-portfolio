"""Re-run exact preserved baseline in checkpoint plus new tests in authoritative project."""
from pathlib import Path
import subprocess,sys,json,hashlib,re,os
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
def run():
    old=subprocess.run([sys.executable,"-B","-m","research_sr_v4.run_tests"],cwd=ROOT/"checkpoint",
        capture_output=True,text=True,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
    (ROOT/"out/baseline_latest.log").write_text(old.stdout+"\n"+old.stderr,encoding="utf-8")
    baseline=json.loads((ROOT/"checkpoint/research_sr_v4/out/test_summary.json").read_text())
    new=subprocess.run([sys.executable,"-B","-m","unittest","discover","-s","research_sr_v4_1/tests","-v"],
        cwd=PROJECT,capture_output=True,text=True,env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"})
    log=new.stdout+"\n"+new.stderr
    (ROOT/"out/new_tests.log").write_text(log,encoding="utf-8")
    count=re.search(r"Ran (\d+) tests?",log)
    skip=re.search(r"skipped=(\d+)",log)
    manifest=json.loads((ROOT/"out/protected_hashes.json").read_text())
    changed=[str(p) for p,h in manifest.items() if not (PROJECT/p).exists() or hashlib.sha256((PROJECT/p).read_bytes()).hexdigest()!=h]
    source_diff=[p for p in manifest if p.endswith(".py") and
                 hashlib.sha256((ROOT/"checkpoint"/p).read_bytes()).hexdigest()!=manifest[p]]
    summary={"baseline_tests":baseline["total_tests"],"baseline_suites":baseline["suites"],
        "baseline_exit_code":old.returncode,"new_tests":int(count.group(1)) if count else 0,
        "new_exit_code":new.returncode,"new_skipped":int(skip.group(1)) if skip else 0,
        "protected_files":len(manifest),"changed_protected_files":changed,"checkpoint_source_differences":source_diff}
    summary["total_tests"]=summary["baseline_tests"]+summary["new_tests"]
    summary["passed"]=old.returncode==0 and new.returncode==0 and not changed and not source_diff and count is not None
    (ROOT/"out/test_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return 0 if summary["passed"] else 1
if __name__=="__main__":
    raise SystemExit(run())

