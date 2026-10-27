"""Deterministic regression tests: no network, credentials or broker code."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import unittest
import pandas as pd
from sr_execution import SimConfig, simulate_holdout


def frame(rows, start='2026-10-22T13:30:00Z', freq='15min'):
    stamps=pd.date_range(start,periods=len(rows),freq=freq,tz='UTC')
    return pd.DataFrame([
        {'timestamp':t, 'open':r[0], 'high':r[1], 'low':r[2], 'close':r[3],
         'session':t.tz_convert('America/New_York').strftime('%Y-%m-%d')}
        for t,r in zip(stamps,rows)])


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.support={'id':'S1','kind':'support','lower':99.7,'upper':100.3,'center':100}
        self.resistance={'id':'R1','kind':'resistance','lower':100.7,'upper':101.3,'center':101}

    def run_study(self, bars, zones=None, cfg=None, atr=1):
        return simulate_holdout(bars, zones if zones is not None else [self.support],atr,
                                cfg if cfg is not None else SimConfig())

    def test_no_entry_on_touch_bar(self):
        bars=frame([(100,100.1,99.9,100),(100.1,102,100.05,101.6),
                    (101.6,101.7,101.2,101.3)])
        events,trades,summary=self.run_study(bars)
        self.assertEqual(len(trades),1)
        self.assertEqual(trades.iloc[0]['entry_bar_start'],bars.iloc[1]['timestamp'].isoformat())
        self.assertEqual(events.iloc[0]['signal_known_at'],(bars.iloc[0]['timestamp']+pd.Timedelta(minutes=15)).isoformat())
        self.assertGreater(trades.iloc[0]['entry_price'],100.1)

    def test_conservative_both_stop_and_target_same_bar(self):
        bars=frame([(100,100.1,99.9,100),(100,102,99.3,101),
                    (101,101.5,100,101.1)])
        e,t,_=self.run_study(bars)
        self.assertEqual(t.iloc[0].exit_reason,'stop_ambiguous_adverse_first')
        self.assertTrue(bool(t.iloc[0].ambiguous_intrabar))
        self.assertLess(float(t.iloc[0].net_pnl),0)

    def test_exclude_intrabar_ambiguous(self):
        bars=frame([(100,100.1,99.9,100),(100,102,99.3,101)])
        e,t,s=self.run_study(bars,cfg=SimConfig(intrabar_policy='exclude'))
        self.assertEqual(len(t),0)
        self.assertEqual(e.iloc[0].status,'ambiguous_unresolved')

    def test_long_stop_before_later_bounce_matches_msft_s2(self):
        # Exact 22 Oct 2026 bars shared by user: signal 14:00, entry 14:15.
        bars=frame([
            (533.68,533.68,529.02,529.55),
            (529.535,529.62,525.13,526.68),
            (526.67,526.735,524.07,524.46),
            (524.475,524.643,522.98,523.32),
            (523.305,524.3,522.36,523.83),
            (523.815,525.96,523.48,525.83),
            (525.895,526.91,525.583,526.675)])
        z={'id':'S2','kind':'support','lower':524.1126,'upper':525.0074,'center':524.5233}
        ev,t,_=self.run_study(bars,zones=[z],atr=1.813717207)
        self.assertEqual(len(t),1)
        self.assertEqual(t.iloc[0].entry_bar_start,bars.iloc[3].timestamp.isoformat())
        self.assertEqual(t.iloc[0].exit_reason,'stop')
        self.assertLess(t.iloc[0].net_pnl,0)

    def test_msft_r1_next_open_not_executable_at_resistance(self):
        bars=frame([(533.68,533.68,529.02,529.55),
                    (529.535,529.62,525.13,526.68)])
        z={'id':'R1','kind':'resistance','lower':533.1926,'upper':535.8858,'center':534.6397}
        ev,t,_=self.run_study(bars,[z],SimConfig(allow_short_research=True),atr=1.813717207)
        self.assertEqual(len(t),0)
        self.assertEqual(ev.iloc[0].status,'skipped_entry_too_far')

    def test_msft_opening_bar_support_resistance_conflict(self):
        bars=frame([(533.68,533.68,529.02,529.55),
                    (529.535,529.62,525.13,526.68)])
        s={'id':'S1','kind':'support','lower':528.2027,'upper':530.3174,'center':529.27}
        r={'id':'R1','kind':'resistance','lower':533.1926,'upper':535.8858,'center':534.6397}
        ev,t,_=self.run_study(bars,[s,r],SimConfig(allow_short_research=True),atr=1.8)
        self.assertEqual(len(t),0)
        self.assertEqual(len(ev),2)
        self.assertEqual(set(ev.status),{'skipped_multi_zone_collision'})

    def test_gap_beyond_stop_fills_at_worse_open(self):
        bars=frame([(100,100.1,99.9,100),(100,100.3,99.95,100.15),
                    (98,98.3,97.6,97.8)])
        _,t,_=self.run_study(bars,cfg=SimConfig(reward_risk=20))
        self.assertEqual(t.iloc[0].exit_reason,'stop_gap')
        self.assertLess(t.iloc[0].exit_price,98)
        self.assertLess(t.iloc[0].net_r,-1)

    def test_target_gap_fills_at_target_not_better_open(self):
        bars=frame([(100,100.1,99.9,100),(100,100.3,99.95,100.15),
                    (110,111,109,110.5)])
        _,t,_=self.run_study(bars,cfg=SimConfig(reward_risk=1.0))
        self.assertEqual(t.iloc[0].exit_reason,'target_gap_at_limit')
        self.assertLess(t.iloc[0].exit_price,110)

    def test_eod_exit_without_overnight(self):
        bars=frame([(100,100.1,99.9,100),(100,100.1,99.95,100.05)],
                   start='2026-10-22T19:15:00Z')
        _,t,_=self.run_study(bars,cfg=SimConfig(horizon_bars=4,reward_risk=20))
        self.assertEqual(len(t),1)
        self.assertEqual(t.iloc[0].exit_reason,'eod_close')
        self.assertEqual(t.iloc[0].bars_held,1)

    def test_last_bar_touch_no_entry(self):
        bars=frame([(101,101.5,100.6,101.2),(100,100.3,99.7,100)])
        e,t,_=self.run_study(bars)
        self.assertEqual(len(t),0)
        self.assertEqual(e.iloc[0].status,'skipped_no_next_bar')

    def test_no_entry_across_session_gap(self):
        bars=frame([(100,100.1,99.9,100),(100,100.3,99.95,100.2)],freq='1D')
        e,t,_=self.run_study(bars)
        self.assertEqual(len(t),0)
        self.assertEqual(e.iloc[0].status,'skipped_no_next_bar')

    def test_missing_next_bar_skipped(self):
        bars=frame([(100,100.1,99.9,100),(100,100.3,99.95,100.2)])
        bars.loc[1,'timestamp']=bars.loc[1,'timestamp']+pd.Timedelta(minutes=15)
        e,t,_=self.run_study(bars)
        self.assertEqual(len(t),0)
        self.assertEqual(e.iloc[0].status,'skipped_data_gap')

    def test_missing_bar_during_position_invalidates(self):
        bars=frame([(100,100.1,99.9,100),(100,100.3,99.95,100.2),
                    (100.3,100.5,100.1,100.4),(100.5,100.8,100.3,100.7)])
        bars.loc[2:,'timestamp']=bars.loc[2:,'timestamp']+pd.Timedelta(minutes=15)
        e,t,_=self.run_study(bars,cfg=SimConfig(reward_risk=20))
        self.assertEqual(len(t),0)
        self.assertEqual(e.iloc[0].status,'invalid_data_gap')

    def test_resistance_short_disabled_by_default(self):
        bars=frame([(101,101.2,100.9,101),(101,101.05,100.5,100.6)])
        e,t,_=self.run_study(bars,[self.resistance])
        self.assertEqual(len(t),0)
        self.assertEqual(e.iloc[0].status,'skipped_short_disabled')

    def test_resistance_short_research_can_be_simulated(self):
        bars=frame([(101,101.1,100.9,101),(101,101.02,100.4,100.5),
                    (100.5,100.6,100.1,100.2)])
        e,t,_=self.run_study(bars,[self.resistance],
                             SimConfig(allow_short_research=True,reward_risk=0.5))
        self.assertEqual(len(t),1)
        self.assertEqual(t.iloc[0].side,'short')
        self.assertEqual(t.iloc[0].exit_reason,'target')

    def test_whole_share_risk_and_notional_limits(self):
        bars=frame([(100,100.1,99.9,100),(100,101.1,100,101)])
        _,t,_=self.run_study(bars,cfg=SimConfig(reward_risk=20))
        self.assertEqual(len(t),1)
        tr=t.iloc[0]
        self.assertLessEqual(tr.quantity*tr.entry_price,10000.0001)
        self.assertLessEqual(tr.initial_planned_risk_usd,500.0001)

    def test_repeat_is_deterministic(self):
        bars=frame([(100,100.1,99.9,100),(100,100.3,99.95,100.15),
                    (100.2,101,100.15,100.8)])
        result1=self.run_study(bars)
        result2=self.run_study(bars)
        pd.testing.assert_frame_equal(result1[0],result2[0])
        pd.testing.assert_frame_equal(result1[1],result2[1])
        self.assertEqual(result1[2],result2[2])

    def test_invalid_ohlc_rejected(self):
        bars=frame([(100,99.8,99.6,100)])
        with self.assertRaises(ValueError): self.run_study(bars)

    def test_nonpositive_prices_rejected(self):
        bars=frame([(100,100.1,-1,100)])
        with self.assertRaises(ValueError): self.run_study(bars)

    def test_duplicate_timestamps_rejected(self):
        bars=frame([(100,100.1,99.9,100),(101,101.5,100.8,101.2)])
        bars.loc[1,'timestamp']=bars.loc[0,'timestamp']
        with self.assertRaises(ValueError): self.run_study(bars)

    def test_empty_event_window_is_inconclusive(self):
        bars=frame([(110,111,109,110),(111,112,110,111)])
        e,t,s=self.run_study(bars)
        self.assertEqual(len(e),0)
        self.assertIsNone(s['win_rate'])


if __name__=='__main__':
    unittest.main()

# Note: tests use synthetic historical bars. No API key or broker connection.
