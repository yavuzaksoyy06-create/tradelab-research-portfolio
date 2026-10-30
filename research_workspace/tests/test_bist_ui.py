"""BIST upload UI mechanics only; no generated fixture is a market result."""
import hashlib
from io import BytesIO
import json
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest


SCRIPT = "from research_workspace.bist_ui import render\nrender()"


class BISTUITests(unittest.TestCase):
    def setUp(self):
        get_option = st.get_option
        local = patch("research_workspace.bist_ui.st.get_option",
                      side_effect=lambda name: "127.0.0.1" if name == "server.address" else get_option(name))
        local.start()
        self.addCleanup(local.stop)

    def app(self):
        return AppTest.from_string(SCRIPT, default_timeout=60).run()

    def fill_source(self, at):
        at.selectbox(key="bist_symbol").set_value("GARAN")
        at.text_input(key="bist_provider").set_value("Test provider")
        at.text_input(key="bist_source_url").set_value("https://example.org/history")
        at.text_input(key="bist_license_reference").set_value("Test local research permission")

    def test_initial_display_does_not_load_or_analyze(self):
        with patch("research_workspace.bist_ui.load_csv") as load, \
             patch("research_workspace.bist_ui.analyze") as analyze:
            at = self.app()
            self.assertFalse(at.exception)
            self.assertIn("BIST · Günlük Araştırma", [e.value for e in at.subheader])
            load.assert_not_called()
            analyze.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)

    def test_explicit_submission_binds_source_hash_and_drops_result_on_rerun(self):
        # Tiny mocked data only exercises presentation; backend tests enforce
        # full real-input coverage. These values are never a BIST result.
        dates = pd.date_range("2023-01-02", periods=2)
        frame = pd.DataFrame({"date": dates, "open": [10., 11.], "high": [12., 13.],
                              "low": [9., 10.], "close": [11., 12.]})
        curve = pd.DataFrame({"date": dates, "adjusted_close": [11., 12.],
                              "ema20": [11., 11.1], "ema60": [11., 11.05],
                              "net_equity": [1., 1.01], "buyhold_equity": [1., 1.02]})
        payload = b"software-presentation-fixture-only"
        meta = {"csv_sha256": hashlib.sha256(payload).hexdigest(), "symbol": "GARAN"}
        with patch("research_workspace.bist_ui.st.file_uploader", return_value=BytesIO(payload)), \
             patch("research_workspace.bist_ui.load_csv", return_value=(frame, meta)) as load, \
             patch("research_workspace.bist_ui.analyze", return_value=({"software_fixture_only": True}, curve)) as analyze:
            at = self.app()
            self.fill_source(at)
            at.checkbox(key="bist_usage_rights").set_value(True)
            at.button(key="bist_run").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(load.call_count, 1)
            raw, manifest = load.call_args.args
            self.assertEqual(raw, payload)
            self.assertEqual(manifest["csv_sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(manifest["symbol"], "GARAN")
            self.assertEqual(manifest["provider"], "Test provider")
            self.assertEqual(manifest["source_url"], "https://example.org/history")
            self.assertEqual(manifest["license_reference"], "Test local research permission")
            self.assertEqual(manifest["usage_rights"], "user_confirmed_local_research")
            self.assertFalse(manifest["source_independently_verified"])
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 3)
            spec = json.loads(at.get("plotly_chart")[0].proto.spec)
            self.assertEqual(spec["data"][0]["type"], "candlestick")
            self.assertEqual(spec["data"][0]["name"], "GARAN")
            self.assertTrue(all(str(x).startswith("2023-") for x in spec["data"][0]["x"]))
            self.assertEqual(json.loads(at.json[0].value), {"software_fixture_only": True})
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.json), 0)

    def test_absent_upload_cannot_create_chart_or_backtest(self):
        with patch("research_workspace.bist_ui.load_csv") as load, \
             patch("research_workspace.bist_ui.analyze") as analyze:
            at = self.app()
            self.fill_source(at)
            at.checkbox(key="bist_usage_rights").set_value(True)
            at.button(key="bist_run").click().run()
            self.assertFalse(at.exception)
            load.assert_not_called()
            analyze.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertTrue(at.warning or at.error)

    def test_nonloopback_workspace_never_exposes_upload_or_backend(self):
        local_options = st.get_option
        with patch("research_workspace.bist_ui.st.get_option",
                   side_effect=lambda name: "0.0.0.0" if name == "server.address" else local_options(name)), \
             patch("research_workspace.bist_ui.load_csv") as load, \
             patch("research_workspace.bist_ui.analyze") as analyze:
            at = self.app()
            self.assertFalse(at.exception)
            self.assertFalse(any(b.key == "bist_run" for b in at.button))
            self.assertEqual(len(at.get("file_uploader")), 0)
            load.assert_not_called()
            analyze.assert_not_called()

    def test_upload_without_rights_confirmation_is_not_processed(self):
        with patch("research_workspace.bist_ui.st.file_uploader", return_value=BytesIO(b"test fixture")), \
             patch("research_workspace.bist_ui.load_csv") as load, \
             patch("research_workspace.bist_ui.analyze") as analyze:
            at = self.app()
            self.fill_source(at)
            at.button(key="bist_run").click().run()
            self.assertFalse(at.exception)
            load.assert_not_called()
            analyze.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertTrue(at.warning or at.error)

    def test_rejected_source_shows_no_exception_body_or_private_path(self):
        with patch("research_workspace.bist_ui.st.file_uploader", return_value=BytesIO(b"test fixture")), \
             patch("research_workspace.bist_ui.load_csv", side_effect=ValueError("SECRET_SOURCE_BODY private-path")), \
             patch("research_workspace.bist_ui.analyze") as analyze:
            at = self.app()
            self.fill_source(at)
            at.checkbox(key="bist_usage_rights").set_value(True)
            at.button(key="bist_run").click().run()
            self.assertFalse(at.exception)
            analyze.assert_not_called()
            text = " ".join(e.value for e in (*at.warning, *at.error))
            self.assertTrue(text)
            self.assertNotIn("SECRET_SOURCE_BODY", text)
            self.assertNotIn("private-path", text)
            self.assertEqual(len(at.get("plotly_chart")), 0)

