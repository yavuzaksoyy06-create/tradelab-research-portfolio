"""Pure financial calculations shared by portfolio and reference experiments."""
from dataclasses import dataclass
import math
from research_sr_v4.execution import ExecutionConfig

@dataclass(frozen=True)
class PortfolioConfig(ExecutionConfig):
    aggregate_exposure_cap: float = .30
    max_positions: int = 3
    allocation_order: tuple[str,...] = ("MSFT","SPY","QQQ")
    version: str = "4.1.0"

    def __post_init__(self):
        # V4 validates only its numeric fields; subclass adds explicit nonnumeric settings.
        base={k:getattr(self,k) for k in ExecutionConfig.__dataclass_fields__}
        ExecutionConfig(**base)
        if not math.isfinite(self.aggregate_exposure_cap) or not 0<self.aggregate_exposure_cap<=.30:
            raise ValueError("Aggregate entry exposure cap must be in (0, .30]")
        if type(self.max_positions) is not int or not 1<=self.max_positions<=3:
            raise ValueError("Position count must be 1..3")
        if tuple(self.allocation_order)!=("MSFT","SPY","QQQ"):
            raise ValueError("Version 4.1 fixes an explicit MSFT, SPY, QQQ priority")

def costs(cfg):
    return (cfg.half_spread_bps+cfg.slippage_bps)/10000,cfg.fee_bps/10000

def plan_entry(raw_open, signal, equity, cash, gross, cfg):
    """Size from current observable marks; never high/low/close of entry bar."""
    c,f=costs(cfg)
    stop=signal["lower"]-cfg.stop_buffer_atr*signal["atr"]
    distance=max(signal["lower"]-raw_open,raw_open-signal["upper"],0)
    entry=raw_open*(1+c)
    unit_risk=entry*(1+f)-stop*(1-c)*(1-f)
    if stop<=0 or raw_open<=stop:
        return None,"entry_open_at_or_below_stop"
    if distance>cfg.max_distance_atr*signal["atr"]:
        return None,"entry_too_far"
    if unit_risk<cfg.min_risk_atr*signal["atr"]:
        return None,"risk_too_small"
    if equity<=0 or cash<0:
        return None,"insolvent"
    # Post-fill mark equity loses spread/slippage and entry fee immediately.
    drag=entry*(1+f)-raw_open
    limits={"risk":equity*cfg.risk_fraction/unit_risk,
            "symbol_notional":equity*cfg.max_notional_fraction/entry,
            "cash":cash/(entry*(1+f)),
            "aggregate_exposure":max(0,cfg.aggregate_exposure_cap*equity-gross)/
                                 (raw_open+cfg.aggregate_exposure_cap*drag)}
    binding=min(limits,key=limits.get)
    qty=math.floor(limits[binding]+1e-12)
    if qty<1:
        return None,{"cash":"insufficient_cash","aggregate_exposure":"aggregate_exposure_cap",
                     "symbol_notional":"symbol_notional_cap","risk":"risk_budget"}[binding]
    target=(entry*(1+f)+cfg.reward_risk*unit_risk)/((1-c)*(1-f))
    return {"entry_price":entry,"raw_entry":raw_open,"quantity":qty,
            "stop":stop,"target":target,"planned_risk":qty*unit_risk,
            "entry_fee":qty*entry*f,"entry_debit":qty*entry*(1+f),
            "entry_cost":qty*(entry-raw_open)+qty*entry*f,
            "binding_constraint":binding,"equity_at_entry":equity,
            "risk_budget":equity*cfg.risk_fraction},None

def open_exit(position, raw_open, liquidate):
    if liquidate:
        return raw_open,"daily_drawdown_next_open"
    if raw_open<=position["stop"]:
        return raw_open,"gap_stop"
    if raw_open>=position["target"]:
        return raw_open,"gap_target_open"
    return None,None

def bar_exit(position, bar, cfg):
    stop=bar.low<=position["stop"]
    target=bar.high>=position["target"]
    if stop:
        return position["stop"],"stop",False,target
    if target:
        return position["target"],"target",False,False
    if bar.bar_end==bar.session_close:
        return bar.close,"exchange_session_close",True,False
    if position["bars_held"]>=cfg.horizon_bars:
        return bar.close,"horizon_close",True,False
    return None,None,True,False

