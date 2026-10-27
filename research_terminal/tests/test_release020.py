"""Causal coordinates, inspector evidence and UI regression for release 0.2.0."""
import copy
import json
import unittest
import pandas as pd
from streamlit.testing.v1 import AppTest
from research_terminal.adapter import Store,ROOT
from research_terminal.replay import Replay
from research_terminal.charts import market,clock_label,MARKERS
from research_terminal.inspection import events_at,inspect_event,matched_trade,next_recorded_cursor,display_values
from research_sr_v4.data import expected_grid

class Release020Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store=Store();cls.experiment=cls.store.run();cls.replay=Replay(cls.store,cls.experiment)
    def state(self,index=None):
        if index is None:return self.replay.state("SPY","2026-08-26",13)
        session=self.replay.clock.iloc[index].session;first,_=self.replay.bounds(session)
        return self.replay.state("SPY",session,index-first+1)
    def trace(self,fig,role):return next(t for t in fig.data if t.meta and t.meta.get("role")==role)
    def test_candles_volume_atr_alignment(self):
        state=self.state();fig=market(state,100)
        candles=self.trace(fig,"candles");volume=self.trace(fig,"volume");atr=self.trace(fig,"atr")
        self.assertTrue(all(b-a==1 for a,b in zip(candles.x,candles.x[1:])))
        self.assertEqual(list(candles.x),list(volume.x))
        self.assertEqual(list(volume.y),state["bars"].tail(100).volume.tolist())
        for i,y in zip(atr.x,atr.y):
            if i is not None:self.assertEqual(y,state["snapshots"][i]["atr"])
        self.assertIn(None,atr.x);self.assertFalse(atr.connectgaps)
    def test_dst_early_close_weekend_ordinal_axis(self):
        bars=expected_grid("2026-10-30","2026-11-27")
        for k,v in {"open":100.,"high":101.,"low":99.,"close":100.5,"volume":50}.items():bars[k]=v
        snapshots=[{"atr":1.,"zones":[],"known_at":str(t)} for t in bars.bar_end]
        state={"bars":bars,"snapshots":snapshots,"snapshot":snapshots[-1],"pivots":[],
               "symbol":"SPY","session":"2026-11-27","index":len(bars)-1}
        fig=market(state,len(bars));c=self.trace(fig,"candles")
        self.assertEqual(list(c.x),list(range(len(bars))))
        self.assertEqual(len(bars.query("session == '2026-11-27'")),14)
        self.assertIn("09:45 EDT",clock_label(bars.bar_end.iloc[0]))
        self.assertIn("09:45 EST",clock_label(bars.query("session == '2026-11-02'").bar_end.iloc[0]))
        self.assertIn("13:00 EST",clock_label(bars.bar_end.iloc[-1]))
    def test_rectangles_use_known_bounds_and_pivots_use_confirmation(self):
        state=self.state();fig=market(state)
        for shape in fig.layout.shapes:
            self.assertLessEqual(shape.x1,state["index"])
            if shape.type=="rect":
                self.assertTrue(any(z["id"]==shape.name and z["lower"]==shape.y0 and z["upper"]==shape.y1
                                    for z in state["snapshots"][shape.x0]["zones"]))
        trace=self.trace(fig,"pivot")
        expected=[p["confirmed_index"] for p in state["pivots"] if state["index"]-99<=p["confirmed_index"]<=state["index"]]
        self.assertEqual(list(trace.x),expected)
    def test_marker_identity_and_highlight(self):
        state=self.state();events=events_at(self.replay,state);event=events[-1]
        fig=market(state,events=events,selected=event["event_id"])
        self.assertEqual(len(MARKERS),len({v[1] for v in MARKERS.values()}))
        trace=next(t for t in fig.data if t.meta and t.meta.get("role")=="event" and event["event_id"] in t.customdata)
        self.assertEqual(trace.marker.size[list(trace.customdata).index(event["event_id"])],17)
        self.assertIn(event["event_id"],trace.text[list(trace.customdata).index(event["event_id"])])
    def test_opening_entry_uses_entry_bar_not_prior_close(self):
        state=self.state();events=events_at(self.replay,state)
        e=next(e for e in events if e["kind"]=="accepted_entry")
        t=matched_trade(e,state)
        self.assertEqual(e["known_index"],t["entry_index"])
        self.assertGreater(pd.Timestamp(e["observable_at"]),pd.Timestamp(e["timestamp"]))
    def test_visibility_switches(self):
        fig=market(self.state(),visibility={k:False for k in ("zones","pivots","execution","rejected","signals","atr","volume")})
        self.assertEqual(len(fig.data),1)
        self.assertFalse(any(s.type=="rect" for s in fig.layout.shapes))
    def test_inspector_recorded_bar_and_portfolio(self):
        state=self.state();event=events_at(self.replay,state)[-1];detail=inspect_event(event,state,self.replay)
        self.assertEqual(detail["market_evidence"]["completed_bar"]["close"],state["bars"].loc[event["known_index"],"close"])
        self.assertEqual(detail["risk_assessment"]["cursor_portfolio"],state["equity"])
        self.assertTrue(all(e["seq"]<=state["equity"]["seq"] for e in detail["ledger"]))
    def test_partial_evidence_does_not_invent_fields(self):
        state=self.state();event=copy.deepcopy(events_at(self.replay,state)[0])
        event["payload"]={}
        detail=display_values(inspect_event(event,state,self.replay))
        self.assertEqual(detail["signal_evaluation"]["rule"],"Not recorded / Unavailable")
        self.assertEqual(detail["simulated_execution"],"Not recorded / Unavailable")
    def test_no_future_outcome_in_inspector(self):
        t=self.experiment["trades"].query("symbol == 'SPY' and exit_index > entry_index").iloc[0]
        state=self.state(int(t.entry_index));event=next(e for e in events_at(self.replay,state)
            if e["kind"]=="accepted_entry" and e["known_index"]==int(t.entry_index))
        detail=inspect_event(event,state,self.replay)
        self.assertIsNotNone(detail["simulated_execution"])
        for key in ("exit_price","net_pnl","r_multiple","reason","exit_index","trade_id"):
            self.assertNotIn(key,detail["simulated_execution"])
    def test_stop_target_boundaries(self):
        state=self.state();t=next(t for t in state["trades"] if t["symbol"]=="SPY")
        fig=market(state,selected_trade=t)
        lines=[s for s in fig.layout.shapes if str(s.name).startswith("planned_")]
        self.assertEqual(len(lines),2)
        for line in lines:
            self.assertGreaterEqual(line.x0,t["entry_index"])
            self.assertLessEqual(line.x1,min(state["index"],t.get("exit_index",state["index"])))
    def test_next_event_stays_in_session(self):
        for kind in ("signal","trade"):
            cursor=next_recorded_cursor(self.replay,"SPY","2026-08-26",0,kind)
            self.assertGreater(cursor,0);self.assertLessEqual(cursor,26)
            self.assertEqual(next_recorded_cursor(self.replay,"SPY","2026-08-26",26,kind),26)
    def test_no_future_event_marker(self):
        state=self.state();events=events_at(self.replay,state)
        self.assertTrue(all(e["known_index"]<=state["index"] for e in events))
        fig=market(state,events=events)
        self.assertTrue(all(x is None or x<=state["index"] for t in fig.data for x in t.x))

class InspectorUITests(unittest.TestCase):
    def app(self):
        at=AppTest.from_file(str(ROOT/"app.py"),default_timeout=60).run()
        at.radio(key="page").set_value("Market Intelligence").run()
        at.selectbox(key="symbol").set_value("SPY").run()
        at.selectbox(key="session").set_value("2026-08-26").run()
        return at
    def test_event_selection_preserves_cursor_and_changes_evidence(self):
        at=self.app();at.select_slider(key="cursor").set_value(13).run()
        self.assertFalse(at.exception)
        initial=at.selectbox(key="inspector_event").value
        replay=Replay(Store(),Store().run())
        events=events_at(replay,replay.state("SPY","2026-08-26",13))
        another=next(e["event_id"] for e in events if e["event_id"]!=initial and e["known_index"]>=replay.bounds("2026-08-26")[0])
        at.selectbox(key="inspector_event").set_value(another).run()
        self.assertEqual(at.session_state["cursor"],13)
        self.assertTrue(any(another in str(j.value) for j in at.json))
        self.assertFalse(at.exception)
    def test_previous_jump_reset_and_no_event_state(self):
        at=self.app()
        next(b for b in at.button if b.label=="Next simulated trade").click().run()
        self.assertGreater(at.session_state["cursor"],0)
        self.assertTrue(any('accepted_entry' in str(j.value) and at.session_state["inspector_event"] in str(j.value) for j in at.json))
        cursor=at.session_state["cursor"]
        next(b for b in at.button if b.label=="Previous candle").click().run()
        self.assertEqual(at.session_state["cursor"],cursor-1)
        at.text_input(key="event_search").set_value("never-matches-event").run()
        self.assertEqual(len([s for s in at.selectbox if s.key=="inspector_event"]),0)
        next(b for b in at.button if b.label=="Reset to open").click().run()
        next(b for b in at.button if b.label=="Previous candle").click().run()
        self.assertEqual(at.session_state["cursor"],0);self.assertFalse(at.exception)

