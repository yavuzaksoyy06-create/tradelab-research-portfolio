"""Read-only prospective manifest validation; deliberately contains no evaluator."""
import argparse, json, platform
from pathlib import Path
from datetime import datetime,timezone
from importlib import metadata
import pandas as pd
from .adapter import integrity, digest, read_json, BASE, SYMBOLS, PROTOCOL_HASH
from research_sr_v4_1.data import validate_panel
from research_sr_v4.data import schedule

def dependencies():
    frozen = read_json(BASE / "DEPENDENCIES.json")["versions"]
    return {name: {"expected":version,"actual":metadata.version(name)} for name,version in frozen.items()}

def validate_manifest(manifest_path=None, now=None):
    clock = pd.Timestamp(now or datetime.now(timezone.utc))
    if clock.tzinfo is None:
        raise ValueError("Timezone-aware clock required")
    report = {"checked_at":str(clock),"evaluated":False,"read_only":True,"errors":[],
              "time_gate_passed":False,"data_valid":False,"ready":False}
    try:
        protocol, verified = integrity()
        report["integrity"] = verified
        window = protocol["future_window"]
        report["window"] = window
        report["time_gate_passed"] = clock >= pd.Timestamp(window["complete_after"])
        if not report["time_gate_passed"]:
            report["errors"].append("Future window incomplete: wait until "+window["complete_after"])
        deps = dependencies()
        report["dependencies"] = deps
        if any(d["expected"] != d["actual"] for d in deps.values()):
            report["errors"].append("Frozen dependency versions differ")
        if platform.python_version() != "3.12.10":
            report["errors"].append("Frozen Python version differs from 3.12.10")
        if len(schedule(window["start"],window["end"])) != window["sessions"]:
            report["errors"].append("Frozen calendar session count differs")
        if manifest_path is None:
            report["errors"].append("No versioned dataset manifest supplied")
            return report
        path = Path(manifest_path).resolve()
        manifest = read_json(path)
        if manifest.get("protocol_sha256") != PROTOCOL_HASH:
            raise ValueError("Manifest protocol hash mismatch")
        if manifest.get("source_sha256") != protocol["source_sha256"]:
            raise ValueError("Manifest source hashes mismatch")
        if manifest.get("dependencies") != read_json(BASE/"DEPENDENCIES.json")["versions"]:
            raise ValueError("Manifest dependency versions mismatch")
        version = manifest.get("dataset_version","")
        if not isinstance(version,str) or not version or not all(c.isalnum() or c in "-_." for c in version):
            raise ValueError("Explicit safe dataset_version required")
        if path.parent.name != version:
            raise ValueError("Manifest must reside in its immutable dataset_version directory")
        if set(manifest.get("datasets",{})) != set(SYMBOLS):
            raise ValueError("Exactly MSFT, SPY and QQQ datasets required")
        panel = {}
        for symbol, item in manifest["datasets"].items():
            expected = {"symbol":symbol,"provider":"Alpaca historical","feed":"sip","adjustment":"split",
                        "timeframe":"15min","calendar":"XNYS","start":window["start"],"end":window["end"]}
            if any(item.get(k) != v for k,v in expected.items()):
                raise ValueError(f"{symbol}: explicit SIP/split/provider/calendar/window metadata mismatch")
            p = (path.parent / item["file"]).resolve()
            if p.parent != path.parent or p.suffix.lower() != ".csv":
                raise ValueError(f"{symbol}: CSV must be inside the versioned manifest directory")
            if digest(p) != item["sha256"]:
                raise ValueError(f"{symbol}: dataset SHA256 mismatch")
            panel[symbol] = pd.read_csv(p)
        validated = validate_panel(panel,window["start"],window["end"],now=clock)
        report["data_valid"] = True
        report["datasets"] = {s:{"sessions":int(f.session.nunique()),"bars":len(f),
            "sha256":manifest["datasets"][s]["sha256"]} for s,f in validated.items()}
        report["ready"] = report["time_gate_passed"] and not report["errors"]
    except (ValueError,KeyError,OSError,metadata.PackageNotFoundError) as exc:
        report["errors"].append(str(exc))
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path)
    args=parser.parse_args()
    result=validate_manifest(args.manifest)
    print(json.dumps(result,indent=2))
    return 0 if result["ready"] else 2

if __name__=="__main__":
    raise SystemExit(main())

