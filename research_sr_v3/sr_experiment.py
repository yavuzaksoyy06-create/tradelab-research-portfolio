r"""TradeLab S/R v3 — historical simulation ONLY, no orders or TradingClient.

Run from C:\\Trading\\TradeLab\\research_sr:
  ..\.venv\Scripts\python.exe sr_experiment.py --symbol MSFT
"""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import os
import sys

import pandas as pd
from dotenv import load_dotenv
from sr_core import (NY, prepare_bars, select_completed_sessions,
                     detect_pivots, discover_zones, validate_zones)
from sr_execution import SimConfig, simulate_holdout

HERE = Path(__file__).resolve().parent


def fetch_alpaca(symbol: str, asof_day: str, feed_pref: str):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed

    # The file is designed to live within the existing TradeLab project.
    for env_path in (HERE.parent / '.env', Path.cwd() / '.env', HERE / '.env'):
        if env_path.is_file():
            load_dotenv(env_path, override=False)
            break
    key = os.environ.get('ALPACA_API_KEY', '').strip()
    secret = os.environ.get('ALPACA_SECRET_KEY', '').strip()
    if not key or not secret:
        raise RuntimeError('Missing Alpaca PAPER keys in the existing parent .env; do not paste keys into chat')
    client = StockHistoricalDataClient(key, secret)
    # Exclusive NY midnight cut-off: includes only past, fully closed NY dates.
    cutoff_ny = datetime.strptime(asof_day, '%Y-%m-%d').replace(tzinfo=NY)
    end = cutoff_ny.astimezone(timezone.utc)
    start = (cutoff_ny - timedelta(days=55)).astimezone(timezone.utc)
    candidates = [feed_pref] if feed_pref != 'auto' else ['sip','iex']
    last_error = None
    for feed in candidates:
        try:
            req = StockBarsRequest(symbol_or_symbols=symbol,
                                   timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                                   start=start,end=end,
                                   feed=DataFeed.SIP if feed=='sip' else DataFeed.IEX)
            raw = client.get_stock_bars(req).data.get(symbol, [])
            rows = [dict(timestamp=b.timestamp.isoformat(),open=b.open, high=b.high,
                         low=b.low, close=b.close, volume=b.volume) for b in raw]
            if not rows:
                raise RuntimeError(f'No 15m historical bars returned for {symbol}')
            print(f'[DATA] Alpaca historical {feed.upper()} | {len(rows)} raw bars | end(exclusive)={end.isoformat()}')
            return pd.DataFrame(rows),feed
        except Exception as e:
            last_error = e
            print(f'[DATA] {feed.upper()} unavailable: {type(e).__name__}; no credentials displayed',file=sys.stderr)
    raise RuntimeError(f'Unable to download historical data; last error type {type(last_error).__name__}')


def plot_chart(frame: pd.DataFrame, zones: list[dict], train_len: int,
               title: str, out_path: Path, trades: pd.DataFrame | None = None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D
    import numpy as np

    x = np.arange(len(frame))
    fig, (ax, av) = plt.subplots(2, 1, figsize=(16,9),sharex=True,
                                  gridspec_kw={'height_ratios':[4,1],'hspace':0.06})
    for i, (_,bar) in enumerate(frame.iterrows()):
        up = bar['close'] >= bar['open']
        c = '#1f987a' if up else '#c75151'
        ax.vlines(i,bar['low'],bar['high'],color=c,linewidth=0.8)
        ax.add_patch(Rectangle((i-0.30,min(bar['open'],bar['close'])),0.6,
                               max(0.001,abs(bar['close']-bar['open'])),
                               facecolor=c,edgecolor=c,linewidth=0.4))
        av.bar(i,bar['volume'],color=c,width=0.68)
    for z in zones:
        c = '#198754' if z['kind']=='support' else '#cf3636'
        ax.axhspan(z['lower'],z['upper'], xmin=max(0,(train_len-0.5)/len(frame)), xmax=1, alpha=0.13,color=c)
        ax.hlines(z['center'],xmin=train_len-0.5,xmax=len(frame),linestyle='--',linewidth=1.1,color=c)
        ax.text(len(frame)-0.5,z['center'],f"{z['id']} {z['lower']:.2f}–{z['upper']:.2f}",
                ha='right',va='bottom',fontsize=9,color=c,
                bbox={'facecolor':'white','alpha':0.85,'edgecolor':'none','pad':1.5})
    if trades is not None and not trades.empty:
        stamp_to_i = {pd.Timestamp(ts):j for j,ts in enumerate(frame['timestamp'])}
        for _,tr in trades.iterrows():
            ei = stamp_to_i.get(pd.Timestamp(tr['entry_bar_start']))
            xi = stamp_to_i.get(pd.Timestamp(tr['exit_bar_start']))
            if ei is not None:
                ax.scatter(ei, tr['entry_price'], marker='^' if tr['side']=='long' else 'v',
                           color='#185abd', s=48, zorder=7)
            if xi is not None:
                ax.scatter(xi, tr['exit_price'], marker='x', color='#111111',s=38,zorder=7)
    ax.axvline(train_len-0.5,color='#555555',linewidth=1.4,linestyle=':')
    av.axvline(train_len-0.5,color='#555555',linewidth=1.4,linestyle=':')
    ax.axvspan(train_len-0.5,len(frame)-0.5,color='#3e6c98',alpha=0.07)
    ax.set_ylabel('USD')
    av.set_ylabel('Volume')
    ax.set_title(title+'  |  TRAINING: first 10 sessions  |  HOLDOUT: final 2 (levels only drawn on holdout)',fontsize=11)
    ax.grid(axis='y',alpha=0.2)
    av.grid(axis='y',alpha=0.2)
    starts=frame.groupby('session',sort=False).head(1).index.to_list()
    labels=frame.loc[starts,'session'].tolist()
    av.set_xticks(starts)
    av.set_xticklabels(labels,rotation=55,ha='right',fontsize=8)
    av.set_xlim(-1,len(frame))
    ax.legend(handles=[Line2D([0],[0],color='#198754',label='Support zone'),
                       Line2D([0],[0],color='#cf3636',label='Resistance zone'),
                       Line2D([0],[0],color='#555555',linestyle=':',label='Training / validation boundary')],
              loc='upper left',fontsize=9)
    fig.text(0.02,0.012,'Research simulation only: blue triangles = assumed next-bar entries; x = assumed exits. Not broker fills.',
             fontsize=9,color='#555555')
    fig.subplots_adjust(top=.91, bottom=.16, left=.08, right=.97)
    fig.savefig(out_path,dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description='TradeLab v3 event-sourced S/R execution STUDY, no orders')
    parser.add_argument('--symbol', default='MSFT', help='US equity ticker')
    parser.add_argument('--feed', choices=['sip','iex','auto'], default='sip',
                        help='Default historical SIP; auto may fall back to IEX and will label source')
    parser.add_argument('--asof', default=datetime.now(NY).date().isoformat(),
                        help='Exclusive NY calendar date YYYY-MM-DD; e.g. 2026-10-23')
    parser.add_argument('--input-csv', type=Path, help='Offline OHLCV CSV instead of Alpaca API')
    parser.add_argument('--output', type=Path, default=HERE/'out')
    parser.add_argument('--allow-short-research', action='store_true',
                        help='Hypothetical resistance shorts only, not broker orders')
    parser.add_argument('--intrabar-policy', choices=['adverse_first','exclude'],default='adverse_first')
    parser.add_argument('--horizon', type=int, default=4, help='Max bars after touch signal, default 4')
    parser.add_argument('--half-spread-bps', type=float, default=1.0)
    parser.add_argument('--slippage-bps', type=float, default=2.0)
    parser.add_argument('--fee-bps', type=float, default=0.0)
    args=parser.parse_args()
    symbol=args.symbol.strip().upper()
    if not (symbol.replace('.','').isalpha() and len(symbol)<=8):
        parser.error('Use a valid US equities symbol')
    try:
        datetime.strptime(args.asof,'%Y-%m-%d')
    except ValueError:
        parser.error('Invalid --asof date')

    print('[SAFE] HISTORICAL RESEARCH ONLY | no TradingClient | no broker orders')
    if args.input_csv:
        if not args.input_csv.is_file():
            raise FileNotFoundError(f'Input CSV not found: {args.input_csv}')
        source='CSV (user-supplied, verify data rights/source)'
        raw=pd.read_csv(args.input_csv)
    else:
        raw,source=fetch_alpaca(symbol,args.asof,args.feed)
    df=prepare_bars(raw)
    df=df.loc[df['session'] < args.asof].reset_index(drop=True)
    # V3 research uses ONLY complete 26 x 15m RTH sessions, never silently
    # assumes that missing bars have zero volume or fills.
    all_bars,train,valid,sessions,missing,skipped=select_completed_sessions(
        df,training_days=10,validation_days=2,min_bars=26)
    if missing:
        raise ValueError(f'Incomplete selected RTH sessions: {missing}')
    expected_slots = [(9*60+30)+15*i for i in range(26)]
    for day,group in all_bars.groupby('session'):
        mins=[x.hour*60+x.minute for x in group['ny_start'].dt.tz_localize(None)]
        if mins!=expected_slots or not all(x.second==0 for x in group['ny_start'].dt.tz_localize(None)):
            raise ValueError(f'Irregular intraday bar times in {day}; cannot run a fill simulation')

    pivots=detect_pivots(train,left=3,right=3)
    zones,params=discover_zones(train,pivots,tol_atr=0.35,top_per_side=2)
    train_end=pd.Timestamp(train['timestamp'].iloc[-1])+pd.Timedelta(minutes=15)
    for z in zones:
        if any(pd.Timestamp(p['confirmed_at'])>train_end for p in z['evidence']):
            raise ValueError('Training zone includes an unconfirmed/future pivot')
    atr=float(params['training_median_atr14'])
    reaction=validate_zones(valid,zones,atr,horizon=args.horizon)
    cfg=SimConfig(horizon_bars=args.horizon, intrabar_policy=args.intrabar_policy,
                  allow_short_research=args.allow_short_research,
                  half_spread_bps=args.half_spread_bps, slippage_bps=args.slippage_bps,
                  fee_bps_per_side=args.fee_bps)
    events,trades,summary=simulate_holdout(valid,zones,atr,cfg)
    print(f'[PERIOD] training={sessions[:10]} | HOLDOUT={sessions[10:]}')
    print(f'[DATA] {len(train)} train 15m bars / {len(valid)} holdout bars; feed={source}')
    if skipped:
        print(f'[CAUTION] Insufficient/incomplete sessions omitted: {skipped}')
    for z in zones:
        print(f"[ZONE] {z['id']} {z['kind']} {z['lower']:.2f}-{z['upper']:.2f}; "
              f"{z['pivots']} training pivots / {z['train_touches']} historical touches")
    print('[PRICE REACTIONS — v2 descriptive, NOT trades]',
          reaction['result'].value_counts().to_dict() if not reaction.empty else {})
    print('[EXECUTION EVENT STATUS]',events['status'].value_counts().to_dict() if not events.empty else {})
    print('[SIMULATED TRADES]', summary['trades_completed'],
          '| net hypothetical PnL USD:',summary['net_pnl_usd'],
          '| means nothing statistically with only 2 holdout days')

    args.output.mkdir(parents=True,exist_ok=True)
    out=args.output
    raw_path=out/f'{symbol}_12_sessions_ohlcv.csv'
    all_bars.loc[:,['timestamp','open','high','low','close','volume','session']].to_csv(raw_path,index=False)
    pivots.to_csv(out/f'{symbol}_training_pivots.csv',index=False)
    simple_zones=[{k:v for k,v in z.items() if k not in ('evidence','side_ok')} for z in zones]
    pd.DataFrame(simple_zones).to_csv(out/f'{symbol}_training_zones.csv',index=False)
    evidence=[{'zone_id':z['id'],**p} for z in zones for p in z['evidence']]
    pd.DataFrame(evidence,columns=['zone_id','kind','pivot_index','pivot_at','confirmed_at','price']).to_csv(
        out/f'{symbol}_zone_evidence.csv',index=False)
    reaction.to_csv(out/f'{symbol}_price_reaction_only.csv',index=False)
    events.to_csv(out/f'{symbol}_execution_events.csv',index=False)
    trades.to_csv(out/f'{symbol}_hypothetical_trades.csv',index=False)
    raw_hash=hashlib.sha256(raw_path.read_bytes()).hexdigest()
    audit={
        'version':'v3.0.0','symbol':symbol,'feed':source,'asof_exclusive_ny':args.asof,
        'analysis_is_not_trade_signal':True,'no_orders':True,
        'data_provenance':{'source':str(args.input_csv) if args.input_csv else 'Alpaca historical bars',
                           'raw_csv_sha256':raw_hash,'timezone':'America/New_York',
                           'rth_sessions':sessions,'train_dates':sessions[:10],
                           'holdout_dates':sessions[10:],'session_bars':26,
                           'excluded_sparse_sessions':skipped},
        'train_zone_parameters':params,'zones':simple_zones,
        'reaction_counts':reaction['result'].value_counts().to_dict() if not reaction.empty else {},
        'hypothetical_execution_summary':summary,
        'limitations':[
            '12 total sessions and 2 out-of-sample sessions are NOT statistically sufficient.',
            'One static set of retrospectively chosen training zones; no walk-forward daily re-estimation.',
            'No true broker fills; assumed next-open execution with modeled costs.',
            'Orders within 15-minute candles do not have observable sequence; simultaneous stop and target is assigned adverse-first or excluded.',
            'Opening gaps can cause realized losses greater than the planned trade risk.',
            'Stop order/limit target assumptions are simplistic and not a matching engine.',
            'A single active position and whole-share sizing are simplifying assumptions.',
            'Corporate actions, commissions, borrow availability for shorts and SIP/IEX mismatch require separate research.',
            'Session/half-day/holiday coverage is intentionally restricted to complete 26-bar regular US sessions.',
            'Trade signals require next-bar entry within an ATR-defined distance of a training zone.',
            'Reactions and trade outcomes are distinct measurements.',
            'Technical analysis is not a demonstrated profitable strategy.'
        ]}
    (out/f'{symbol}_audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    plot_chart(all_bars,zones,len(train),f'{symbol} 15m ({source.upper()}) | v3',
               out/f'{symbol}_support_resistance_v3.png',trades)
    print(f'[DONE] Outputs: {out.resolve()}')
    print(f'[AUDIT] SHA256 stored OHLCV: {raw_hash}')


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(f'[ERROR] {type(error).__name__}: {error}',file=sys.stderr)
        sys.exit(1)
