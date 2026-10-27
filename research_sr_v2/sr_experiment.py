r"""TradeLab S/R Experiment — historical analysis ONLY, no orders or TradingClient.

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
               title: str, out_path: Path):
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
    fig.text(0.02,0.012,'Research visualization — not a trading signal. Future outcomes did not determine training zones.',
             fontsize=9,color='#555555')
    fig.subplots_adjust(top=.91, bottom=.16, left=.08, right=.97)
    fig.savefig(out_path,dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description='TradeLab v2 support/resistance study (READ-ONLY)')
    parser.add_argument('--symbol',default='MSFT',help='US stock ticker, e.g. MSFT, AAPL, NVDA')
    parser.add_argument('--feed',choices=['auto','sip','iex'],default='auto',
                        help='Auto tries SIP historical first, then IEX')
    parser.add_argument('--asof',default=datetime.now(NY).date().isoformat(),
                        help='YYYY-MM-DD NY date, EXCLUSIVE start of this date; defaults to today')
    parser.add_argument('--input-csv',type=Path,help='Optional OHLCV CSV instead of Alpaca API')
    parser.add_argument('--output',type=Path,default=HERE/'out')
    args=parser.parse_args()
    symbol=args.symbol.strip().upper()
    if not (symbol.replace('.', '').isalpha() and len(symbol)<=8):
        parser.error('Use a valid US equities symbol')
    try:
        datetime.strptime(args.asof,'%Y-%m-%d')
    except ValueError:
        parser.error('--asof must be YYYY-MM-DD')
    print('[SAFE] RESEARCH-ONLY | no TradingClient | no order capabilities')
    if args.input_csv:
        source='CSV (user supplied)'
        raw=pd.read_csv(args.input_csv)
    else:
        raw,source=fetch_alpaca(symbol,args.asof,args.feed)
    df=prepare_bars(raw)
    df=df.loc[df['session'] < args.asof].reset_index(drop=True)
    all_bars, train, valid, sessions, missing, skipped = select_completed_sessions(df)
    pivots=detect_pivots(train,left=3,right=3)
    zones,params=discover_zones(train,pivots,tol_atr=0.35,top_per_side=2)
    result=validate_zones(valid,zones,params['training_median_atr14'],horizon=4)
    print('[PERIOD] Training:',sessions[:10],'| validation:',sessions[10:])
    if missing:
        print('[CAUTION] Missing 15m bars in included sessions:',missing)
    print('[LEVELS]',len(zones),'zones; holdout touch events:',len(result))
    for z in zones:
        print(f"  {z['id']} {z['kind']}  {z['lower']:.2f}–{z['upper']:.2f} "
              f"({z['pivots']} pivots / {z['train_touches']} train touches)")
    if result.empty:
        print('[RESULT] No independent validation touches. INCONCLUSIVE; do not infer success.')
    else:
        print('[RESULT] Holdout outcomes:',result['result'].value_counts().to_dict())
    args.output.mkdir(parents=True,exist_ok=True)
    out=args.output
    # Raw retained provenance: model outputs cannot be substituted for source data.
    raw_path=out/f'{symbol}_12_sessions_ohlcv.csv'
    all_bars.loc[:,list(['timestamp','open','high','low','close','volume','session'])].to_csv(raw_path,index=False)
    pivots.to_csv(out/f'{symbol}_training_pivots.csv',index=False)
    simple_zones=[{k:v for k,v in z.items() if k not in ('evidence','side_ok')} for z in zones]
    pd.DataFrame(simple_zones).to_csv(out/f'{symbol}_training_zones.csv',index=False)
    evidence=[]
    for z in zones:
        for p in z['evidence']:
            evidence.append({'zone_id':z['id'],**p})
    pd.DataFrame(evidence,columns=['zone_id','kind','pivot_index','pivot_at',
                                   'confirmed_at','price']).to_csv(out/f'{symbol}_zone_evidence.csv',index=False)
    result.to_csv(out/f'{symbol}_holdout_validation.csv',index=False)
    raw_hash=hashlib.sha256(raw_path.read_bytes()).hexdigest()
    report={
        'symbol':symbol,'feed':source,'asof_exclusive_ny':args.asof,
        'analysis_is_not_trade_signal':True,
        'source':'Alpaca historical bars API' if not args.input_csv else str(args.input_csv),
        'timezone':'America/New_York',
        'session':'09:30–16:00 US Eastern (RTH), 15m bars, no extended hours',
        'selected_sessions':sessions,
        'training_sessions':sessions[:10],
        'heldout_validation_sessions':sessions[10:],
        'selected_session_missing_bar_count':missing,
        'other_rejected_sparse_sessions':skipped,
        'raw_csv_sha256':raw_hash,
        'parameters':params|{'left_pivot_bars':3,'right_pivot_bars':3,
                            'min_bars_per_day':24,'expected_bars_per_full_day':26,
                            'validation_horizon_bars':4,'bounce_criterion_atr':0.5,
                            'break_criterion_atr_beyond_zone':0.25,
                            'touch_separation_non_touch_bars':4,
                            'same_session_followup_only':True,
                            'zone_consolidation_uses_training_atr':True,
                            'max_zones_per_side':2},
        'zones':simple_zones,
        'validation_rows':len(result),
        'validation_outcomes':result['result'].value_counts().to_dict() if not result.empty else {},
        'limitations':[
            '12 sessions are only a technical demonstration, not statistical proof.',
            'Zones selected using training data retrospectively, without trading performance claims.',
            'Touches and OHLC after-touch extrema do not prove executable fills.',
            'Intrabar event ordering is unknown with 15m OHLC bars.',
            'Intraday RTH aggregation across holidays/half-days and some missing bars is simplified.',
            'IEX is a single exchange and may differ from consolidated SIP or TradingView data.',
            'No split adjustment; for long sample spans corporate actions must be addressed.',
            'Training zone selection is retrospective; do not interpret older training touches as live forecasts.',
            'Zone consolidation is a heuristic based on train ATR; not empirically optimized.',
            'Adjacent days are never combined into a four-bar validation horizon.',
            'Validation touches are not independent if nearby in time/market regime.'
        ]
    }
    (out/f'{symbol}_audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    chart=out/f'{symbol}_support_resistance.png'
    plot_chart(all_bars,zones,len(train),f'{symbol} 15m ({source.upper()})',chart)
    print(f'[DONE] Files saved to: {out.resolve()}')
    print(f'[AUDIT] SHA256 raw OHLCV: {raw_hash}')


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        print(f'[ERROR] {type(error).__name__}: {error}',file=sys.stderr)
        sys.exit(1)
