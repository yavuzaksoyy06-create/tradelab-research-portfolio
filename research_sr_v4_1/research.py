"""Versioned historical replay and a gated, future-only evaluation specification."""
from dataclasses import asdict,replace
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
from research_sr_v4.causal import FeatureConfig
from research_sr_v4.data import schedule
from .data import ROOT,V4,load_cache,features_and_signals
from .policy import PortfolioConfig
from .portfolio import simulate,write_tables,SCHEMAS
from .controls import matched_controls,trend_baseline,SEEDS
from .statistics import metrics,compare,buy_hold_reference

WINDOWS={"training_diagnostic":("2026-04-01","2026-07-13"),
         "validation_diagnostic":("2026-07-14","2026-08-24"),
         "observed_replay":("2026-08-25","2026-10-22")}
CANDIDATES=("touch","rejection","trend_filtered")
PRODUCTION=("__init__.py","data.py","policy.py","portfolio.py","controls.py","statistics.py","research.py")

def source_hashes():
    paths=[ROOT/n for n in PRODUCTION]+[V4/n for n in ("__init__.py","data.py","causal.py","execution.py","research.py")]
    return {str(p.relative_to(ROOT.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

def freeze():
    future=schedule("2026-10-26","2027-06-01").iloc[:60]
    protocol={"version":"4.1.0","portfolio":asdict(PortfolioConfig()),"features":asdict(FeatureConfig()),
        "historical_windows":WINDOWS,"historical_claim":"Previously inspected; accounting and descriptive diagnostics only",
        "control_seeds":SEEDS,
        "control":"One causal delay 0..3 bars per anchor, same session/hour bucket, translated percentage geometry; report realized exposure mismatch",
        "allocation":"MSFT then SPY then QQQ; exits at open before entries; intrabar proceeds unavailable for opening allocations",
        "cost_sensitivity_bps_per_side":[0,3,6,10],
        "statistics":"paired daily difference versus mean of five seeds; five-session block bootstrap, 1000 resamples; 20 sessions and 10 active paired sessions minimum; no alpha claims",
        "future_window":{"start":str(future.index[0].date()),"end":str(future.index[-1].date()),
                         "sessions":60,"complete_after":str(future.close.iloc[-1]+pd.Timedelta(minutes=15))},
        "future_gates":"All three complete SIP/split datasets and matching frozen source; never evaluate an unfinished session",
        "source_sha256":source_hashes()}
    encoded=json.dumps(protocol,indent=2,sort_keys=True)
    path=ROOT/"PORTFOLIO_EXPERIMENT_CONFIG.json"
    if path.exists():
        if json.loads(path.read_text())!=json.loads(encoded):
            raise RuntimeError("Frozen protocol/source differs. Preserve old experiment and version the change explicitly.")
    else:
        path.write_text(encoded,encoding="utf-8")
        (ROOT/"out/protocol_freeze_time.json").write_text(json.dumps({"frozen_utc":datetime.now(timezone.utc).isoformat(),
            "protocol_sha256":hashlib.sha256(encoded.encode()).hexdigest()},indent=2),encoding="utf-8")
    return protocol

def future_readiness(protocol,now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError("Clock must be timezone-aware")
    ready=now>=pd.Timestamp(protocol["future_window"]["complete_after"])
    return {"time_gate_passed":ready,"new_data_loaded":False,"evaluated":False,
            "reason":"Data ingestion/manifest review still required" if ready else "Frozen future 60-session window is not complete",
            "window":protocol["future_window"]}

def choose(signals,start,end,strategy=None):
    return [s for s in signals if start<=s["session"]<=end and (strategy is None or s["strategy"]==strategy)]

def save(result,directory,metadata,protocol):
    result["audit"].update({"dataset_sha256":{s:m["sha256"] for s,m in metadata.items()},
        "source_sha256":protocol["source_sha256"],"evaluation_kind":"already-observed historical replay",
        "version":protocol["version"]})
    write_tables(result,directory)
    m=metrics(result)
    (Path(directory)/"portfolio_metrics.json").write_text(json.dumps(m,indent=2,sort_keys=True,allow_nan=False),encoding="utf-8")
    return m

def run():
    protocol=freeze()
    panel,metadata=load_cache()
    features,signals=features_and_signals(panel)
    report={"version":"4.1.0","dataset_metadata":metadata,"protocol":protocol,
            "future_evaluation":future_readiness(protocol),"windows":{}}
    for symbol,f in features.items():
        p=ROOT/"out/features"; p.mkdir(exist_ok=True)
        (p/f"{symbol}_causal_features.json").write_text(json.dumps(f,allow_nan=False),encoding="utf-8")
    trend=trend_baseline(panel,features)
    replay_runs={}
    for window,(start,end) in WINDOWS.items():
        print(f"Portfolio {window}: {start} to {end}",flush=True)
        row={"dates":[start,end],"candidates":{},"matched_comparisons":{},"matched_seed_metrics":{}}
        for strategy in CANDIDATES:
            anchors=choose(signals,start,end,strategy)
            r=simulate(panel,anchors,start=start,end=end)
            row["candidates"][strategy]=save(r,ROOT/"out"/window/strategy,metadata,protocol)
            controls=[]
            for seed in SEEDS:
                ss=matched_controls(panel,anchors,seed)
                control=simulate(panel,ss,start=start,end=end)
                controls.append(control)
                m=save(control,ROOT/"out"/window/f"matched_{strategy}_{seed}",metadata,protocol)
                row["matched_seed_metrics"][f"{strategy}_{seed}"]=m
            row["matched_comparisons"][strategy]=compare(r,controls)
            if window=="observed_replay":
                replay_runs[strategy]=r
        baseline=simulate(panel,choose(trend,start,end),start=start,end=end)
        row["trend_baseline"]=save(baseline,ROOT/"out"/window/"trend_baseline",metadata,protocol)
        row["buy_hold_reference"]=buy_hold_reference(panel,start,end,PortfolioConfig())
        report["windows"][window]=row
    # Cost sensitivity is descriptive on the old validation interval, never selection.
    report["validation_cost_sensitivity"]=[]
    start,end=WINDOWS["validation_diagnostic"]
    for cost in (0,3,6,10):
        cfg=replace(PortfolioConfig(),half_spread_bps=0,slippage_bps=cost)
        for strategy in CANDIDATES:
            r=simulate(panel,choose(signals,start,end,strategy),cfg,start,end)
            report["validation_cost_sensitivity"].append({"cost_bps_per_side":cost,"strategy":strategy,**metrics(r)})
    save(replay_runs["touch"],ROOT/"out",metadata,protocol)
    plot(replay_runs)
    (ROOT/"out/comparison_results.json").write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False),encoding="utf-8")
    print("Portfolio research finished; no new out-of-sample data evaluated.",flush=True)
    return report

def plot(runs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(12,10),sharex=True)
    for strategy,r in runs.items():
        e=pd.DataFrame(r["equity"]); close=e[e.phase=="close"]
        stamp=pd.to_datetime(close.timestamp,utc=True)
        axes[0].plot(stamp,close.equity-r["config"]["initial_capital"],label=strategy)
        axes[1].plot(stamp,close.exposure_fraction*100,label=strategy)
        axes[2].plot(stamp,close.daily_drawdown*100,label=strategy)
    for ax in axes: ax.legend(); ax.grid(alpha=.2)
    axes[0].set(ylabel="Net hypothetical USD",title="Shared 100k portfolio — observed historical replay, NOT new holdout")
    axes[1].set(ylabel="Close exposure %")
    axes[2].set(ylabel="Observed daily drawdown %",xlabel="Date (UTC)")
    fig.tight_layout(); fig.savefig(ROOT/"out/portfolio_overview.png",dpi=140); plt.close(fig)

if __name__=="__main__":
    run()

