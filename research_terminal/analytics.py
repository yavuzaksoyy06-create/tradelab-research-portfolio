"""Presentation ratios only; recorded accounting values remain authoritative."""
import pandas as pd

def risk_view(run):
    equity=run["equity"].copy()
    equity["planned_risk_pct"]=100*equity.planned_open_risk/equity.equity
    positions=run["positions"].merge(equity[["seq","equity"]],on="seq",validate="many_to_one")
    positions["symbol_exposure_pct"]=100*positions.market_value/positions.equity
    return equity,positions

def reconciliation(run):
    equity=run["equity"]
    initial=run["audit"]["config"]["initial_capital"]
    return {
        "cash_plus_positions_error_max":float((equity.cash+equity.market_value-equity.equity).abs().max()),
        "initial_plus_pnl_error_max":float((initial+equity.realized_pnl+equity.unrealized_pnl-equity.equity).abs().max()),
        "recorded_identity_error_max":float(equity.identity_error.abs().max()),
        "final_equity_minus_initial_and_trades":float(equity.iloc[-1].equity-initial-run["trades"].net_pnl.sum())
    }

