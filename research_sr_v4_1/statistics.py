"""Descriptive paired statistics; no alpha or causal-inference claims."""
import numpy as np
import pandas as pd
from research_sr_v4.research import bootstrap

def daily_pnl(result):
    f=pd.DataFrame(result["equity"])
    close=f[f.phase=="close"].groupby("session",sort=True).equity.last()
    return close.diff().fillna(close.iloc[0]-result["config"]["initial_capital"])

def metrics(result):
    t=pd.DataFrame(result["trades"])
    eq=pd.DataFrame(result["equity"])
    p=t.net_pnl if len(t) else pd.Series(dtype=float)
    daily=daily_pnl(result)
    n_sessions=int(t.session.nunique()) if len(t) else 0
    wins=p[p>0]; losses=p[p<0]
    exposure=float(eq[eq.phase=="after_entries"].exposure_fraction.mean())
    returns=daily/(result["config"]["initial_capital"]+daily.cumsum().shift(1,fill_value=0))
    supported=len(daily)>=60 and n_sessions>=30 and len(t)>=30 and returns.std(ddof=1)>0
    statuses=pd.Series([d["status"] for d in result["decisions"]],dtype=str)
    return {"signals":len(result["decisions"]),"executed_trades":len(t),
        "rejected":int((statuses!="executed").sum()),"decision_reasons":statuses.value_counts().to_dict(),
        "sessions":len(daily),"active_trade_sessions":n_sessions,"net_pnl":float(p.sum()),
        "return_pct":100*(result["final_equity"]/result["config"]["initial_capital"]-1),
        "win_rate":float((p>0).mean()) if len(t) else None,
        "expectancy_usd":float(p.mean()) if len(t) else None,
        "expectancy_r":float(t.r_multiple.mean()) if len(t) else None,
        "average_winner":float(wins.mean()) if len(wins) else None,
        "average_loser":float(losses.mean()) if len(losses) else None,
        "profit_factor":float(wins.sum()/-losses.sum()) if len(losses) else None,
        "max_drawdown_pct":100*float(eq.max_drawdown.max()),
        "max_daily_drawdown_pct":100*float(eq.daily_drawdown.max()),
        "average_open_exposure_fraction":exposure,
        "return_per_average_exposure_pct":100*(result["final_equity"]/result["config"]["initial_capital"]-1)/exposure if exposure else None,
        "sharpe":float(np.sqrt(252)*returns.mean()/returns.std(ddof=1)) if supported else None,
        "sharpe_gate":"60 sessions, 30 trades and 30 active trade sessions; otherwise omitted",
        "daily_mean_pnl_95_block_interval":bootstrap(daily) if n_sessions>=10 and len(daily)>=20 else None,
        "interval_gate":"Descriptive five-session circular blocks; >=20 sessions and >=10 active trade sessions",
        "fees":sum(x["fee"] for x in result["cash"]),
        "spread_slippage":sum(x["execution_cost"] for x in result["cash"]),
        "final_equity":result["final_equity"],
        "max_identity_error":float(eq.identity_error.abs().max()),
        "regimes":{str(k):{"trades":len(g),"net_pnl":float(g.net_pnl.sum())}
                   for k,g in t.groupby("regime")} if len(t) else {}}

def compare(candidate,controls):
    a=daily_pnl(candidate)
    matrix=pd.concat([daily_pnl(x) for x in controls],axis=1)
    if matrix.isna().any().any() or not a.index.equals(matrix.index):
        raise ValueError("Paired sessions must align")
    mean=matrix.mean(axis=1)
    diff=a-mean
    cm=metrics(candidate)
    control_metrics=[metrics(x) for x in controls]
    exp=float(np.mean([x["average_open_exposure_fraction"] for x in control_metrics]))
    active=int(((a!=0)|(mean!=0)).sum())
    return {"claim_type":"descriptive conditional timing comparison; not SR-detection alpha or causal inference",
        "paired_sessions":len(diff),"active_paired_sessions":active,
        "mean_daily_difference_usd":float(diff.mean()),
        "paired_daily_difference_95_block_interval":bootstrap(diff) if active>=10 and len(diff)>=20 else None,
        "candidate_average_exposure":cm["average_open_exposure_fraction"],
        "control_average_exposure":exp,
        "exposure_ratio":exp/cm["average_open_exposure_fraction"] if cm["average_open_exposure_fraction"] else None,
        "candidate_trades":cm["executed_trades"],
        "control_mean_trades":float(np.mean([x["executed_trades"] for x in control_metrics])),
        "control_net_pnl_by_seed":[x["net_pnl"] for x in control_metrics],
        "exposure_matching_status":"ex-ante budgets/horizon and opportunity strata matched; realized exposure NOT forced equal",
        "inference_warning":"Seeds are dependent counterfactuals, not additional independent observations; no multiplicity-adjusted significance claim"}

def buy_hold_reference(panel,start,end,cfg):
    """One shared cash account, 10% initial allocation each, overnight/no risk exits."""
    from .policy import costs
    import math
    c,fee=costs(cfg)
    cash=cfg.initial_capital
    positions={}
    selected={s:f[(f.session>=start)&(f.session<=end)].reset_index(drop=True) for s,f in panel.items()}
    for symbol in cfg.allocation_order:
        if symbol not in selected:
            continue
        entry=selected[symbol].open.iloc[0]*(1+c)
        q=math.floor(cfg.initial_capital*cfg.max_notional_fraction/entry)
        debit=q*entry*(1+fee)
        if debit>cash:
            raise ValueError("Reference cannot borrow")
        cash-=debit
        positions[symbol]=q
    curve=[]
    n=len(next(iter(selected.values())))
    for i in range(n):
        eq=cash+sum(q*selected[s].close.iloc[i] for s,q in positions.items())
        if i==n-1:
            eq=cash+sum(q*selected[s].close.iloc[i]*(1-c)*(1-fee) for s,q in positions.items())
        curve.append(float(eq))
    values=np.r_[cfg.initial_capital,curve]
    return {"net_pnl":curve[-1]-cfg.initial_capital,"return_pct":100*(curve[-1]/cfg.initial_capital-1),
        "max_drawdown_pct":100*float((1-values/np.maximum.accumulate(values)).max()),
        "initial_quantities":positions,
        "policy":"Shared 100k cash, initial 10% each, overnight holdings; no stops/daily lock/rebalance, no dividends/cash yield; separate risk reference"}

