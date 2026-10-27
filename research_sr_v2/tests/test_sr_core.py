import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

import math
import unittest
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from sr_core import (prepare_bars,select_completed_sessions,detect_pivots,
                     discover_zones,validate_zones,touch_indices)

NY=ZoneInfo('America/New_York')


def synthetic_bars():
    rows=[]
    d=date(2026,10,5)
    days=0
    i=0
    while days<12:
        if d.weekday()<5:
            for k in range(26):
                stamp=datetime(d.year,d.month,d.day,9,30,tzinfo=NY)+timedelta(minutes=15*k)
                close=100+2.0*math.sin(i*.23)+.0025*i
                open_=close + .13*math.cos(i*.43)
                rows.append(dict(timestamp=stamp.isoformat(),
                                 open=open_,high=max(open_,close)+.18,
                                 low=min(open_,close)-.18,close=close,
                                 volume=3000+(i%19)*80))
                i+=1
            days+=1
        d+=timedelta(days=1)
    return pd.DataFrame(rows)


class CoreTests(unittest.TestCase):
    def test_completed_session_split(self):
        s=prepare_bars(synthetic_bars())
        full,train,val,dates,missing,skipped=select_completed_sessions(s)
        self.assertEqual((len(full),len(train),len(val)),(312,260,52))
        self.assertEqual(len(dates),12)
        self.assertEqual(missing,{})
        self.assertLess(train.timestamp.max(),val.timestamp.min())

    def test_no_holdout_leakage_into_zones(self):
        f,t,v,*_=select_completed_sessions(prepare_bars(synthetic_bars()))
        piv=detect_pivots(t)
        z1,p1=discover_zones(t,piv)
        self.assertGreater(len(z1),0)
        # Totally rewrite holdout prices but training zones remain identical.
        f.loc[len(t):,'close'] = 9999.0
        z2,p2=discover_zones(t,detect_pivots(t))
        self.assertEqual([(x['kind'],x['lower'],x['upper']) for x in z1],
                         [(x['kind'],x['lower'],x['upper']) for x in z2])

    def test_pivot_confirmation_after_pivot_time(self):
        full,t,*_=select_completed_sessions(prepare_bars(synthetic_bars()))
        piv=detect_pivots(t,left=3,right=3)
        self.assertGreater(len(piv),3)
        for _,p in piv.iterrows():
            i=int(p.pivot_index)
            self.assertEqual(pd.Timestamp(p.confirmed_at), t.at[i+3,'timestamp']+pd.Timedelta(minutes=15))

    def test_touch_episodes(self):
        x=pd.DataFrame({'low':[9.8,9.9,10.5,10.5,10.5,10.5,9.9,9.95],
                        'high':[10.2,10.1,10.9,10.9,10.9,10.9,10.1,10.05]})
        self.assertEqual(touch_indices(x,9.95,10.05),[0,6])

    def test_validation_bounce_is_descriptive_only(self):
        x=pd.DataFrame({'timestamp':pd.to_datetime([
            '2026-10-20T14:30Z','2026-10-20T14:45Z','2026-10-20T15:00Z',
            '2026-10-20T15:15Z','2026-10-20T15:30Z']),
            'open':[100,100.25,100.35,100.5,100.65],
            'high':[100.2,100.4,100.55,100.7,100.95],
            'low':[99.8,100.2,100.25,100.40,100.55],
            'close':[100,100.3,100.5,100.66,100.8]})
        z=[{'id':'S1','kind':'support','lower':99.9,'upper':100.1,'center':100}]
        out=validate_zones(x,z,atr=1,horizon=4)
        self.assertEqual(out.iloc[0]['result'],'bounce')
        self.assertEqual(len(out),1)

    def test_same_session_horizon_does_not_cross_overnight(self):
        import pandas as pd
        stamps = list(pd.date_range('2026-10-21T19:00:00Z', periods=4, freq='15min')) + \
                 list(pd.date_range('2026-10-22T13:30:00Z', periods=5, freq='15min'))
        x = pd.DataFrame({'timestamp':stamps,
                          'open':[100.0]+[103.0]*8,
                          'high':[100.2]+[103.1]*8,
                          'low':[99.8]+[102.9]*8,
                          'close':[100.0]+[103.0]*8})
        z=[{'id':'S1','kind':'support','lower':99.9,'upper':100.1,'center':100}]
        result=validate_zones(x,z,atr=1,horizon=4)
        self.assertEqual(result.iloc[0]['result'],'insufficient_same_session_followup')
        self.assertEqual(result.iloc[0]['bars_following'],3)
        self.assertTrue(pd.isna(result.iloc[0]['close_after_horizon']))

    def test_adjacent_zones_consolidated_with_training_atr(self):
        f,t,*_=select_completed_sessions(prepare_bars(synthetic_bars()))
        from sr_core import atr_series
        a=float(atr_series(t,14).iloc[14:].median())
        last=float(t['close'].iloc[-1])
        d=[]
        for kind,offset in [('support',-1.5),('resistance',1.5)]:
            for k in (0,0.40):
                price=last+(offset-k if kind=='support' else offset+k)*a
                d.append({'kind':kind,'pivot_index':k,'pivot_at':t['timestamp'].iloc[20].isoformat(),
                          'confirmed_at':t['timestamp'].iloc[24].isoformat(),'price':price})
        z,params=discover_zones(t,pd.DataFrame(d),tol_atr=0.35,merge_gap_atr=0.10)
        self.assertEqual(len([x for x in z if x['kind']=='support']),1)
        self.assertEqual(len([x for x in z if x['kind']=='resistance']),1)
        self.assertEqual(params['pre_consolidation_candidate_count'],4)
        self.assertEqual(params['post_consolidation_candidate_count'],2)

    def test_bad_data_rejected(self):
        d=synthetic_bars()
        d.loc[0,'high']=d.loc[0,'close']-2
        with self.assertRaises(ValueError):
            prepare_bars(d)


if __name__=='__main__':
    unittest.main()
