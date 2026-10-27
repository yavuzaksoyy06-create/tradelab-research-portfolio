"""TradeLab S/R v3 — deterministic, historical, READ-ONLY execution research.

This module has no broker API imports. No orders are created or submitted.
No claim of market fill precision is made: 15m bars hide intrabar ordering.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import time
from typing import Any
import math
import pandas as pd

BAR = pd.Timedelta(minutes=15)


@dataclass(frozen=True)
class SimConfig:
    starting_equity: float = 100_000.0
    risk_fraction: float = 0.005
    max_notional_fraction: float = 0.10
    max_daily_loss_fraction: float = 0.02
    stop_buffer_atr: float = 0.10
    min_stop_distance_atr: float = 0.05
    reward_risk: float = 2.0
    max_entry_distance_atr: float = 0.50
    horizon_bars: int = 4
    half_spread_bps: float = 1.0
    slippage_bps: float = 2.0
    fee_bps_per_side: float = 0.0
    intrabar_policy: str = 'adverse_first'  # adverse_first | exclude
    allow_short_research: bool = False

    def check(self) -> None:
        if not (self.starting_equity > 0 and 0 < self.risk_fraction <= 0.05 and
                0 < self.max_notional_fraction <= 1 and 0 < self.max_daily_loss_fraction <= 0.20 and 0 <= self.stop_buffer_atr <= 2 and
                0 <= self.min_stop_distance_atr <= 2 and self.reward_risk > 0 and
                self.max_entry_distance_atr >= 0 and self.horizon_bars > 0):
            raise ValueError('Invalid simulator capital, risk, stop, reward or horizon settings')
        if any(x < 0 or not math.isfinite(x) for x in
               (self.half_spread_bps, self.slippage_bps, self.fee_bps_per_side)):
            raise ValueError('Invalid execution cost')
        if self.half_spread_bps + self.slippage_bps >= 250:
            raise ValueError('Extreme execution cost is unsupported')
        if self.intrabar_policy not in ('adverse_first', 'exclude'):
            raise ValueError('Invalid intrabar collision policy')


EVENT_COLUMNS = ['event_id', 'zone_id', 'kind', 'signal_bar_start', 'signal_known_at',
                 'entry_bar_start', 'entry_open', 'zone_lower', 'zone_upper',
                 'status', 'reason', 'linked_trade_id']
TRADE_COLUMNS = ['trade_id', 'event_id', 'zone_id', 'side', 'signal_bar_start',
                 'signal_known_at', 'entry_bar_start', 'entry_price', 'planned_stop',
                 'planned_target', 'quantity', 'initial_planned_risk_usd',
                 'exit_bar_start', 'exit_known_by', 'exit_price', 'exit_reason',
                 'ambiguous_intrabar', 'bars_held', 'gross_pnl', 'fees_usd',
                 'net_pnl', 'net_r', 'mfe_per_share', 'mae_per_share',
                 'equity_after']


def _validate_frame(df: pd.DataFrame) -> pd.DataFrame:
    required = ('timestamp', 'open', 'high', 'low', 'close', 'session')
    missing = [x for x in required if x not in df]
    if missing:
        raise ValueError('Missing simulator bars: ' + repr(missing))
    v = df.copy()
    v['timestamp'] = pd.to_datetime(v['timestamp'], utc=True, errors='raise')
    for col in ('open', 'high', 'low', 'close'):
        v[col] = pd.to_numeric(v[col], errors='raise')
    if v['timestamp'].isna().any() or v['timestamp'].duplicated().any():
        raise ValueError('Missing or duplicated bar timestamps')
    if v[['open', 'high', 'low', 'close']].isna().any().any():
        raise ValueError('Non-numeric OHLC')
    if not all(math.isfinite(x) and x > 0 for x in v[['open', 'high', 'low', 'close']].to_numpy().ravel()):
        raise ValueError('Non-finite or nonpositive prices')
    if ((v.high < v[['open','close','low']].max(axis=1)) |
        (v.low > v[['open','close','high']].min(axis=1))).any():
        raise ValueError('Invalid OHLC range')
    v = v.sort_values('timestamp').reset_index(drop=True)
    # Session boundaries are supplied by data preparation; no cross-session simulation.
    return v


def _touch_events(day: pd.DataFrame, zones: list[dict], gap_bars: int = 4) -> dict[int,list[dict]]:
    """Group episodes by their first touch bar; multiple zones on one bar collide."""
    grouped: dict[int,list[dict]] = {}
    for z in zones:
        touching = (day.low <= float(z['upper'])) & (day.high >= float(z['lower']))
        last_touch = -(gap_bars+2)
        for i, touching_now in enumerate(touching):
            if touching_now:
                if i - last_touch >= gap_bars+1:
                    grouped.setdefault(i, []).append(z)
                last_touch = i
    return grouped


def _near_zone(price: float, z: dict, atr: float, tolerance: float) -> bool:
    return (float(z['lower'])-tolerance*atr <= price <=
            float(z['upper'])+tolerance*atr)


def _execution(bars: pd.DataFrame, start_idx: int, side: str,
               entry: float, stop: float, target: float, cfg: SimConfig):
    """Bar-ordered stop/target test. An ambiguous double touch is never scored as a win."""
    direction = 1 if side == 'long' else -1
    extremes = []
    status, exit_base, exit_i, ambiguity = None, None, None, False
    for i in range(start_idx, min(len(bars), start_idx+cfg.horizon_bars)):
        bar = bars.iloc[i]
        # Data loss invalidates all supposed fill-based conclusions.
        if i > start_idx and bar.timestamp - bars.iloc[i-1].timestamp != BAR:
            return {'status':'invalid_data_gap', 'exit':None, 'idx':None,
                    'ambiguous':False, 'mfe':None, 'mae':None}
        op, hi, lo = float(bar.open), float(bar.high), float(bar.low)
        extremes.append((hi, lo))
        if direction == 1:
            if op <= stop:
                status, exit_base, exit_i = 'stop_gap', op, i
            elif op >= target:
                status, exit_base, exit_i = 'target_gap_at_limit', target, i
            else:
                hit_stop, hit_target = lo <= stop, hi >= target
                if hit_stop and hit_target:
                    ambiguity = True
                    if cfg.intrabar_policy == 'exclude':
                        return {'status':'ambiguous_unresolved','exit':None,'idx':None,
                                'ambiguous':True,'mfe':None,'mae':None}
                    status, exit_base, exit_i = 'stop_ambiguous_adverse_first', stop, i
                elif hit_stop:
                    status, exit_base, exit_i = 'stop', stop, i
                elif hit_target:
                    status, exit_base, exit_i = 'target', target, i
        else:
            if op >= stop:
                status, exit_base, exit_i = 'stop_gap', op, i
            elif op <= target:
                status, exit_base, exit_i = 'target_gap_at_limit', target, i
            else:
                hit_stop, hit_target = hi >= stop, lo <= target
                if hit_stop and hit_target:
                    ambiguity = True
                    if cfg.intrabar_policy == 'exclude':
                        return {'status':'ambiguous_unresolved','exit':None,'idx':None,
                                'ambiguous':True,'mfe':None,'mae':None}
                    status, exit_base, exit_i = 'stop_ambiguous_adverse_first', stop, i
                elif hit_stop:
                    status, exit_base, exit_i = 'stop', stop, i
                elif hit_target:
                    status, exit_base, exit_i = 'target', target, i
        if status is not None:
            break
    if status is None:
        exit_i = min(len(bars)-1, start_idx+cfg.horizon_bars-1)
        exit_base = float(bars.iloc[exit_i].close)
        status = ('eod_close' if exit_i == len(bars)-1 else 'time_exit')
    highs, lows = zip(*extremes)
    mfe = max(0.0, max(highs)-entry) if direction==1 else max(0.0, entry-min(lows))
    mae = max(0.0, entry-min(lows)) if direction==1 else max(0.0, max(highs)-entry)
    return {'status':status,'exit':exit_base,'idx':exit_i,'ambiguous':ambiguity,
            'mfe':mfe,'mae':mae}


def simulate_holdout(valid: pd.DataFrame, zones: list[dict], atr: float,
                     cfg: SimConfig=SimConfig()) -> tuple[pd.DataFrame,pd.DataFrame,dict]:
    """Static training zones, strictly next-bar entry, single position at a time.

    Research-only indicative fills, never executable broker orders.
    """
    cfg.check()
    if not (math.isfinite(atr) and atr > 0):
        raise ValueError('ATR must be positive')
    v = _validate_frame(valid)
    ids = [z['id'] for z in zones]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate zone IDs')
    for z in zones:
        if z['kind'] not in ('support','resistance') or float(z['lower']) > float(z['upper']):
            raise ValueError('Invalid zone')
    events, trades = [], []
    equity = cfg.starting_equity
    basis_cost = (cfg.half_spread_bps+cfg.slippage_bps)/10_000
    fee_frac = cfg.fee_bps_per_side/10_000
    event_n = trade_n = 0
    for session, orig_day in v.groupby('session',sort=True):
        day = orig_day.sort_values('timestamp').reset_index(drop=True)
        candidates = _touch_events(day,zones)
        day_start_equity = equity
        busy_through = -1
        for i in sorted(candidates):
            arr = candidates[i]
            bar_ts = pd.Timestamp(day.at[i,'timestamp'])
            known_at = bar_ts+BAR
            for z in arr:
                event_n+=1
                ev_id=f'E{event_n:04d}'
                event={'event_id':ev_id, 'zone_id':z['id'], 'kind':z['kind'],
                       'signal_bar_start':bar_ts.isoformat(),
                       'signal_known_at':known_at.isoformat(),
                       'entry_bar_start':None,'entry_open':None,
                       'zone_lower':float(z['lower']),'zone_upper':float(z['upper']),
                       'status':None,'reason':None,'linked_trade_id':None}
                if i <= busy_through:
                    event['status']='skipped_position_busy'
                    event['reason']='Another hypothetical position remained open during this touch'
                elif equity <= day_start_equity*(1-cfg.max_daily_loss_fraction):
                    event['status']='skipped_daily_loss_guard'
                    event['reason']='Daily simulated equity drawdown exceeds limit; no further signals'
                elif len(arr)>1:
                    event['status']='skipped_multi_zone_collision'
                    event['reason']='Same bar touched multiple zones; no cherry-picking side'
                elif z['kind']=='resistance' and not cfg.allow_short_research:
                    event['status']='skipped_short_disabled'
                    event['reason']='Short research disabled in default long-only experiment'
                elif i+1 >= len(day):
                    event['status']='skipped_no_next_bar'
                    event['reason']='No next 15m bar inside same session; never hold overnight'
                elif pd.Timestamp(day.at[i+1,'timestamp'])-bar_ts != BAR:
                    event['status']='skipped_data_gap'
                    event['reason']='Next bar is not contiguous; execution timing cannot be inferred'
                else:
                    next_idx=i+1
                    op=float(day.at[next_idx,'open'])
                    event['entry_bar_start']=pd.Timestamp(day.at[next_idx,'timestamp']).isoformat()
                    event['entry_open']=op
                    if not _near_zone(op,z,atr,cfg.max_entry_distance_atr):
                        event['status']='skipped_entry_too_far'
                        event['reason']='Next bar open outside pre-specified ATR zone proximity'
                    else:
                        side='long' if z['kind']=='support' else 'short'
                        direction=1 if side=='long' else -1
                        entry=op*(1+direction*basis_cost)
                        stop=(float(z['lower'])-cfg.stop_buffer_atr*atr if side=='long'
                              else float(z['upper'])+cfg.stop_buffer_atr*atr)
                        stop_exit_ref=stop*(1-direction*basis_cost)
                        per_share_risk=direction*(entry-stop_exit_ref)
                        if (per_share_risk <= cfg.min_stop_distance_atr*atr or
                                per_share_risk <= 0):
                            event['status']='skipped_invalid_stop'
                            event['reason']='Stop on wrong side or too close after costs'
                        else:
                            qty_risk=math.floor(equity*cfg.risk_fraction/per_share_risk)
                            qty_notional=math.floor(equity*cfg.max_notional_fraction/entry)
                            qty=min(qty_risk,qty_notional)
                            if qty < 1:
                                event['status']='skipped_insufficient_size'
                                event['reason']='Risk/notional budget permits no whole share'
                            else:
                                target=entry+direction*cfg.reward_risk*per_share_risk
                                walk=_execution(day,next_idx,side,entry,stop,target,cfg)
                                event['status']='simulated' if walk['exit'] is not None else walk['status']
                                event['reason']=walk['status']
                                if walk['exit'] is not None:
                                    trade_n+=1
                                    trade_id=f'T{trade_n:04d}'
                                    event['linked_trade_id']=trade_id
                                    exit_ref=float(walk['exit'])
                                    exit_price=exit_ref*(1-direction*basis_cost)
                                    gross=direction*(exit_price-entry)*qty
                                    fees=fee_frac*qty*(entry+exit_price)
                                    pnl=gross-fees
                                    initial_risk=per_share_risk*qty
                                    equity+=pnl
                                    xi=int(walk['idx'])
                                    trade={'trade_id':trade_id,'event_id':ev_id,
                                           'zone_id':z['id'],'side':side,
                                           'signal_bar_start':bar_ts.isoformat(),
                                           'signal_known_at':known_at.isoformat(),
                                           'entry_bar_start':event['entry_bar_start'],
                                           'entry_price':round(entry,6),'planned_stop':round(stop,6),
                                           'planned_target':round(target,6),'quantity':qty,
                                           'initial_planned_risk_usd':round(initial_risk,6),
                                           'exit_bar_start':pd.Timestamp(day.at[xi,'timestamp']).isoformat(),
                                           'exit_known_by':(pd.Timestamp(day.at[xi,'timestamp'])+BAR).isoformat(),
                                           'exit_price':round(exit_price,6),'exit_reason':walk['status'],
                                           'ambiguous_intrabar':bool(walk['ambiguous']),
                                           'bars_held':xi-next_idx+1,
                                           'gross_pnl':round(gross,6),'fees_usd':round(fees,6),
                                           'net_pnl':round(pnl,6),'net_r':round(pnl/initial_risk,6),
                                           'mfe_per_share':round(walk['mfe'],6),
                                           'mae_per_share':round(walk['mae'],6),
                                           'equity_after':round(equity,6)}
                                    trades.append(trade)
                                    busy_through=xi
                                else:
                                    # If data incomplete, lock the whole hypothetical window.
                                    busy_through=min(len(day)-1,next_idx+cfg.horizon_bars-1)
                events.append(event)
    e=pd.DataFrame(events,columns=EVENT_COLUMNS)
    t=pd.DataFrame(trades,columns=TRADE_COLUMNS)
    completed=len(t)
    winning=int((t.net_pnl>0).sum()) if completed else 0
    losing=int((t.net_pnl<0).sum()) if completed else 0
    pnls = t.net_pnl.astype(float).tolist() if completed else []
    wins = [p for p in pnls if p>0]
    losses = [p for p in pnls if p<0]
    gross_wins = sum(wins)
    gross_losses = -sum(losses)
    # Drawdown measured on completed-trade equity, not within open positions.
    checkpoints = [cfg.starting_equity]+(t.equity_after.astype(float).tolist() if completed else [])
    peak = checkpoints[0]
    drawdowns=[]
    for point in checkpoints:
        peak = max(peak, point)
        drawdowns.append((peak-point)/peak if peak>0 else 0.0)
    summary={'simulation_only':True,'paper_or_live_orders_submitted':False,
             'events_total':len(e),'skipped_events':int((e.status!='simulated').sum()) if len(e) else 0,
             'skip_reason_counts':e.loc[e.status!='simulated','status'].value_counts().to_dict() if len(e) else {},
             'trades_completed':completed,'winning_trades':winning,'losing_trades':losing,
             'win_rate':winning/completed if completed else None,
             'net_pnl_usd':round(float(t.net_pnl.sum()),6) if completed else 0.0,
             'mean_net_r':float(t.net_r.mean()) if completed else None,
             'profit_factor':(gross_wins/gross_losses if gross_losses>0 else None),
             'max_closed_trade_equity_drawdown_fraction':max(drawdowns),
             'gross_profit_usd':round(gross_wins,6),
             'gross_loss_usd':round(gross_losses,6),
             'ambiguous_conservative_trades':int(t.ambiguous_intrabar.sum()) if completed else 0,
             'equity_end':round(equity,6),
             'config':asdict(cfg),
             'inference_warning':'Bar-based fills are assumptions, not confirmed broker execution.'}
    return e,t,summary
