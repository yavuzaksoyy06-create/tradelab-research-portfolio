"""Historical ML UI mechanics on simulated returns, never claimed market results."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from research_workspace.ise_ml import COLUMNS, SOURCE_URL, evaluate, load_csv


SCRIPT = "from research_workspace.ise_ml_ui import render\nrender()"


class ISEMLUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(19)
        raw = pd.DataFrame(rng.normal(0, .01, (536, 9)), columns=COLUMNS[1:])
        raw.insert(0, "date", pd.bdate_range("2009-01-05", periods=536))
        payload = raw.to_csv(index=False).encode()
        cls.frame, cls.meta = load_csv(payload, {"source_id": "uci247", "license": "CC-BY-4.0",
                                                "source_url": SOURCE_URL,
                                                "csv_sha256": hashlib.sha256(payload).hexdigest()})

    def setUp(self):
        original = st.get_option
        local = patch("research_workspace.ise_ml_ui.st.get_option",
                      side_effect=lambda name: "127.0.0.1" if name == "server.address" else original(name))
        local.start()
        self.addCleanup(local.stop)

    def app(self):
        return AppTest.from_string(SCRIPT, default_timeout=60).run()

    def load(self, at, path):
        at.text_input(key="ise_snapshot_path").set_value(path)
        at.button(key="ise_load").click().run()
        self.assertFalse(at.exception)

    def test_initial_render_does_not_read_or_evaluate(self):
        with patch("research_workspace.ise_ml_ui.read_snapshot") as read, \
             patch("research_workspace.ise_ml_ui.evaluate") as model:
            at = self.app()
            self.assertFalse(at.exception)
            self.assertIn("İstanbul Endeksi · Makine Öğrenmesi", [h.value for h in at.subheader])
            read.assert_not_called()
            model.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)

    def test_nonloopback_bind_exposes_no_private_input_or_backend(self):
        original = st.get_option
        with patch("research_workspace.ise_ml_ui.st.get_option",
                   side_effect=lambda name: "0.0.0.0" if name == "server.address" else original(name)), \
             patch("research_workspace.ise_ml_ui.read_snapshot") as read, \
             patch("research_workspace.ise_ml_ui.evaluate") as model:
            at = self.app()
            self.assertFalse(at.exception)
            self.assertFalse(any(e.key == "ise_snapshot_path" for e in at.text_input))
            self.assertFalse(any(e.key == "ise_load" for e in at.button))
            read.assert_not_called()
            model.assert_not_called()

    def test_relative_and_unc_paths_are_rejected_before_read(self):
        with patch("research_workspace.ise_ml_ui.read_snapshot") as read, \
             patch("research_workspace.ise_ml_ui.evaluate") as model:
            for path in ("relative/snapshot", r"\\server\share\snapshot", ""):
                with self.subTest(path=path):
                    at = self.app()
                    self.load(at, path)
                    read.assert_not_called()
                    model.assert_not_called()
                    self.assertEqual(len(at.get("plotly_chart")), 0)
                    self.assertTrue(at.warning or at.error)

    def test_load_alone_does_not_evaluate_or_show_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_ml_ui.read_snapshot", return_value=(self.frame, self.meta)) as read, \
             patch("research_workspace.ise_ml_ui.evaluate") as model:
            at = self.app()
            self.load(at, tmp)
            self.assertEqual(read.call_count, 1)
            model.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)
            cursor = at.slider(key="ise_cursor")
            self.assertEqual(cursor.proto.max, 428)
            self.assertEqual(cursor.proto.min, 321)

    def test_explicit_evaluation_uses_replay_limit_and_clears_stale_output(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_ml_ui.read_snapshot", return_value=(self.frame, self.meta)), \
             patch("research_workspace.ise_ml_ui.evaluate", wraps=evaluate) as model:
            at = self.app()
            self.load(at, tmp)
            at.slider(key="ise_cursor").set_value(350).run()
            model.assert_not_called()
            at.button(key="ise_evaluate").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(model.call_args.kwargs["visible_count"], 350)
            self.assertGreater(len(at.get("plotly_chart")), 0)
            reports = [json.loads(e.value) for e in at.json]
            report = next(r for r in reports if "evaluated_rows" in r)
            self.assertEqual(report["evaluated_rows"], 29)
            self.assertFalse(report["holdout_scored"])
            self.assertFalse(report["orders_enabled"])
            self.assertFalse(report["economic_backtest_available"])
            cutoff = self.frame.date.iloc[349]
            for element in at.dataframe:
                if "date" in element.value.columns:
                    self.assertLessEqual(pd.to_datetime(element.value.date).max(), cutoff)
            at.slider(key="ise_cursor").set_value(351).run()
            self.assertFalse(at.exception)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertFalse(any("evaluated_rows" in json.loads(e.value) for e in at.json))

    def test_failed_reload_removes_previous_snapshot_and_sanitizes_error(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_ml_ui.read_snapshot", return_value=(self.frame, self.meta)) as read, \
             patch("research_workspace.ise_ml_ui.evaluate") as model:
            at = self.app()
            self.load(at, tmp)
            self.assertTrue(any(e.key == "ise_cursor" for e in at.slider))
            read.side_effect = OSError("SECRET_SOURCE_BODY private-provider-path")
            self.load(at, tmp)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertFalse(any(e.key == "ise_cursor" for e in at.slider))
            model.assert_not_called()
            text = " ".join(e.value for e in (*at.error, *at.warning))
            self.assertTrue(text)
            self.assertNotIn("SECRET_SOURCE_BODY", text)
            self.assertNotIn("private-provider-path", text)
