"""Deterministic support/resistance experiment. No broker or order functionality.

Research only: pivot zones are discovered on a training window; validation data
are never used to construct or rank them. See README for limitations.
"""
from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo
import math
import pandas as pd

NY = ZoneInfo('America/New_York')
BAR_MINUTES = 15
REQUIRED = ('timestamp', 'open', 'high', 'low', 'close', 'volume')


def prepare_bars(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f'Missing OHLCV columns: {missing}')
    df = frame.loc[:, list(REQUIRED)].copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='raise')
    for c in REQUIRED[1:]:
        df[c] = pd.to_numeric(df[c], errors='raise')
    if df['timestamp'].duplicated().any():
        raise ValueError('Duplicate bar timestamps: cannot audit source reliably')
    df = df.sort_values('timestamp').reset_index(drop=True)
    if df[list(REQUIRED[1:])].isna().any().any():
        raise ValueError('Missing OHLCV values')
    if not all(math.isfinite(float(v)) for v in df[list(REQUIRED[1:])].to_numpy().ravel()):
        raise ValueError('Nonfinite OHLCV value')
    if (df['low'] <= 0).any() or (df['volume'] < 0).any():
        raise ValueError('Invalid price or volume')
    if ((df['high'] < df[['open', 'close', 'low']].max(axis=1)) |
        (df['low'] > df[['open', 'close', 'high']].min(axis=1))).any():
        raise ValueError('Inconsistent OHLC values')
    ny_timestamps = df['timestamp'].dt.tz_convert(NY)
    df['session'] = ny_timestamps.dt.strftime('%Y-%m-%d')
    df['ny_start'] = ny_timestamps
    local_time = ny_timestamps.dt.time
    # Only US regular-session 15m starts. This study intentionally omits half-days.
    rth = (local_time >= time(9, 30)) & (local_time <= time(15, 45))
    df = df.loc[rth].copy().reset_index(drop=True)
    return df


def select_completed_sessions(df: pd.DataFrame, training_days=10, validation_days=2,
                              min_bars=24):
    """Select chronologically last 12 sufficiently covered *past* RTH sessions.

    Caller must exclude current NY calendar day before passing bars. At least
    min_bars of expected 26 are required. Missing bars are reported, never filled.
    """
    expected = 26
    counts = df.groupby('session').size()
    candidate = [str(s) for s, n in counts.items() if min_bars <= n <= expected]
    required = training_days + validation_days
    if len(candidate) < required:
        raise ValueError(f'Need {required} sessions with at least {min_bars}/26 bars; '
                         f'got {len(candidate)}. Possible IEX gaps, half-days or data limits.')
    sessions = candidate[-required:]
    chosen = df.loc[df['session'].isin(sessions)].copy().reset_index(drop=True)
    train_names = sessions[:training_days]
    val_names = sessions[training_days:]
    train = chosen.loc[chosen['session'].isin(train_names)].reset_index(drop=True)
    valid = chosen.loc[chosen['session'].isin(val_names)].reset_index(drop=True)
    missing = {s: expected-int(counts[s]) for s in sessions if int(counts[s]) != expected}
    skipped = {str(s): int(n) for s,n in counts.items() if s not in sessions and n < min_bars}
    return chosen, train, valid, sessions, missing, skipped


def atr_series(df: pd.DataFrame, period=14) -> pd.Series:
    prior = df['close'].shift(1)
    tr = pd.concat([(df['high']-df['low']).abs(),
                    (df['high']-prior).abs(),
                    (df['low']-prior).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def detect_pivots(train: pd.DataFrame, left=3, right=3) -> pd.DataFrame:
    """Strict extrema; confirmation occurs at the END of the rightmost bar."""
    if left < 1 or right < 1:
        raise ValueError('left/right must be >= 1')
    out = []
    for i in range(left, len(train)-right):
        hi = float(train.at[i, 'high'])
        lo = float(train.at[i, 'low'])
        left_hi = train.iloc[i-left:i]['high']
        right_hi = train.iloc[i+1:i+1+right]['high']
        left_lo = train.iloc[i-left:i]['low']
        right_lo = train.iloc[i+1:i+1+right]['low']
        confirm = (train.at[i+right,'timestamp'] + pd.Timedelta(minutes=BAR_MINUTES)).isoformat()
        for kind, yes, price in (
            ('resistance', bool((hi > left_hi).all() and (hi > right_hi).all()), hi),
            ('support', bool((lo < left_lo).all() and (lo < right_lo).all()), lo)
        ):
            if yes:
                out.append({'kind':kind,'pivot_index':i,'pivot_at':train.at[i,'timestamp'].isoformat(),
                            'confirmed_at':confirm,'price':price})
    return pd.DataFrame(out, columns=['kind','pivot_index','pivot_at','confirmed_at','price'])


def touch_indices(df: pd.DataFrame, low: float, high: float, gap_bars=4) -> list[int]:
    """Starts of touch episodes; at least gap_bars non-touch bars separate episodes."""
    touching = (df['low'] <= high) & (df['high'] >= low)
    starts = []
    last_touch = -(gap_bars+2)
    for i, touch in enumerate(touching):
        if touch:
            if i-last_touch >= gap_bars+1:
                starts.append(i)
            last_touch = i
    return starts


def discover_zones(train: pd.DataFrame, pivots: pd.DataFrame, tol_atr=0.35,
                   top_per_side=2):
    if len(train) < 20:
        raise ValueError('Insufficient training bars')
    atr = float(atr_series(train, 14).iloc[14:].median())
    if not (math.isfinite(atr) and atr > 0):
        raise ValueError('Invalid training ATR')
    width = max(0.01, tol_atr*atr)
    last_price = float(train['close'].iloc[-1])
    all_zones=[]
    for kind in ('support','resistance'):
        sub=pivots.loc[pivots['kind'].eq(kind)].sort_values('price').to_dict('records')
        clusters=[]
        for p in sub:
            if clusters and abs(float(p['price'])-clusters[-1]['center']) <= width:
                members=clusters[-1]['members']
                members.append(p)
                clusters[-1]['center']=sum(float(m['price']) for m in members)/len(members)
            else:
                clusters.append({'center':float(p['price']),'members':[p]})
        # Merge overlapping bands, avoiding near-duplicate support or resistance zones.
        merged=[]
        for cl in clusters:
            if merged:
                prev=merged[-1]
                prev_lo=min(float(m['price']) for m in prev['members'])-width/2
                prev_hi=max(float(m['price']) for m in prev['members'])+width/2
                this_lo=min(float(m['price']) for m in cl['members'])-width/2
                this_hi=max(float(m['price']) for m in cl['members'])+width/2
                if this_lo <= prev_hi:
                    prev['members'].extend(cl['members'])
                    prev['center']=sum(float(m['price']) for m in prev['members'])/len(prev['members'])
                    continue
            merged.append(cl)
        for cl in merged:
            members=cl['members']
            prices=[float(m['price']) for m in members]
            lower=min(prices)-width/2
            upper=max(prices)+width/2
            events=touch_indices(train,lower,upper)
            side_ok = (cl['center'] < last_price if kind=='support' else cl['center'] > last_price)
            all_zones.append({'kind':kind,'lower':lower,'upper':upper,'center':cl['center'],
                              'pivots':len(members),'train_touches':len(events),
                              'score':2*len(members)+len(events),
                              'last_pivot_at':max(m['pivot_at'] for m in members),
                              'side_ok':side_ok,
                              'evidence':members})
    chosen=[]
    for kind in ('support','resistance'):
        matching=[z for z in all_zones if z['kind']==kind and z['side_ok']]
        matching.sort(key=lambda z:(z['score'],z['last_pivot_at'], -abs(z['center']-last_price)),reverse=True)
        chosen.extend(matching[:top_per_side])
    for n,z in enumerate(chosen,1):
        z['id']=('S' if z['kind']=='support' else 'R') + str(sum(a['kind']==z['kind'] for a in chosen[:n]))
    return chosen, {'training_median_atr14':atr,'cluster_center_tolerance':width,
                    'train_last_close':last_price,'left_right_pivots':3,
                    'touch_gap_non_touch_bars':4}


def validate_zones(valid:pd.DataFrame,zones:list[dict],atr:float,horizon=4):
    rows=[]
    for z in zones:
        events=touch_indices(valid,z['lower'],z['upper'])
        for i in events:
            follow=valid.iloc[i+1:i+horizon+1]
            item={'zone_id':z['id'],'kind':z['kind'],
                  'touch_at':valid.at[i,'timestamp'].isoformat(),
                  'zone_lower':round(z['lower'],4),'zone_upper':round(z['upper'],4),
                  'bars_following':len(follow),'result':'insufficient_followup',
                  'mfe_from_zone_mid':None,'mae_from_zone_mid':None}
            if len(follow)==horizon:
                mid=z['center']
                high=float(follow['high'].max())
                low=float(follow['low'].min())
                final=float(follow['close'].iloc[-1])
                # Ex post displacement test, NOT a prediction or executable trade.
                if z['kind']=='support':
                    item['result']=('bounce' if final>=mid+0.5*atr else
                                    'break' if final<z['lower']-0.25*atr else 'ambiguous')
                    item['mfe_from_zone_mid']=round(high-mid,4)
                    item['mae_from_zone_mid']=round(low-mid,4)
                else:
                    item['result']=('bounce' if final<=mid-0.5*atr else
                                    'break' if final>z['upper']+0.25*atr else 'ambiguous')
                    item['mfe_from_zone_mid']=round(mid-low,4)
                    item['mae_from_zone_mid']=round(mid-high,4)
            rows.append(item)
    return pd.DataFrame(rows,columns=['zone_id','kind','touch_at','zone_lower','zone_upper',
                                      'bars_following','result','mfe_from_zone_mid',
                                      'mae_from_zone_mid'])
