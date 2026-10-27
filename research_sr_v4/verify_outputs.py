from pathlib import Path
import hashlib,json,ast
import pandas as pd
from research_sr_v4.data import fetch
from research_sr_v4.causal import build_features
from research_sr_v4.research import controls,STRATEGIES
from research_sr_v4.execution import simulate
ROOT=Path(__file__).resolve().parent
r=json.loads((ROOT/"out/research_results.json").read_text())
checks=[]
for name,expected in r["source_sha256"].items():
    assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, name

for symbol,detail in r["symbols"].items():
    bars,meta=fetch(symbol,"2026-04-01","2026-10-22")
    f=build_features(bars)
    sig=f["signals"]+controls(bars,f)
    start,end=detail["splits"]["test"]["dates"]
    for strategy in STRATEGIES:
        result=simulate(bars,[s for s in sig if s["strategy"]==strategy],start=start,end=end)
        for table in ("events","trades","equity"):
            original=(ROOT/"out"/symbol/f"test_{strategy}_{table}.csv").read_bytes()
            generated=pd.DataFrame(result[table]).to_csv(index=False).encode("utf-8")
            assert original==generated,(symbol,strategy,table)
            checks.append(f"{symbol}/{strategy}/{table}")
    original=pd.read_csv(ROOT.parent/"research_sr_v3/out/MSFT_12_sessions_ohlcv.csv") if symbol=="MSFT" else None
    if original is not None:
        original["timestamp"]=pd.to_datetime(original.timestamp,utc=True)
        joined=original.merge(bars,on="timestamp",suffixes=("_v3","_refetch"))
        delta={c:float((joined[c+"_v3"]-joined[c+"_refetch"]).abs().max()) for c in ["open","high","low","close","volume"]}
        comparison={"overlapping_bars":len(joined),"max_abs_difference":delta}
imports=[]
for name in ["__init__.py","data.py","causal.py","execution.py","research.py"]:
    tree=ast.parse((ROOT/name).read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node,ast.Import):
            imports.extend(n.name for n in node.names)
assert not any("alpaca.trading" in name for name in imports)
proof={"all_passed":True,"byte_identical_csv_tables":len(checks),"checks":checks,
       "source_hashes_verified":len(r["source_sha256"]),"v3_vs_new_sip_refetch":comparison,
       "production_imports_have_no_broker_trading_module":True}
(ROOT/"out/reproducibility_verification.json").write_text(json.dumps(proof,indent=2),encoding="utf-8")
print(json.dumps(proof,indent=2))



