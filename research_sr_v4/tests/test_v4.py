"""Financial-invariant tests; synthetic OHLCV is explicitly not market performance."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from research_sr_v4.data import validate, expected_grid, DataQualityError
from research_sr_v4.causal import build_features, FeatureConfig
from research_sr_v4.execution import simulate, ExecutionConfig
from research_sr_v4.research import bootstrap, metrics

def fixture(start="2026-10-22",end=None):
    f=expected_grid(start,end or start)
    f["open"]=100.
    f["high"]=100.2
    f["low"]=99.9
    f["close"]=100.
    f["volume"]=1000.
    return f

def bar(f,i,o,h,l,c):
    f.loc[i,["open","high","low","close"]]=[o,h,l,c]

def signal(f,i=0,**kw):
    return {"signal_index":i,"known_at":str(f.bar_end.iloc[i]),"session":f.session.iloc[i],
        "zone_id":"S1","lower":99.7,"upper":100.3,"atr":1.,"strategy":"touch",
        "regime":"other","collision":False,**kw}

class DataTests(unittest.TestCase):
    def test_early_close(self):
        self.assertEqual(len(expected_grid("2026-11-27","2026-11-27")),14)
        self.assertEqual(str(expected_grid("2026-11-27","2026-11-27").bar_end.iloc[-1]),"2026-11-27 18:00:00+00:00")
    def test_holiday(self):
        self.assertEqual(len(expected_grid("2026-12-25","2026-12-25")),0)
    def test_dst(self):
        self.assertEqual(expected_grid("2026-03-06","2026-03-06").timestamp.iloc[0].hour,14)
        self.assertEqual(expected_grid("2026-03-09","2026-03-09").timestamp.iloc[0].hour,13)
    def test_complete_session(self):
        self.assertEqual(len(validate(fixture(),"2026-10-22","2026-10-22")),26)
    def test_missing_bar(self):
        with self.assertRaises(DataQualityError):
            validate(fixture().drop(index=2),"2026-10-22","2026-10-22")
    def test_truncated_day(self):
        with self.assertRaises(DataQualityError):
            simulate(fixture().iloc[:2],[signal(fixture())])
    def test_duplicate(self):
        f=fixture()
        with self.assertRaises(DataQualityError):
            validate(pd.concat([f,f.iloc[:1]]),"2026-10-22","2026-10-22")
    def test_naive_timezone(self):
        f=fixture()
        f["timestamp"]=f.timestamp.dt.tz_localize(None)
        with self.assertRaises(DataQualityError):
            validate(f,"2026-10-22","2026-10-22")
    def test_invalid_price_volume(self):
        for col,value in [("low",0),("open",-1),("close",np.nan),("high",np.inf),("volume",-1)]:
            f=fixture()
            f.loc[1,col]=value
            with self.subTest(column=col,value=value),self.assertRaises(DataQualityError):
                validate(f,"2026-10-22","2026-10-22")
    def test_invalid_range(self):
        f=fixture()
        f.loc[0,"high"]=99
        with self.assertRaises(DataQualityError):
            validate(f,"2026-10-22","2026-10-22")
    def test_future_unfinished_bar(self):
        with self.assertRaises(DataQualityError):
            validate(fixture(),"2026-10-22","2026-10-22",now="2026-10-22T14:00Z")
    def test_missing_entire_session(self):
        f=fixture()
        with self.assertRaises(DataQualityError):
            validate(f,"2026-10-21","2026-10-22")

class CausalTests(unittest.TestCase):
    def sample(self):
        f=fixture("2026-10-01","2026-10-22")
        x=np.arange(len(f))
        f["close"]=100+np.sin(x*.4)
        f["open"]=f.close-.1
        f["low"]=f.close-.4
        f["high"]=f.close+.4
        return f
    def test_confirmed_pivot_not_early(self):
        f=fixture()
        f.loc[20,"low"]=90
        before=build_features(f.iloc[:23])
        after=build_features(f.iloc[:24])
        self.assertFalse(any(p["pivot_index"]==20 for p in before["pivots"]))
        p=next(p for p in after["pivots"] if p["pivot_index"]==20)
        self.assertEqual(p["confirmed_index"],23)
        self.assertEqual(p["confirmed_at"],str(f.bar_end.iloc[23]))
    def test_prefix_invariance_on_adversarial_future(self):
        f=self.sample()
        prefix=build_features(f.iloc[:200])
        f.loc[200:,["open","high","low","close"]]*=10
        extended=build_features(f)
        self.assertEqual(prefix["snapshots"],extended["snapshots"][:200])
        self.assertEqual(prefix["signals"],[s for s in extended["signals"] if s["signal_index"]<200])
        self.assertEqual(prefix["pivots"],[p for p in extended["pivots"] if p["confirmed_index"]<200])
    def test_hourly_filter_cannot_use_unclosed_bucket(self):
        f=self.sample()
        a=build_features(f.iloc[:3])
        b=build_features(f.iloc[:4])
        self.assertIsNone(a["snapshots"][-1]["hourly_ema9"])
        self.assertEqual(b["snapshots"][-1]["hourly_ema9"],f.close.iloc[3])
    def test_overlap_merges_same_kind(self):
        f=fixture("2026-10-21","2026-10-22")
        f[["open","close"]]=105.
        f["high"]=106.
        f["low"]=104.
        f.loc[20,"low"]=100.
        f.loc[30,"low"]=100.1
        r=build_features(f)
        z=[z for z in r["snapshots"][33]["zones"] if z["kind"]=="support"]
        self.assertEqual(len(z),1)
        self.assertEqual(z[0]["pivot_count"],2)
    def test_touch_separation_and_strategy_subsets(self):
        r=build_features(self.sample(),replace(FeatureConfig(),min_pivots=1))
        a={(s["signal_index"],s["zone_id"]) for s in r["signals"] if s["strategy"]=="touch"}
        b={(s["signal_index"],s["zone_id"]) for s in r["signals"] if s["strategy"]=="rejection"}
        c={(s["signal_index"],s["zone_id"]) for s in r["signals"] if s["strategy"]=="trend_filtered"}
        self.assertTrue(c<=b<=a)
        self.assertGreater(len(a),0)
        self.assertGreater(len(b),0)
        self.assertGreater(len(c),0)
        f=self.sample()
        for sig in r["signals"]:
            if sig["strategy"] in {"rejection","trend_filtered"}:
                row=f.iloc[sig["signal_index"]]
                self.assertGreater(row.close,sig["upper"])
                self.assertGreater(row.close,row.open)
                self.assertGreaterEqual(row.close-row.low,.1*sig["atr"])
            if sig["strategy"]=="trend_filtered":
                self.assertEqual(sig["regime"],"uptrend")
        for zone in {s["zone_id"] for s in r["signals"]}:
            indices=sorted({s["signal_index"] for s in r["signals"] if s["zone_id"]==zone})
            self.assertTrue(all(y-x>=4 for x,y in zip(indices,indices[1:])))
    def test_zone_expiration(self):
        f=fixture("2026-10-21","2026-10-22")
        f.loc[20,"low"]=90
        r=build_features(f,replace(FeatureConfig(),lookback_bars=10))
        self.assertTrue(any(e["event"]=="expired" for e in r["lifecycle"]))
    def test_two_close_break_invalidation(self):
        f=fixture("2026-10-21","2026-10-22")
        f.loc[20,"low"]=99
        for i in [25,26]:
            bar(f,i,95,96,94,95)
        r=build_features(f)
        self.assertTrue(any(e["event"]=="invalidated" for e in r["lifecycle"]))
    def test_invalid_feature_config(self):
        with self.assertRaises(ValueError):
            FeatureConfig(zone_half_width_atr=float("nan"))

class ExecutionTests(unittest.TestCase):
    def run_one(self,f=None,s=None,cfg=ExecutionConfig()):
        f=fixture() if f is None else f
        return simulate(f,[signal(f)] if s is None else s,cfg)
    def test_next_open_fill(self):
        f=fixture()
        bar(f,0,100,110,90,100) # Signal candle's stop does not affect a later position.
        r=self.run_one(f)
        t=r["trades"][0]
        self.assertEqual(t["entry_at"],str(f.timestamp.iloc[1]))
        self.assertAlmostEqual(t["entry_price"],100.03)
        self.assertEqual(t["reason"],"horizon_close")
    def test_early_signal_timestamp_rejected(self):
        f=fixture()
        r=self.run_one(f,[signal(f,known_at=str(f.timestamp.iloc[0]))])
        self.assertEqual(r["events"][0]["status"],"invalid_signal")
    def test_no_entry_on_next_session(self):
        f=fixture("2026-10-21","2026-10-22")
        r=self.run_one(f,[signal(f,25)])
        self.assertEqual(r["events"][0]["status"],"no_next_same_session_bar")
    def test_stop_below_open_fee_mask_regression(self):
        f=fixture()
        bar(f,1,99.599,100.1,99.4,99.9)
        r=self.run_one(f)
        self.assertEqual(r["events"][0]["status"],"entry_open_at_or_below_stop")
        self.assertFalse(r["trades"])
    def test_gap_stop(self):
        f=fixture()
        bar(f,2,95,96,94,95)
        t=self.run_one(f)["trades"][0]
        self.assertEqual(t["reason"],"gap_stop")
        self.assertAlmostEqual(t["exit_price"],95*(1-.0003))
    def test_gap_target_uses_observed_open(self):
        f=fixture()
        bar(f,2,105,106,104,105)
        t=self.run_one(f)["trades"][0]
        self.assertEqual(t["reason"],"gap_target_open")
        self.assertEqual(t["raw_exit"],105)
        self.assertAlmostEqual(t["exit_price"],105*(1-.0003))
    def test_collision_adverse_first(self):
        f=fixture()
        bar(f,1,100,105,90,100)
        t=self.run_one(f)["trades"][0]
        self.assertEqual(t["reason"],"stop")
        self.assertTrue(t["collision_adverse_first"])
    def test_exit_bar_excursions_bounded_not_fabricated(self):
        f=fixture()
        bar(f,1,100,105,90,100)
        t=self.run_one(f)["trades"][0]
        self.assertIsNone(t["mfe_exact"])
        self.assertIsNone(t["mae_exact"])
        self.assertLess(t["mae_lower"],t["observed_mae"])
        self.assertEqual(t["mae_upper"],t["observed_mae"])
    def test_stop_before_rebound(self):
        f=fixture()
        bar(f,1,100,100.1,99,99.5)
        bar(f,2,101,110,100,109)
        t=self.run_one(f)["trades"][0]
        self.assertEqual(t["exit_index"],1)
        self.assertLess(t["net_pnl"],0)
        self.assertLess(t["observed_mfe"],1)
    def test_missing_after_entry_fails_whole_run(self):
        f=fixture().drop(index=2)
        with self.assertRaises(DataQualityError):
            self.run_one(f,[signal(f)])
    def test_fees_inside_risk_budget(self):
        f=fixture()
        bar(f,1,100,100.2,99,99.5)
        cfg=replace(ExecutionConfig(),risk_fraction=.0001,fee_bps=100)
        t=self.run_one(f,cfg=cfg)["trades"][0]
        self.assertLessEqual(t["planned_risk"],10)
        self.assertAlmostEqual(-t["net_pnl"],t["planned_risk"])
    def test_target_is_net_reward_risk(self):
        f=fixture()
        bar(f,1,100,110,99.9,105)
        t=self.run_one(f,cfg=replace(ExecutionConfig(),fee_bps=10))["trades"][0]
        self.assertEqual(t["reason"],"target")
        self.assertAlmostEqual(t["r_multiple"],2)
    def test_no_overlap(self):
        f=fixture()
        r=self.run_one(f,[signal(f),signal(f,1,zone_id="S2")])
        self.assertEqual(r["events"][1]["status"],"position_already_open")
        self.assertEqual(len(r["trades"]),1)
    def test_duplicate_signal(self):
        f=fixture()
        r=self.run_one(f,[signal(f),signal(f)])
        self.assertEqual(r["events"][1]["status"],"duplicate_signal")
        self.assertEqual(len(r["trades"]),1)
    def test_multi_zone_signal_collision(self):
        f=fixture()
        r=self.run_one(f,[signal(f),signal(f,zone_id="S2")])
        self.assertFalse(r["trades"])
        self.assertTrue(all(e["status"]=="multi_zone_collision" for e in r["events"]))
    def test_wide_signal_candle_collision_flag(self):
        f=fixture()
        r=self.run_one(f,[signal(f,collision=True)])
        self.assertFalse(r["trades"])
    def test_entry_too_far(self):
        f=fixture()
        bar(f,1,102,103,101,102)
        self.assertEqual(self.run_one(f)["events"][0]["status"],"entry_too_far")
    def test_insufficient_capital(self):
        r=self.run_one(cfg=replace(ExecutionConfig(),initial_capital=1))
        self.assertEqual(r["events"][0]["status"],"insufficient_capital")
    def test_limits_and_nonfinite_config(self):
        for change in [{"risk_fraction":.006},{"max_notional_fraction":.11},{"daily_drawdown":.03},
                       {"fee_bps":float("nan")},{"initial_capital":float("inf")}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                replace(ExecutionConfig(),**change)
    def test_invalid_indicator(self):
        f=fixture()
        r=self.run_one(f,[signal(f,atr=float("nan"))])
        self.assertEqual(r["events"][0]["status"],"invalid_signal")
    def test_eod_real_close(self):
        f=fixture()
        t=self.run_one(f,[signal(f,24)])["trades"][0]
        self.assertEqual(t["reason"],"exchange_session_close")
        self.assertEqual(t["exit_known_by"],str(f.session_close.iloc[-1]))
    def test_cash_mark_to_market_and_pnl(self):
        f=fixture()
        bar(f,1,100,101.2,99.9,101)
        r=self.run_one(f,cfg=replace(ExecutionConfig(),reward_risk=20))
        t=r["trades"][0]
        row=r["equity"][1]
        self.assertAlmostEqual(row["equity"],row["cash"]+row["position_quantity"]*101)
        self.assertGreater(row["position_quantity"],0)
        self.assertAlmostEqual(r["final_equity"],100000+sum(t["net_pnl"] for t in r["trades"]))
        self.assertTrue(all(x["cash"]>=0 for x in r["equity"]))
        self.assertLessEqual(t["quantity"]*t["entry_price"],10000)
    def test_daily_drawdown_blocks_after_gap(self):
        f=fixture()
        bar(f,2,70,71,69,70)
        r=self.run_one(f,[signal(f),signal(f,2,zone_id="S2")])
        self.assertEqual(r["events"][1]["status"],"daily_drawdown_block")
        self.assertLess(r["final_equity"],98000)
    def test_repeatability(self):
        f=fixture()
        self.assertEqual(self.run_one(f),self.run_one(f))
    def test_bootstrap_reproducibility(self):
        self.assertEqual(bootstrap(range(42)),bootstrap(range(42)))
        self.assertIsNone(bootstrap([1,2]))
    def test_metrics_no_invented_profit_factor(self):
        r=self.run_one()
        m=metrics(r)
        self.assertEqual(m["executed"],1)
        self.assertIsNone(m["sharpe_daily"])

class V3RegressionTests(unittest.TestCase):
    def test_original_msft_hash_and_exact_executions(self):
        from research_sr_v4.audit_v3 import run
        run()
        p=Path(__file__).resolve().parents[1]/"out/v3_independent_audit.json"
        audit=json.loads(p.read_text())
        self.assertTrue(audit["v3_reproduced"])
        self.assertEqual(audit["summary"]["net_pnl_usd"],-64.659109)

if __name__=="__main__":
    unittest.main()

