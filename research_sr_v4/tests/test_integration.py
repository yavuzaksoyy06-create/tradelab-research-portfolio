"""Offline integration against downloaded, hashed SIP caches; no network calls."""
from pathlib import Path
import hashlib
import json
import unittest
import pandas as pd
from research_sr_v4.data import validate
from research_sr_v4.causal import build_features
from research_sr_v4.execution import simulate
from research_sr_v4.research import metrics

ROOT=Path(__file__).resolve().parents[1]

class MarketDataIntegrationTests(unittest.TestCase):
    def load(self,symbol):
        path=ROOT/"out/cache"/f"{symbol}_2026-04-01_2026-10-22_sip_split_15m.csv"
        if not path.exists():
            self.skipTest("Run explicit historical ingestion first; no substitute data")
        meta=json.loads(path.with_suffix(".json").read_text())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),meta["sha256"])
        f=validate(pd.read_csv(path),"2026-04-01","2026-10-22")
        self.assertEqual(len(f),3692)
        self.assertEqual(f.session.nunique(),142)
        return f
    def check_symbol(self,symbol):
        f=self.load(symbol)
        features=build_features(f)
        for strategy in ["touch","rejection","trend_filtered"]:
            r=simulate(f,[s for s in features["signals"] if s["strategy"]==strategy],start="2026-09-01",end="2026-10-22")
            self.assertAlmostEqual(r["final_equity"],100000+sum(t["net_pnl"] for t in r["trades"]),places=7)
            last_exit=-1
            for t in r["trades"]:
                self.assertGreater(t["entry_index"],last_exit)
                last_exit=t["exit_index"]
                self.assertGreater(t["quantity"],0)
                self.assertLessEqual(t["mfe_lower"],t["mfe_upper"])
                self.assertLessEqual(t["mae_lower"],t["mae_upper"])
                if t["reason"]=="stop":
                    self.assertAlmostEqual(t["net_pnl"],-t["planned_risk"],places=7)
                if t["reason"]=="target":
                    self.assertAlmostEqual(t["net_pnl"],2*t["planned_risk"],places=7)
            self.assertTrue(all(e["position_quantity"]==0 for e in r["equity"] if e["timestamp"].endswith("20:00:00+00:00")))
            m=metrics(r)
            self.assertEqual(m["signals"],m["executed"]+m["rejected"])
    def test_msft_lifecycle(self):
        self.check_symbol("MSFT")
    def test_spy_lifecycle(self):
        self.check_symbol("SPY")
    def test_qqq_lifecycle(self):
        self.check_symbol("QQQ")
    def test_real_data_prefix_invariance(self):
        f=self.load("MSFT")
        a=build_features(f.iloc[:2000])
        b=build_features(f)
        self.assertEqual(a["snapshots"],b["snapshots"][:2000])
        self.assertEqual(a["signals"],[s for s in b["signals"] if s["signal_index"]<2000])

