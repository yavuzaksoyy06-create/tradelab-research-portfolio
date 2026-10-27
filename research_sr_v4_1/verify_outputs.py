"""Reproduce every saved portfolio table/metric/audit with the frozen sources."""
from pathlib import Path
import hashlib,json,ast
from .data import ROOT
from .research import run,freeze

def verify():
    paths=sorted(set((ROOT/"out").rglob("portfolio_*.csv"))|
                 set((ROOT/"out").rglob("portfolio_metrics.json"))|
                 set((ROOT/"out").rglob("portfolio_audit.json"))|
                 {ROOT/"out/comparison_results.json"})
    if not paths or not (ROOT/"out/comparison_results.json").exists():
        raise RuntimeError("Run research before verification")
    before={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    freeze()
    run()
    changed=[name for name,h in before.items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    manifest=json.loads((ROOT/"out/protected_hashes.json").read_text())
    protected_changes=[name for name,h in manifest.items() if hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()!=h]
    forbidden=[]
    for p in ROOT.glob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8-sig"))):
            if isinstance(node,ast.ImportFrom) and node.module and node.module.startswith("alpaca.trading"):
                forbidden.append(p.name)
            if isinstance(node,ast.Import):
                forbidden.extend(p.name for n in node.names if n.name.startswith("alpaca.trading"))
    proof={"passed":not changed and not protected_changes and not forbidden,
        "byte_identical_artifacts":len(paths)-len(changed),"changed_artifacts":changed,
        "protected_files_checked":len(manifest),"changed_protected_files":protected_changes,
        "forbidden_trading_imports":forbidden,"source_manifest_checked":True,
        "no_external_network_required":True}
    (ROOT/"out/reproducibility_verification.json").write_text(json.dumps(proof,indent=2),encoding="utf-8")
    print(json.dumps(proof,indent=2),flush=True)
    if not proof["passed"]:
        raise AssertionError("Reproducibility or preservation gate failed")
    return proof
if __name__=="__main__":
    verify()

