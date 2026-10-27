"""Verified, immutable adapters. Financial arithmetic stays in frozen V4.1."""
from pathlib import Path
import hashlib, json
import pandas as pd
from research_sr_v4_1.data import load_cache
from research_sr_v4_1.portfolio import SCHEMAS
from research_sr_v4_1.controls import matched_controls, trend_baseline

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
BASE = PROJECT / "research_sr_v4_1"
PERIODS = ("observed_replay", "validation_diagnostic", "training_diagnostic")
SYMBOLS = ("MSFT", "SPY", "QQQ")
PROTOCOL_HASH = "93e311df4885c13823dbf0db705c75dd0c9c6488bf8d8b2d114de237d80c7f6b"

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def integrity():
    protocol_path = BASE / "PORTFOLIO_EXPERIMENT_CONFIG.json"
    protocol = read_json(protocol_path)
    if hashlib.sha256(json.dumps(protocol,indent=2,sort_keys=True).encode()).hexdigest() != PROTOCOL_HASH:
        raise ValueError("Frozen protocol hash mismatch")
    changed = [p for p, h in protocol["source_sha256"].items()
               if not (PROJECT / p).is_file() or digest(PROJECT / p) != h]
    manifest = read_json(ROOT / "out/protected_manifest.json")
    # Include all frozen research artifacts; root documents may be versioned separately.
    for name, h in manifest.items():
        if name.startswith(("research_sr", "tests")):
            p = PROJECT / name
            if not p.is_file() or digest(p) != h:
                changed.append(name)
    if changed:
        raise ValueError("Frozen files changed: " + ", ".join(changed[:8]))
    return protocol, {"protected_files": len(manifest), "changed": [], "protocol_sha256": PROTOCOL_HASH}

class Store:
    def __init__(self):
        self.protocol, self.integrity = integrity()
        self.panel, self.metadata = load_cache()
        self.features = {s: read_json(BASE / "out/features" / f"{s}_causal_features.json") for s in SYMBOLS}
        self.report = read_json(BASE / "out/comparison_results.json")
        self._runs = {}

    def variants(self, period):
        if period not in PERIODS:
            raise ValueError("Unsupported research period")
        return sorted(p.name for p in (BASE / "out" / period).iterdir()
                      if p.is_dir() and (p / "portfolio_metrics.json").is_file())

    def run(self, period="observed_replay", variant="touch"):
        if variant not in self.variants(period):
            raise ValueError("Unsupported frozen experiment")
        key = period, variant
        if key not in self._runs:
            directory = BASE / "out" / period / variant
            tables = {k: pd.read_csv(directory / f"portfolio_{k}.csv") for k in SCHEMAS}
            for k, cols in SCHEMAS.items():
                if list(tables[k].columns) != cols:
                    raise ValueError(f"Invalid {k} table schema")
            tables["metrics"] = read_json(directory / "portfolio_metrics.json")
            tables["audit"] = read_json(directory / "portfolio_audit.json")
            tables["period"], tables["variant"] = period, variant
            tables["dates"] = self.protocol["historical_windows"][period]
            # Stable across future changes; identifies source data + configuration, not future outcomes.
            identity = [PROTOCOL_HASH, period, variant, {s:m["sha256"] for s,m in self.metadata.items()}]
            tables["run_id"] = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            tables["signals"] = self.signals(period, variant)
            self._runs[key] = tables
        return self._runs[key]

    def signals(self, period, variant):
        start, end = self.protocol["historical_windows"][period]
        signals = [{"symbol":s, **x} for s, f in self.features.items() for x in f["signals"]]
        if variant == "trend_baseline":
            signals = trend_baseline(self.panel, self.features)
        elif variant.startswith("matched_"):
            stem, seed = variant[len("matched_"):].rsplit("_", 1)
            anchors = [x for x in signals if x["strategy"] == stem and start <= x["session"] <= end]
            return matched_controls(self.panel, anchors, int(seed))
        else:
            signals = [x for x in signals if x["strategy"] == variant]
        return [x for x in signals if start <= x["session"] <= end]

    def comparison(self, period):
        return pd.DataFrame([{"variant":v, **self.run(period,v)["metrics"]}
                             for v in self.variants(period)])


