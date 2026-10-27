"""Run terminal tests and check frozen-file preservation; save actual evidence."""
import io,json,unittest,hashlib,os
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS']='false'
from datetime import datetime,timezone
from .adapter import ROOT,PROJECT,read_json,integrity
def main():
    import tempfile
    tempfile.tempdir=str(ROOT/"temp")
    os.environ["TEMP"]=str(ROOT/"temp")
    os.environ["TMP"]=str(ROOT/"temp")
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (ROOT/"out/terminal_tests.log").write_text(stream.getvalue(),encoding="utf-8")
    protocol,check=integrity()
    protected=read_json(ROOT/"out/protected_manifest.json")
    changed=[name for name,h in protected.items() if name.startswith(("research_sr","tests"))
        and hashlib.sha256((PROJECT/name).read_bytes()).hexdigest()!=h]
    baseline=read_json(ROOT/"checkpoint/research_sr_v4_1/out/test_summary.json")
    summary={"checked_at":datetime.now(timezone.utc).isoformat(),"terminal_tests":result.testsRun,
        "failures":len(result.failures),"errors":len(result.errors),"skipped":len(result.skipped),
        "baseline_tests":baseline["total_tests"],"baseline_passed":baseline["passed"],
        "total_tests":result.testsRun+baseline["total_tests"],"changed_frozen_files":changed,
        "frozen_files_checked":sum(name.startswith(("research_sr","tests")) for name in protected),
        "passed":result.wasSuccessful() and not changed and baseline["passed"]}
    summary["terminal_source_sha256"] = {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in list(ROOT.glob("*.py"))+list((ROOT/"tests").glob("*.py"))}
    (ROOT/"out/test_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(stream.getvalue())
    print(json.dumps(summary,indent=2))
    return 0 if summary["passed"] else 1
if __name__=="__main__":raise SystemExit(main())

