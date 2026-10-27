import unittest
import pandas as pd
from research_sr_v4_1.data import load_cache,features_and_signals,validate_panel
from research_sr_v4_1.portfolio import simulate
from research_sr_v4_1.controls import matched_controls
from research_sr_v4_1.statistics import metrics,compare
from research_sr_v4_1.research import future_readiness
from research_sr_v4.data import DataQualityError

class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel,cls.meta=load_cache()
        cls.features,cls.signals=features_and_signals(cls.panel)
    def run_strategy(self,strategy):
        ss=[s for s in self.signals if s["strategy"]==strategy and "2026-08-25"<=s["session"]<="2026-10-22"]
        r=simulate(self.panel,ss,start="2026-08-25",end="2026-10-22")
        self.assertAlmostEqual(r["final_equity"],100000+sum(t["net_pnl"] for t in r["trades"]),places=7)
        self.assertTrue(all(abs(e["identity_error"])<1e-7 for e in r["equity"]))
        self.assertTrue(all(e["positions"]<=3 and e["cash"]>=0 for e in r["equity"]))
        m=metrics(r)
        self.assertEqual(m["signals"],m["executed_trades"]+m["rejected"])
        self.assertIsNone(m["sharpe"])
        return r,ss
    def test_real_touch_accounting(self):
        self.run_strategy("touch")
    def test_real_rejection_accounting(self):
        self.run_strategy("rejection")
    def test_real_trend_accounting(self):
        self.run_strategy("trend_filtered")
    def test_real_data_full_reproducibility(self):
        a,ss=self.run_strategy("touch")
        b=simulate(dict(reversed(list(self.panel.items()))),list(reversed(ss)),
                   start="2026-08-25",end="2026-10-22")
        self.assertEqual(a,b)
    def test_control_actual_pairing_and_repeatability(self):
        a,ss=self.run_strategy("touch")
        c=matched_controls(self.panel,ss,11)
        self.assertEqual(len(c),len(ss))
        self.assertEqual(c,matched_controls(self.panel,ss,11))
        r=simulate(self.panel,c,start="2026-08-25",end="2026-10-22")
        summary=compare(a,[r])
        self.assertEqual(summary["paired_sessions"],42)
        self.assertIn("NOT forced equal",summary["exposure_matching_status"])
    def test_original_msft_v3_executions_through_new_engine(self):
        f=self.panel["MSFT"]
        ss=[]
        for stamp,lo,hi in [("2026-10-21T13:30Z",528.2026994887309,530.317400511269),
                             ("2026-10-22T14:00Z",524.1125994887309,525.0074005112691)]:
            i=int(f.index[f.timestamp==pd.Timestamp(stamp)][0])
            ss.append({"symbol":"MSFT","strategy":"touch","zone_id":str(i),"signal_index":i,
                "session":f.session.iloc[i],"known_at":str(f.bar_end.iloc[i]),
                "lower":lo,"upper":hi,"atr":1.813717207251907,"collision":False})
        r=simulate({"MSFT":f},ss,start="2026-10-21",end="2026-10-22")
        self.assertEqual([t["quantity"] for t in r["trades"]],[18,19])
        self.assertAlmostEqual(r["trades"][0]["net_pnl"],-48.351521,places=6)
        self.assertAlmostEqual(r["trades"][1]["net_pnl"],-16.307588,places=6)
    def test_future_window_time_gate(self):
        protocol={"future_window":{"complete_after":"2027-01-22T21:15Z"}}
        self.assertFalse(future_readiness(protocol,"2026-10-23T19:00Z")["time_gate_passed"])
        self.assertFalse(future_readiness(protocol,"2027-01-22T21:00Z")["evaluated"])
    def test_correct_equivalent_timezone_is_normalized(self):
        p={s:f.copy() for s,f in self.panel.items()}
        p["QQQ"]["timestamp"]=p["QQQ"].timestamp.dt.tz_convert("America/New_York")
        checked=validate_panel(p,"2026-04-01","2026-10-22")
        self.assertEqual(checked["QQQ"].timestamp.tolist(),checked["MSFT"].timestamp.tolist())

