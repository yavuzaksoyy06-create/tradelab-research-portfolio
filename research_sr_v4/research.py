"""Frozen, chronological research protocol. No optimization or automatic winner selection."""
from dataclasses import asdict, replace
from pathlib import Path
import hashlib
import json
import math
import subprocess
import sys
import numpy as np
import pandas as pd
from .data import fetch
from .causal import build_features, FeatureConfig
from .execution import simulate, ExecutionConfig

ROOT=Path(__file__).resolve().parent
STRATEGIES=["touch","rejection","trend_filtered","trend_baseline","timed_control"]
PROTOCOL={
    "version":"4.0.0","symbols":["MSFT","SPY","QQQ"],"start":"2026-04-01","end":"2026-10-22",
    "feed":"sip","adjustment":"split","train_sessions":70,"validation_sessions":30,
    "test_policy":"All remaining sessions; no parameter selection from any returns",
    "walk_forward_test_block_sessions":14,"features":asdict(FeatureConfig()),
    "execution":asdict(ExecutionConfig()),"seed":20261023,
    "cost_sensitivity_bps_per_side":[0,3,6,10],"width_sensitivity_atr":[.15,.20,.30],
    "sensitivity_scope":"training_and_validation_only",
    "baseline_policy":"Timed control every fourth completed bar, same sizing/horizon/costs; exposure is measured, not forced equal",
    "universe_policy":"All three symbols, including failures; independent 100k accounts, not an executable combined portfolio",
    "bootstrap":"1000 circular moving-block resamples of five session P&Ls; descriptive 95% interval",
}
def freeze_protocol():
    path=ROOT/"EXPERIMENT_CONFIG.json"
    text=json.dumps(PROTOCOL,indent=2,sort_keys=True)+"\n"
    if path.exists() and path.read_text(encoding="utf-8-sig")!=text:
        raise RuntimeError("Protocol exists with different settings; version explicitly before changing")
    path.write_text(text,encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()

def controls(bars, features):
    result=[]
    for i,snap in enumerate(features["snapshots"]):
        if i<26*5 or i%4!=0:
            continue
        row=bars.iloc[i]
        if snap["atr"]<=0:
            continue
        base={"signal_index":i,"known_at":str(row.bar_end),"session":row.session,
            "zone_id":"CONTROL","lower":row.close-.9*snap["atr"],"upper":row.close+.1*snap["atr"],
            "atr":snap["atr"],"regime":snap["regime"],"collision":False}
        result.append({**base,"strategy":"timed_control"})
        if snap["regime"]=="uptrend":
            result.append({**base,"strategy":"trend_baseline"})
    return result

def daily_pnl(result):
    frame=pd.DataFrame(result["equity"])
    if frame.empty:
        return pd.Series(dtype=float)
    daily=frame.groupby("session",sort=True).equity.last()
    return daily.diff().fillna(daily.iloc[0]-result["config"]["initial_capital"])

def bootstrap(values,seed=20261023,replicates=1000):
    x=np.asarray(values,dtype=float)
    if len(x)<20:
        return None
    rng=np.random.default_rng(seed)
    n=len(x)
    means=[]
    for _ in range(replicates):
        starts=rng.integers(0,n,math.ceil(n/5))
        sample=x[((starts[:,None]+np.arange(5))%n).ravel()[:n]]
        means.append(float(sample.mean()))
    return [float(v) for v in np.quantile(means,[.025,.975])]

def metrics(result):
    t=pd.DataFrame(result["trades"])
    curve=pd.DataFrame(result["equity"])
    initial=result["config"]["initial_capital"]
    daily=daily_pnl(result)
    pnl=t.net_pnl if len(t) else pd.Series(dtype=float)
    wins=pnl[pnl>0]
    losses=pnl[pnl<0]
    vals=np.r_[initial,curve.equity.to_numpy()] if len(curve) else np.array([initial])
    dd=vals/np.maximum.accumulate(vals)-1
    exposure=float(curve.open_exposure_fraction.mean()) if len(curve) else 0
    previous_equity=initial+daily.cumsum().shift(1,fill_value=0)
    returns=daily/previous_equity
    meaningful=len(daily)>=60 and len(t)>=30 and returns.std(ddof=1)>0
    downside=np.sqrt(np.mean(np.minimum(returns,0)**2)) if len(returns) else 0
    return {"signals":len(result["events"]),"executed":len(t),
        "rejected":sum(e["status"]!="executed" for e in result["events"]),
        "rejection_reasons":dict(pd.Series([e["status"] for e in result["events"] if e["status"]!="executed"],dtype=str).value_counts().items()),
        "independent_trade_sessions":int(t.session.nunique()) if len(t) else 0,
        "net_pnl":float(pnl.sum()),"return_pct":100*(result["final_equity"]/initial-1),
        "win_rate":float((pnl>0).mean()) if len(t) else None,
        "average_winner":float(wins.mean()) if len(wins) else None,
        "average_loser":float(losses.mean()) if len(losses) else None,
        "expectancy_usd":float(pnl.mean()) if len(t) else None,
        "expectancy_r":float(t.r_multiple.mean()) if len(t) else None,
        "profit_factor":float(wins.sum()/-losses.sum()) if len(losses) else None,
        "max_drawdown_pct":100*float(dd.min()),"average_open_exposure":exposure,
        "occupied_bar_fraction":float(curve.occupied_bar.mean()) if len(curve) else 0,
        "return_per_average_exposure_pct":100*(result["final_equity"]/initial-1)/exposure if exposure else None,
        "sharpe_daily":float(np.sqrt(252)*returns.mean()/returns.std(ddof=1)) if meaningful else None,
        "sortino_daily":float(np.sqrt(252)*returns.mean()/downside) if meaningful and downside>0 else None,
        "ratio_note":"Not annualized where omitted: require >=60 sessions and >=30 trades; cash earns zero",
        "fees":float(t.fees.sum()) if len(t) else 0,
        "spread_slippage_cost":float(t.spread_slippage_cost.sum()) if len(t) else 0,
        "mean_daily_pnl_block_bootstrap_95":bootstrap(daily),
        "regimes":{str(k):{"trades":len(g),"net_pnl":float(g.net_pnl.sum())} for k,g in t.groupby("regime")} if len(t) else {},
        "intrabar_excursion_ambiguous_trades":int(t.mfe_exact.isna().sum()) if len(t) else 0}

def buy_hold(bars,start,end,cfg=ExecutionConfig()):
    f=bars[(bars.session>=start)&(bars.session<=end)]
    cost=(cfg.half_spread_bps+cfg.slippage_bps)/10000
    fee=cfg.fee_bps/10000
    entry=f.open.iloc[0]*(1+cost)
    qty=math.floor(cfg.initial_capital*cfg.max_notional_fraction/entry)
    exit_price=f.close.iloc[-1]*(1-cost)
    pnl=qty*(exit_price*(1-fee)-entry*(1+fee))
    return {"net_pnl":float(pnl),"quantity":qty,"return_pct":pnl/cfg.initial_capital*100,
        "note":"10% initial-capital allocation; holds overnight; no stop; split-adjusted price-only, excludes dividends; different risk"}

def run():
    protocol_hash=freeze_protocol()
    import importlib.metadata
    source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in ROOT.glob("*.py")}
    versions={name:importlib.metadata.version(name) for name in
              ["pandas","numpy","alpaca-py","exchange-calendars","matplotlib"]}
    report={"protocol_sha256":protocol_hash,"source_sha256":source_hashes,
            "python":sys.version,"dependencies":versions,"symbols":{},"failures":{}}
    for symbol in PROTOCOL["symbols"]:
        print(f"Research {symbol}: loading verified cache",flush=True)
        try:
            bars,meta=fetch(symbol,PROTOCOL["start"],PROTOCOL["end"])
            features=build_features(bars)
            signals=features["signals"]+controls(bars,features)
            sessions=sorted(bars.session.unique())
            if len(sessions)<120:
                raise ValueError("At least 120 complete sessions required by frozen protocol")
            splits={"train":(sessions[0],sessions[69]),"validation":(sessions[70],sessions[99]),
                    "test":(sessions[100],sessions[-1])}
            out=ROOT/"out"/symbol
            out.mkdir(exist_ok=True)
            (out/"causal_features.json").write_text(json.dumps(features,allow_nan=False),encoding="utf-8")
            results={}
            test_runs={}
            for part,(start,end) in splits.items():
                results[part]={"dates":[start,end],"strategies":{},"buy_hold":buy_hold(bars,start,end)}
                for strategy in STRATEGIES:
                    run_result=simulate(bars,[s for s in signals if s["strategy"]==strategy],start=start,end=end)
                    results[part]["strategies"][strategy]=metrics(run_result)
                    prefix=out/f"{part}_{strategy}"
                    for table in ["events","trades","equity"]:
                        pd.DataFrame(run_result[table]).to_csv(str(prefix)+f"_{table}.csv",index=False)
                    if part=="test":
                        test_runs[strategy]=run_result
            paired={}
            control=daily_pnl(test_runs["timed_control"])
            for strategy in STRATEGIES[:3]:
                diff=daily_pnl(test_runs[strategy])-control
                paired[strategy]={"mean_daily_difference_usd":float(diff.mean()),
                    "block_bootstrap_95":bootstrap(diff),
                    "note":"Risk settings matched; actual exposure differs; not proof of equal-exposure alpha"}
            folds=[]
            for a in range(100,len(sessions),14):
                b=min(a+13,len(sessions)-1)
                folds.append({"history_through":sessions[a-1],"test_dates":[sessions[a],sessions[b]],
                    "metrics":{s:metrics(simulate(bars,[x for x in signals if x["strategy"]==s],
                        start=sessions[a],end=sessions[b])) for s in STRATEGIES}})
            sensitivity=[]
            for width in PROTOCOL["width_sensitivity_atr"]:
                alternative=features if width==.20 else build_features(bars,replace(FeatureConfig(),zone_half_width_atr=width))
                sig=alternative["signals"]
                for cost in PROTOCOL["cost_sensitivity_bps_per_side"]:
                    cfg=replace(ExecutionConfig(),half_spread_bps=0,slippage_bps=cost)
                    for strategy in STRATEGIES[:3]:
                        r=simulate(bars,[s for s in sig if s["strategy"]==strategy],cfg,
                                   start=sessions[70],end=sessions[99])
                        sensitivity.append({"zone_half_width_atr":width,"cost_bps_per_side":cost,
                            "strategy":strategy,"scope":"validation_only",**metrics(r)})
            report["symbols"][symbol]={"metadata":meta,"splits":results,"test_walk_forward":folds,
                "paired_test_vs_timed_control":paired,"validation_sensitivity":sensitivity}
            plot_equity(test_runs,out)
            print(f"Research {symbol}: completed all fixed splits and sensitivity runs",flush=True)
        except Exception as exc:
            report["failures"][symbol]={"type":type(exc).__name__,"detail":str(exc) if isinstance(exc,(ValueError,AssertionError)) else "See local diagnostics; no API details logged"}
            print(f"Research {symbol}: failed ({type(exc).__name__})",flush=True)
    (ROOT/"out/research_results.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    return report

def plot_equity(runs,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(12,5))
    for name,result in runs.items():
        daily=daily_pnl(result).cumsum()
        ax.plot(pd.to_datetime(daily.index),daily,label=name)
    ax.set(title=f"{out.name}: fixed-protocol held-out test, net cumulative P&L",
           ylabel="Hypothetical USD, independent 100k account",xlabel="Session")
    ax.axhline(0,color="black",lw=.7)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out/"test_equity.png",dpi=140)
    plt.close(fig)

if __name__=="__main__":
    run()

