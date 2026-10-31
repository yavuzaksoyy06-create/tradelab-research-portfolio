"""Explicit v2 actions, replay/cache isolation and sanitized errors; simulated fixtures."""
from contextlib import redirect_stderr
from io import StringIO
import json
import tempfile
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest
from research_workspace.tests import test_ise_ml as fixtures
from research_workspace.ise_direction_v2 import evaluate_v2
from tools.ise_direction_v2_research import main

SCRIPT = "from research_workspace.ise_direction_v2_ui import render\nrender()"


class DirectionV2UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ISEMLTests.setUpClass()
        cls.frame, cls.meta = fixtures.ISEMLTests().pack()

    def setUp(self):
        original = st.get_option
        local = patch("research_workspace.ise_direction_v2_ui.st.get_option",
                      side_effect=lambda k: "127.0.0.1" if k == "server.address" else original(k))
        local.start()
        self.addCleanup(local.stop)

    def app(self):
        return AppTest.from_string(SCRIPT, default_timeout=60).run()

    def load(self, path):
        at = self.app()
        at.text_input(key="ise_v2_path").set_value(path)
        at.button(key="ise_v2_load").click().run()
        self.assertFalse(at.exception)
        return at

    def test_initial_and_nonlocal_display_never_loads_or_fits(self):
        with patch("research_workspace.ise_direction_v2_ui.read_snapshot") as read, \
             patch("research_workspace.ise_direction_v2_ui.evaluate_v2") as model:
            at = self.app()
            read.assert_not_called()
            model.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)
            with patch("research_workspace.ise_direction_v2_ui.st.get_option", return_value="0.0.0.0"):
                at = self.app()
                self.assertFalse(at.exception)
                self.assertEqual(len(at.text_input), 0)
                read.assert_not_called()

    def test_load_is_not_fit_and_inspector_cannot_refit_or_extend_replay(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_direction_v2_ui.read_snapshot", return_value=(self.frame.copy(), self.meta.copy())), \
             patch("research_workspace.ise_direction_v2_ui.evaluate_v2", wraps=evaluate_v2) as model:
            at = self.load(tmp)
            model.assert_not_called()
            self.assertEqual(at.slider(key="ise_v2_cursor").max, 428)
            at.slider(key="ise_v2_cursor").set_value(350).run()
            at.button(key="ise_v2_evaluate").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("plotly_chart")), 3)
            report = json.loads(at.json[0].value)
            self.assertEqual(report["evaluated_rows"], 29)
            self.assertFalse(report["fresh_independent_test"])
            self.assertFalse(report["holdout_scored"])
            self.assertFalse(report["orders_enabled"])
            at.selectbox(key="ise_v2_inspector").set_value(321).run()
            self.assertFalse(at.exception)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 3)
            at.slider(key="ise_v2_cursor").set_value(351).run()
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(model.call_count, 1)

    def test_tampered_cached_metric_is_rejected_before_display(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_direction_v2_ui.read_snapshot", return_value=(self.frame.copy(), self.meta.copy())):
            at = self.load(tmp)
            at.slider(key="ise_v2_cursor").set_value(325).run()
            at.button(key="ise_v2_evaluate").click().run()
            cached = at.session_state["ise_v2_cached_report"]
            cached[1]["metrics"]["logistic"]["directional_accuracy"] = .999
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.json), 0)
            self.assertTrue(any("V2_CACHE_REJECTED" in x.value for x in at.error))

    def test_rejected_path_and_provider_error_never_echo_private_content(self):
        with patch("research_workspace.ise_direction_v2_ui.read_snapshot") as read:
            at = self.load(r"\\server\share\SECRET")
            read.assert_not_called()
            self.assertTrue(any("V2_LOAD_REJECTED" in x.value for x in at.error))
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_direction_v2_ui.read_snapshot", side_effect=ValueError("SECRET_BODY")):
            at = self.load(tmp)
            self.assertNotIn("SECRET_BODY", " ".join(x.value for x in at.error))
            self.assertEqual(len(at.get("plotly_chart")), 0)

    def test_spec_drift_fails_before_source_loading(self):
        with patch("research_workspace.ise_direction_v2_ui.experiment_specification", side_effect=ValueError("PRIVATE_PATH")), \
             patch("research_workspace.ise_direction_v2_ui.read_snapshot") as read:
            at = self.app()
            self.assertFalse(at.exception)
            read.assert_not_called()
            self.assertTrue(any("V2_SPEC_REJECTED" in x.value for x in at.error))
            self.assertNotIn("PRIVATE_PATH", " ".join(x.value for x in at.error))

    def test_cli_errors_are_sanitized_and_no_collection_exists(self):
        output = StringIO()
        with patch("sys.argv", ["ise_direction_v2_research.py", "--snapshot", "SECRET_PATH"]), \
             patch("tools.ise_direction_v2_research.read_snapshot", side_effect=ValueError("SECRET_BODY")), \
             redirect_stderr(output):
            self.assertEqual(main(), 1)
        self.assertNotIn("SECRET", output.getvalue())
