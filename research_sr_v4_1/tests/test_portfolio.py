import copy,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
from research_sr_v4.data import expected_grid,DataQualityError
from research_sr_v4.causal import build_features,FeatureConfig
from research_sr_v4.execution import simulate as single
from research_sr_v4_1.data import validate_panel,load_cache,features_and_signals
from research_sr_v4_1.policy import PortfolioConfig,plan_entry
from research_sr_v4_1.portfolio import simulate,write_tables,SCHEMAS
from research_sr_v4_1.controls import matched_controls

def bars(start="2026-10-22",end=None):
    f=expected_grid(start,end or start)
    f["open"]=100.; f["high"]=100.2; f["low"]=99.9; f["close"]=100.; f["volume"]=1000.
    return f

def panel(symbols=("MSFT","SPY","QQQ"),start="2026-10-22",end=None):
    return {s:bars(start,end) for s in symbols}

def signal(p,s="MSFT",i=0,**kw):
    f=p[s]
    return {"symbol":s,"strategy":"touch","zone_id":"S1","signal_index":i,
            "known_at":str(f.bar_end.iloc[i]),"session":f.session.iloc[i],
            "lower":99.7,"upper":100.3,"atr":1.,"regime":"other","collision":False,**kw}

def candle(p,s,i,o,h,l,c):
    p[s].loc[i,["open","high","low","close"]]=[o,h,l,c]

class AccountingTests(unittest.TestCase):
    def run_three(self,cfg=PortfolioConfig()):
        p=panel()
        return simulate(p,[signal(p,s) for s in p],cfg)
    def test_cash_plus_marks_and_realized_unrealized(self):
        r=self.run_three()
        for e in r["equity"]:
            self.assertAlmostEqual(e["cash"]+e["market_value"],e["equity"])
            self.assertAlmostEqual(100000+e["realized_pnl"]+e["unrealized_pnl"],e["equity"])
    def test_trade_and_cash_flow_reconciliation(self):
        r=self.run_three()
        self.assertAlmostEqual(r["final_equity"],100000+sum(t["net_pnl"] for t in r["trades"]))
        self.assertAlmostEqual(r["final_equity"],100000+sum(c["cash_flow"] for c in r["cash"]))
    def test_fees_exactly_once(self):
        r=self.run_three(replace(PortfolioConfig(),fee_bps=10))
        self.assertAlmostEqual(sum(c["fee"] for c in r["cash"]),
            sum(t["entry_fee"]+t["exit_fee"] for t in r["trades"]))
        for t in r["trades"]:
            self.assertAlmostEqual(t["net_pnl"],t["quantity"]*(t["exit_price"]-t["entry_price"])-t["entry_fee"]-t["exit_fee"])
    def test_no_negative_cash_whole_shares(self):
        r=self.run_three()
        self.assertTrue(all(x["cash"]>=0 for x in r["equity"]))
        self.assertTrue(all(type(t["quantity"]) is int and t["quantity"]>0 for t in r["trades"]))
    def test_symbol_and_planned_risk_caps(self):
        for t in self.run_three()["trades"]:
            self.assertLessEqual(t["quantity"]*t["entry_price"],.1*t["equity_at_entry"]+1e-7)
            self.assertLessEqual(t["planned_risk"],.005*t["equity_at_entry"]+1e-7)
    def test_aggregate_post_cost_cap(self):
        r=self.run_three(replace(PortfolioConfig(),aggregate_exposure_cap=.15))
        self.assertTrue(all(d["exposure_after"]<=.15+1e-10 for d in r["decisions"] if d["status"]=="executed"))
        self.assertIn("aggregate_exposure_cap",[d["status"] for d in r["decisions"]])
    def test_mark_to_market_cap_movement_is_reported(self):
        p=panel()
        for s in p:
            candle(p,s,1,100,150,99.9,149)
        r=simulate(p,[signal(p,s) for s in p],
                   replace(PortfolioConfig(),reward_risk=1000))
        self.assertTrue(any(x["event"]=="mark_to_market_exposure_breach" for x in r["risk_events"]))
    def test_insufficient_cash_planner_stress(self):
        p=panel()
        plan,reason=plan_entry(100,signal(p),100000,50,0,PortfolioConfig())
        self.assertIsNone(plan)
        self.assertEqual(reason,"insufficient_cash")
    def test_tiny_capital_three_competitors(self):
        r=self.run_three(replace(PortfolioConfig(),initial_capital=1))
        self.assertFalse(r["trades"])
        self.assertTrue(all(d["status"]=="symbol_notional_cap" for d in r["decisions"]))
    def test_zero_reservations_explained(self):
        self.assertTrue(all(x["reserved_cash"]==0 and x["buying_power"]==x["cash"] for x in self.run_three()["equity"]))
    def test_empty_schemas(self):
        r=simulate(panel(),[])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/"out") as tmp:
            write_tables(r,tmp)
            for name,columns in SCHEMAS.items():
                self.assertEqual(pd.read_csv(Path(tmp)/f"portfolio_{name}.csv").columns.tolist(),columns)

class TimingTests(unittest.TestCase):
    def test_simultaneous_msft_qqq(self):
        p=panel()
        r=simulate(p,[signal(p,"QQQ"),signal(p,"MSFT")])
        entries=[e["symbol"] for e in r["ledger"] if e["action"]=="entry"]
        self.assertEqual(entries,["MSFT","QQQ"])
    def test_dictionary_and_signal_order_independent(self):
        p=panel()
        ss=[signal(p,s) for s in p]
        a=simulate(p,ss)
        b=simulate(dict(reversed(list(p.items()))),list(reversed(ss)))
        self.assertEqual(a,b)
    def test_gap_exit_releases_position_slot_at_open(self):
        p=panel()
        candle(p,"MSFT",2,105,106,104,105)
        r=simulate(p,[signal(p),signal(p,"QQQ",1)],replace(PortfolioConfig(),max_positions=1))
        self.assertTrue(all(d["status"]=="executed" for d in r["decisions"]))
        q=[x for x in r["ledger"] if x["timestamp"]==str(p["MSFT"].timestamp.iloc[2])]
        self.assertEqual([x["action"] for x in q],["exit","entry"])
    def test_intrabar_exit_does_not_release_open_capacity(self):
        p=panel()
        candle(p,"MSFT",2,100,105,99.9,104)
        r=simulate(p,[signal(p),signal(p,"QQQ",1)],replace(PortfolioConfig(),max_positions=1))
        self.assertEqual(r["decisions"][1]["status"],"position_count_cap")
    def test_multiple_independent_exits(self):
        p=panel()
        for s in p:
            candle(p,s,2,95,96,94,95)
        r=simulate(p,[signal(p,s) for s in p])
        self.assertEqual([t["reason"] for t in r["trades"]],["gap_stop"]*3)
    def test_no_same_symbol_duplicate_position(self):
        p=panel()
        r=simulate(p,[signal(p),signal(p,i=1,zone_id="S2")])
        self.assertEqual(r["decisions"][1]["status"],"position_already_open")
    def test_duplicate_signal_and_multizone(self):
        p=panel()
        a=simulate(p,[signal(p),signal(p)])
        self.assertEqual(len(a["trades"]),1)
        self.assertIn("duplicate_signal",[d["status"] for d in a["decisions"]])
        b=simulate(p,[signal(p),signal(p,zone_id="S2")])
        self.assertTrue(all(d["status"]=="multi_zone_collision" for d in b["decisions"]))
    def test_no_fill_before_confirmation(self):
        p=panel()
        r=simulate(p,[signal(p,known_at=str(p["MSFT"].timestamp.iloc[0]))])
        self.assertEqual(r["decisions"][0]["status"],"invalid_signal")
    def test_last_bar_no_next_session_fill(self):
        p=panel(start="2026-10-21",end="2026-10-22")
        r=simulate(p,[signal(p,i=25)])
        self.assertEqual(r["decisions"][0]["status"],"no_next_same_session_bar")
    def test_real_exchange_close(self):
        p=panel()
        r=simulate(p,[signal(p,i=24)])
        self.assertEqual(r["trades"][0]["reason"],"exchange_session_close")
        self.assertEqual(r["trades"][0]["exit_known_by"],str(p["MSFT"].session_close.iloc[-1]))
    def test_cross_symbol_future_cannot_finance_entry(self):
        p=panel()
        ss=[signal(p),signal(p,"QQQ",1)]
        cfg=replace(PortfolioConfig(),aggregate_exposure_cap=.10)
        a=simulate(p,ss,cfg)
        candle(p,"MSFT",2,100,1000,99.9,999)
        b=simulate(p,ss,cfg)
        self.assertEqual(a["decisions"],b["decisions"])
    def test_stop_before_later_rebound_excursions(self):
        p=panel()
        candle(p,"MSFT",1,100,105,90,100)
        candle(p,"MSFT",2,100,1000,99,900)
        t=simulate(p,[signal(p)])["trades"][0]
        self.assertIsNone(t["mfe_exact"])
        self.assertEqual(t["exit_index"],1)
        self.assertLess(t["observed_mfe"],6)
        self.assertLess(t["mae_lower"],t["mae_upper"])
        self.assertTrue(t["collision_adverse_first"])
    def test_gap_profit_uses_observed_open(self):
        p=panel()
        candle(p,"MSFT",2,105,106,104,105)
        t=simulate(p,[signal(p)])["trades"][0]
        self.assertEqual(t["raw_exit"],105)
        self.assertEqual(t["reason"],"gap_target_open")

class RiskTests(unittest.TestCase):
    def test_simultaneous_gap_breaches_and_block(self):
        p=panel()
        for s in ["MSFT","QQQ"]:
            candle(p,s,2,70,71,69,70)
        r=simulate(p,[signal(p),signal(p,"QQQ"),signal(p,"SPY",1)])
        self.assertEqual(r["decisions"][-1]["status"],"daily_drawdown_block")
        self.assertEqual(sum(x["event"]=="daily_drawdown_breach" for x in r["risk_events"]),1)
        self.assertTrue(all(-t["net_pnl"]>t["planned_risk"] for t in r["trades"]))
    def test_reset_at_next_session(self):
        p=panel(start="2026-10-21",end="2026-10-22")
        candle(p,"MSFT",2,70,71,69,70)
        r=simulate(p,[signal(p),signal(p,i=26,zone_id="S2")])
        self.assertEqual(len(r["trades"]),2)
        self.assertTrue(all(x["positions"]==0 for x in r["equity"] if x["phase"]=="close" and x["timestamp"].endswith("20:00:00+00:00")))
    def test_close_breach_liquidates_only_next_open(self):
        p=panel()
        # Wide stop permits a mark loss without a stop; threshold deliberately tightened.
        candle(p,"MSFT",1,100,100.2,98,98.1)
        candle(p,"MSFT",2,97,98,96,97)
        cfg=replace(PortfolioConfig(),daily_drawdown=.0001)
        r=simulate(p,[signal(p,lower=95,upper=100.3,atr=1)],cfg)
        self.assertEqual(r["trades"][0]["reason"],"daily_drawdown_next_open")
        self.assertEqual(r["trades"][0]["raw_exit"],97)
    def test_config_validation(self):
        for change in [{"aggregate_exposure_cap":.31},{"max_positions":4},{"allocation_order":("QQQ","MSFT","SPY")},
                       {"fee_bps":float("nan")}]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                replace(PortfolioConfig(),**change)

class DataAndCausalityTests(unittest.TestCase):
    def test_missing_candle_aborts_entire_portfolio(self):
        p=panel(); p["QQQ"]=p["QQQ"].drop(index=2)
        with self.assertRaises(DataQualityError):
            simulate(p,[signal(p)])
    def test_duplicate_timestamp(self):
        p=panel(); p["SPY"]=pd.concat([p["SPY"].iloc[:1],p["SPY"]],ignore_index=True)
        with self.assertRaises(DataQualityError):
            simulate(p,[])
    def test_wrong_timestamp_order(self):
        p=panel(); p["QQQ"]=p["QQQ"].iloc[::-1]
        with self.assertRaises(DataQualityError):
            simulate(p,[])
    def test_timezone_mismatch(self):
        p=panel(); p["SPY"]["timestamp"]=p["SPY"].timestamp.dt.tz_localize(None)
        with self.assertRaises(DataQualityError):
            simulate(p,[])
    def test_dst_holiday_and_early_close(self):
        self.assertEqual(len(expected_grid("2026-12-25","2026-12-25")),0)
        self.assertEqual(len(expected_grid("2026-11-27","2026-11-27")),14)
        self.assertEqual(expected_grid("2026-03-06","2026-03-06").timestamp.iloc[0].hour,14)
        self.assertEqual(expected_grid("2026-03-09","2026-03-09").timestamp.iloc[0].hour,13)
    def test_incomplete_bar_rejected(self):
        with self.assertRaises(DataQualityError):
            simulate(panel(),[],now="2026-10-22T14:00Z")
    def test_single_symbol_v4_regression(self):
        p=panel(("MSFT",)); sig=signal(p)
        a=simulate(p,[sig])
        b=single(p["MSFT"],[sig])
        self.assertAlmostEqual(a["final_equity"],b["final_equity"])
        self.assertEqual(a["trades"][0]["quantity"],b["trades"][0]["quantity"])
    def test_prefix_features_adversarial_future(self):
        f=bars("2026-10-01","2026-10-22")
        x=np.arange(len(f))
        f["close"]=100+np.sin(x*.4); f["open"]=f.close-.1; f["low"]=f.close-.4; f["high"]=f.close+.4
        a=build_features(f.iloc[:200])
        f.loc[200:,["open","high","low","close"]]*=10
        b=build_features(f)
        self.assertEqual(a["snapshots"],b["snapshots"][:200])
        self.assertEqual(a["signals"],[s for s in b["signals"] if s["signal_index"]<200])
    def test_matched_control_seed_and_future_independence(self):
        p=panel(); anchors=[signal(p,i=i,zone_id=f"S{i}") for i in [0,4,8]]
        a=matched_controls(p,anchors,11)
        self.assertEqual(a,matched_controls(p,anchors,11))
        for s,anchor in zip(a,anchors):
            self.assertGreaterEqual(s["signal_index"],anchor["signal_index"])
            self.assertEqual(s["signal_index"]//4,anchor["signal_index"]//4)
            self.assertEqual(s["session"],anchor["session"])
        p["MSFT"].loc[20:,["open","high","low","close"]]*=10
        self.assertEqual(a,matched_controls(p,anchors,11))
    def test_frozen_hashes_and_actual_data(self):
        p,m=load_cache()
        self.assertTrue(all(len(f)==3692 for f in p.values()))
        self.assertTrue(all(x["adjustment"]=="split" and x["feed"]=="sip" for x in m.values()))
    def test_repeatability(self):
        p=panel()
        ss=[signal(p,s) for s in p]
        self.assertEqual(simulate(p,ss),simulate(p,ss))

if __name__=="__main__":
    unittest.main()


