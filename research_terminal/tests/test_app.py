import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
import streamlit as st
from research_terminal.adapter import ROOT,Store
from research_terminal.replay import Replay
from research_terminal.charts import market

class DashboardTests(unittest.TestCase):
    def app(self):
        return AppTest.from_file(str(ROOT/"app.py"),default_timeout=45).run()
    def test_overview_and_all_pages(self):
        at=self.app()
        self.assertFalse(at.exception)
        for page in ["Market Intelligence","Strategy Lab","Portfolio & Risk","Research Audit"]:
            at.radio(key="page").set_value(page).run(timeout=45)
            self.assertFalse(at.exception,[(x.message) for x in at.exception])
            self.assertEqual(at.title[0].value,page)
    def test_replay_step_jump_reset(self):
        at=self.app()
        at.radio(key="page").set_value("Market Intelligence").run()
        self.assertEqual(at.session_state["cursor"],0)
        next(b for b in at.button if b.label=="+1 candle").click().run()
        self.assertEqual(at.session_state["cursor"],1)
        next(b for b in at.button if b.label=="+4 candles").click().run()
        self.assertEqual(at.session_state["cursor"],5)
        at.select_slider(key="cursor").set_value(26).run()
        self.assertEqual(at.session_state["cursor"],26)
        next(b for b in at.button if b.label=="+1 candle").click().run()
        self.assertEqual(at.session_state["cursor"],26)
        next(b for b in at.button if b.label=="Reset to open").click().run()
        self.assertEqual(at.session_state["cursor"],0)
        self.assertFalse(at.exception)
    def test_no_trades_ui(self):
        at=self.app()
        at.selectbox(key="period").set_value("validation_diagnostic").run()
        at.selectbox(key="variant").set_value("trend_filtered").run()
        at.radio(key="page").set_value("Portfolio & Risk").run()
        self.assertFalse(at.exception)
        self.assertTrue(any("No simulated trades" in x.value for x in at.info))
    def test_loading_error_is_explicit(self):
        st.cache_resource.clear()
        try:
            with patch("research_terminal.adapter.Store",side_effect=FileNotFoundError("Missing cached dataset")):
                at=self.app()
            self.assertFalse(at.exception)
            self.assertTrue(any("Missing cached dataset" in e.value for e in at.error))
        finally:
            st.cache_resource.clear()
    def test_hindsight_opt_in(self):
        at=self.app()
        at.radio(key="page").set_value("Market Intelligence").run()
        self.assertFalse(at.checkbox(key="hindsight").value)
        at.checkbox(key="hindsight").check().run()
        self.assertTrue(any("RETROSPECTIVE" in x.value for x in at.warning))

class ChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store=Store()
        cls.replay=Replay(cls.store,cls.store.run())
    def test_empty_chart(self):
        state=self.replay.state("SPY","2026-08-25",0)
        state["bars"]=state["bars"].iloc[:0]
        fig=market(state)
        self.assertEqual(len(fig.data),0)
        self.assertTrue(fig.layout.annotations)
    def test_missing_optional_markers(self):
        state=self.replay.state("SPY","2026-08-25",1)
        state.update(pivots=[],signals=[],decisions=[],trades=[])
        self.assertGreater(len(market(state).data),0)
    def test_chart_bounds_and_confirmations(self):
        state=self.replay.state("SPY","2026-08-26",13)
        fig=market(state,50)
        cutoff=state["index"]
        for trace in fig.data:
            self.assertTrue(all(x is None or x<=cutoff for x in trace.x))
        for shape in fig.layout.shapes:
            self.assertLessEqual(shape.x1,cutoff)
        # All rectangles have bounds that actually existed at their left endpoint.
        for shape in fig.layout.shapes:
            if shape.type!="rect":continue
            snap=state["snapshots"][int(shape.x0)]
            self.assertTrue(any(z["lower"]==shape.y0 and z["upper"]==shape.y1 for z in snap["zones"]))

