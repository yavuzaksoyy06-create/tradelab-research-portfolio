import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
import pandas as pd
from research_terminal.adapter import Store,integrity,BASE,ROOT,PROTOCOL_HASH
from research_terminal.replay import Replay,ENTRY_FIELDS
from research_terminal.intake import validate_manifest
from research_sr_v4.causal import build_features
from research_sr_v4.data import expected_grid,validate
from research_sr_v4_1.portfolio import simulate,SCHEMAS

class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store=Store()
        cls.experiment=cls.store.run()
        cls.replay=Replay(cls.store,cls.experiment)

    def state_at(self,index,store=None,run=None):
        replay=Replay(store or self.store,run or self.experiment)
        session=replay.clock.iloc[index].session
        first,count=replay.bounds(session)
        return replay.state("SPY",session,index-first+1)

    def test_open_has_no_session_candles(self):
        s=self.replay.state("SPY","2026-08-25",0)
        self.assertFalse((s["bars"].session=="2026-08-25").any())
        self.assertEqual(s["equity"]["cash"],100000)

    def test_one_candle(self):
        s=self.replay.state("SPY","2026-08-25",1)
        self.assertEqual(sum(s["bars"].session=="2026-08-25"),1)
        self.assertEqual(str(s["bars"].bar_end.iloc[-1]),s["timestamp"])

    def test_same_timestamp_next_open_hidden(self):
        d=self.experiment["decisions"].iloc[0]
        s=self.state_at(int(d.signal_index))
        row=next(x for x in s["decisions"] if x["decision_id"]==d.decision_id)
        self.assertEqual(row["status"],"pending_next_open")
        self.assertIsNone(row["equity_before"])
        self.assertEqual(pd.Timestamp(d.decision_at),pd.Timestamp(s["timestamp"]))
        later=self.state_at(int(d.signal_index)+1)
        row=next(x for x in later["decisions"] if x["decision_id"]==d.decision_id)
        self.assertEqual(row["status"],d.status)

    def test_future_trade_result_hidden(self):
        candidates=self.experiment["trades"].query("exit_index > entry_index")
        t=candidates.iloc[0]
        s=self.state_at(int(t.entry_index))
        trade=next(x for x in s["trades"] if x["entry_index"]==t.entry_index and x["symbol"]==t.symbol)
        self.assertEqual(trade["status"],"open")
        for field in ["net_pnl","exit_at","exit_price","r_multiple","trade_id","bars_held","observed_mfe"]:
            self.assertNotIn(field,trade)

    def test_future_outcome_mutation_does_not_change_state(self):
        t=self.experiment["trades"].query("exit_index > entry_index").iloc[0]
        index=int(t.entry_index)
        altered=dict(self.experiment)
        altered["trades"]=self.experiment["trades"].copy()
        mask=altered["trades"].exit_index>index
        altered["trades"].loc[mask,["exit_price","net_pnl","r_multiple"]]=999999
        a=self.state_at(index)["trades"]
        b=self.state_at(index,run=altered)["trades"]
        self.assertEqual(a,b)

    def test_future_candle_mutation_recomputes_causal_features(self):
        index=2700
        frame=self.store.panel["SPY"].copy()
        frame.loc[index+1:,["open","high","low","close"]]*=1.7
        frame.loc[index+1:,"volume"]*=4
        changed=build_features(frame)
        original=self.store.features["SPY"]
        self.assertEqual(original["snapshots"][:index+1],changed["snapshots"][:index+1])
        self.assertEqual([s for s in original["signals"] if s["signal_index"]<=index],
                         [s for s in changed["signals"] if s["signal_index"]<=index])
        store=SimpleNamespace(panel={**self.store.panel,"SPY":frame},features={**self.store.features,"SPY":changed})
        a,b=self.state_at(index),self.state_at(index,store=store)
        for key in ["snapshot","pivots","lifecycle","signals","trades","decisions","equity"]:
            self.assertEqual(a[key],b[key])
        pd.testing.assert_frame_equal(a["bars"],b["bars"])

    def test_future_candles_cannot_change_earlier_portfolio(self):
        index=2700
        panel={s:f.copy() for s,f in self.store.panel.items()}
        for f in panel.values():
            f.loc[index+1:,["open","high","low","close"]]*=1.1
        features={s:build_features(f) for s,f in panel.items()}
        signals=[{"symbol":s,**x} for s,v in features.items() for x in v["signals"]
                 if x["strategy"]=="touch" and "2026-08-25"<=x["session"]<="2026-10-22"]
        result=simulate(panel,signals,start="2026-08-25",end="2026-10-22")
        run={**self.experiment,**{k:pd.DataFrame(result[k],columns=cols) for k,cols in SCHEMAS.items()},"signals":signals}
        a,b=self.state_at(index),self.state_at(index,run=run)
        self.assertAlmostEqual(a["equity"]["cash"],b["equity"]["cash"],places=8)
        self.assertAlmostEqual(a["equity"]["equity"],b["equity"]["equity"],places=8)
        pd.testing.assert_frame_equal(a["ledger"],b["ledger"],check_dtype=False)

    def test_confirmation_not_early(self):
        s=self.state_at(2700)
        self.assertTrue(all(p["confirmed_index"]<=2700 for p in s["pivots"]))
        self.assertTrue(all(pd.Timestamp(p["confirmed_at"])<=pd.Timestamp(s["timestamp"]) for p in s["pivots"]))

    def test_all_symbols_share_clock(self):
        for f in self.store.panel.values():
            self.assertEqual(f.timestamp.tolist(),self.replay.clock.timestamp.tolist())

    def test_session_end_bounds(self):
        for session in self.replay.sessions():
            first,count=self.replay.bounds(session)
            s=self.replay.state("SPY",session,count)
            self.assertEqual(pd.Timestamp(s["timestamp"]),self.replay.clock.iloc[first].session_close)

    def test_invalid_selection(self):
        for symbol,session,cursor in [("BAD","2026-08-25",0),("SPY","2026-08-23",0),
                                      ("SPY","2026-08-25",27),("SPY","2026-08-25",-1)]:
            with self.assertRaises(ValueError):self.replay.state(symbol,session,cursor)

    def test_dst_and_early_close(self):
        grid=expected_grid("2026-10-30","2026-11-27")
        self.assertEqual(grid[grid.session=="2026-10-30"].timestamp.iloc[0].hour,13)
        self.assertEqual(grid[grid.session=="2026-11-02"].timestamp.iloc[0].hour,14)
        self.assertEqual(len(grid[grid.session=="2026-11-27"]),14)

    def test_unfinished_bars_rejected(self):
        f=self.store.panel["SPY"].query("session == '2026-08-25'")
        with self.assertRaises(ValueError):
            validate(f,"2026-08-25","2026-08-25",now="2026-08-25T19:59Z")

    def test_empty_trade_experiment(self):
        run=self.store.run("validation_diagnostic","trend_filtered")
        self.assertTrue(run["trades"].empty)
        state=Replay(self.store,run).state("SPY","2026-07-14",1)
        self.assertEqual(state["trades"],[])

    def test_journal_ids_unique_stable(self):
        s=self.state_at(2800)
        a=self.replay.journal(s)
        self.assertEqual(a,self.replay.journal(s))
        self.assertEqual(len(a),len({e["event_id"] for e in a}))
        self.assertTrue(all(e["protocol_sha256"]==PROTOCOL_HASH for e in a))

    def test_accounting_reconciliation(self):
        for index in [2600,2650,2700,2800,3691]:
            state=self.state_at(index)
            e=state["equity"]
            self.assertAlmostEqual(e["cash"]+e["market_value"],e["equity"],places=7)
            self.assertAlmostEqual(100000+e["realized_pnl"]+e["unrealized_pnl"],e["equity"],places=7)
            self.assertAlmostEqual(state["positions"].market_value.sum(),e["market_value"],places=7)
            self.assertFalse(state["positions"].symbol.duplicated().any())

    def test_export_schema(self):
        for k,cols in SCHEMAS.items():self.assertEqual(list(self.experiment[k].columns),cols)

    def test_missing_cache_fails_closed(self):
        with patch("research_terminal.adapter.load_cache",side_effect=FileNotFoundError("Missing cached dataset")):
            with self.assertRaises(FileNotFoundError):Store()

    def test_frozen_config_rejects_mutation(self):
        from research_terminal import adapter
        real=adapter.read_json
        def modified(path):
            value=real(path)
            if str(path).endswith("PORTFOLIO_EXPERIMENT_CONFIG.json"):
                value["source_sha256"]["research_sr_v4\\causal.py"]="bad"
            return value
        with patch("research_terminal.adapter.read_json",side_effect=modified):
            with self.assertRaises(ValueError):integrity()

    def test_future_gate_closed(self):
        r=validate_manifest(now="2026-10-23T22:00Z")
        self.assertFalse(r["time_gate_passed"])
        self.assertFalse(r["evaluated"])
        self.assertFalse(r["ready"])

    def test_time_alone_never_authorizes_evaluation(self):
        r=validate_manifest(now="2027-01-21T21:15Z")
        self.assertTrue(r["time_gate_passed"])
        self.assertFalse(r["ready"])
        self.assertFalse(r["evaluated"])
        self.assertIn("No versioned dataset manifest supplied",r["errors"])

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):validate_manifest(now="2027-01-21")


    def test_every_saved_variant_has_joinable_signal_evidence(self):
        for period in ("training_diagnostic","validation_diagnostic","observed_replay"):
            for variant in self.store.variants(period):
                run=self.store.run(period,variant)
                replay=Replay(self.store,run)
                for d in run["decisions"].to_dict("records"):
                    key=(d["symbol"],d["signal_index"],d["zone_id"],d["strategy"])
                    self.assertIn(key,replay.signal_map,(period,variant,key))
                self.assertAlmostEqual(run["metrics"]["net_pnl"],run["trades"].net_pnl.sum(),places=7)

if __name__=="__main__":unittest.main()



