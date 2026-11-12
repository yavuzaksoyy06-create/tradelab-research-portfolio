"""Offline UI action boundaries, source cache integrity and sanitized failures."""
from io import BytesIO
import json
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from research_workspace.equity_data import REQUIRED, synthetic_fixture, read_uploaded_csv
from research_workspace.stage7_events import replay_limit

SCRIPT = "from research_workspace.bot_rehearsal_ui import render\nrender()"
MODULE = "research_workspace.bot_rehearsal_ui."


class BotRehearsalUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.metadata = synthetic_fixture()

    def setUp(self):
        original = st.get_option
        local = patch(MODULE + "st.get_option", side_effect=lambda key:
                      "127.0.0.1" if key == "server.address" else original(key))
        ready = patch(MODULE + "readiness_report", return_value={
            "production_allowed": False, "orders_enabled": False,
            "reserved_ise_rows": 108, "blockers": ["V2_PRIMARY_EDGE_NOT_ESTABLISHED"]})
        local.start()
        ready.start()
        self.addCleanup(local.stop)
        self.addCleanup(ready.stop)

    def app(self):
        return AppTest.from_string(SCRIPT, default_timeout=45).run()

    def prepared(self):
        at = self.app()
        at.button(key="bot_prepare").click().run()
        self.assertFalse(at.exception)
        return at

    def output(self):
        curve = pd.DataFrame({"timestamp": self.frame.timestamp.iloc[:3],
                              "equity": [100000., 100000., 99999.],
                              "cash": [100000., 99000., 99999.],
                              "position": [0, 10, 0], "close": [100., 100., 99.9]})
        return {"orders_enabled": False, "mode": "offline_rehearsal"}, curve, [
            {"event": "risk_checked", "index": 1}, {"event": "simulated_fill", "index": 2}]

    def test_initial_view_does_not_generate_data_parse_or_run(self):
        with patch(MODULE + "synthetic_fixture") as data, \
             patch(MODULE + "read_uploaded_csv") as read, \
             patch(MODULE + "run_rehearsal") as run:
            at = self.app()
            self.assertFalse(at.exception)
            data.assert_not_called()
            read.assert_not_called()
            run.assert_not_called()
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.get("download_button")), 0)
            self.assertTrue(any("SENTETİK VERİ" in warning.value for warning in at.warning))

    def test_nonlocal_bind_exposes_no_source_controls_and_clears_data(self):
        with patch(MODULE + "st.get_option", return_value="0.0.0.0"), \
             patch(MODULE + "synthetic_fixture") as data, \
             patch(MODULE + "run_rehearsal") as run:
            at = self.app()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("file_uploader")), 0)
            self.assertEqual(len(at.radio), 0)
            self.assertEqual(len(at.button), 0)
            data.assert_not_called()
            run.assert_not_called()

    def test_preparation_never_runs_and_explicit_run_outputs_current_report_only(self):
        with patch(MODULE + "synthetic_fixture", return_value=(self.frame.copy(), self.metadata.copy())) as data, \
             patch(MODULE + "run_rehearsal", return_value=self.output()) as run, \
             patch(MODULE + "build_report", return_value=b'{"verified":"test"}') as build, \
             patch(MODULE + "verify_report", return_value={}) as verify:
            at = self.prepared()
            data.assert_called_once_with("SPY")
            run.assert_not_called()
            self.assertEqual(at.slider(key="bot_cursor").max, replay_limit(self.frame))
            at.slider(key="bot_cursor").set_value(80).run()
            run.assert_not_called()
            at.button(key="bot_run").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("plotly_chart")), 2)
            self.assertEqual(len(at.get("download_button")), 1)
            self.assertEqual(run.call_args.kwargs, {"visible_count": 80, "halt_at": None})
            build.assert_called_once()
            verify.assert_called_once_with(b'{"verified":"test"}')
            at.slider(key="bot_cursor").set_value(81).run()
            self.assertEqual(run.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.get("download_button")), 0)

    def test_halt_control_is_explicit_and_limited_to_visible_prefix(self):
        with patch(MODULE + "synthetic_fixture", return_value=(self.frame.copy(), self.metadata.copy())), \
             patch(MODULE + "run_rehearsal", return_value=self.output()) as run, \
             patch(MODULE + "build_report", return_value=b"test"), \
             patch(MODULE + "verify_report", return_value={}):
            at = self.prepared()
            at.slider(key="bot_cursor").set_value(50).run()
            at.checkbox(key="bot_halt_enabled").check().run()
            self.assertEqual(at.number_input(key="bot_halt_at").max, 49)
            at.number_input(key="bot_halt_at").set_value(35).run()
            run.assert_not_called()
            at.button(key="bot_run").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(run.call_args.kwargs, {"visible_count": 50, "halt_at": 35})

    def test_source_change_invalidates_prepared_data_before_any_rehearsal(self):
        with patch(MODULE + "synthetic_fixture", return_value=(self.frame.copy(), self.metadata.copy())), \
             patch(MODULE + "run_rehearsal") as run:
            at = self.prepared()
            at.selectbox(key="bot_symbol").set_value("QQQ").run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.slider), 0)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertFalse(any(button.key == "bot_run" for button in at.button))
            run.assert_not_called()

    def test_source_cache_mutation_fails_before_running_or_showing_results(self):
        with patch(MODULE + "synthetic_fixture", return_value=(self.frame.copy(), self.metadata.copy())), \
             patch(MODULE + "run_rehearsal") as run:
            at = self.prepared()
            at.session_state["bot_rehearsal_loaded_data"][1].loc[0, "close"] += .00001
            at.run()
            self.assertFalse(at.exception)
            self.assertTrue(any("BOT_CACHE_REJECTED" in error.value for error in at.error))
            self.assertEqual(len(at.get("plotly_chart")), 0)
            run.assert_not_called()

    def test_uploaded_ohlcv_is_parsed_only_after_preparation_and_without_network(self):
        payload = self.frame[list(REQUIRED)].to_csv(index=False).encode()
        with patch(MODULE + "st.file_uploader", return_value=BytesIO(payload)), \
             patch(MODULE + "read_uploaded_csv", wraps=read_uploaded_csv) as read, \
             patch(MODULE + "run_rehearsal") as run:
            at = self.app()
            at.radio(key="bot_source").set_value("Yerel OHLCV CSV").run()
            read.assert_not_called()
            run.assert_not_called()
            at.button(key="bot_prepare").click().run()
            self.assertFalse(at.exception)
            read.assert_called_once_with(payload, "SPY")
            self.assertEqual(len(at.slider), 1)
            self.assertFalse(at.session_state["bot_rehearsal_loaded_data"][2]["synthetic"])
            run.assert_not_called()

    def test_invalid_source_and_simulation_errors_do_not_echo_private_details(self):
        with patch(MODULE + "synthetic_fixture", side_effect=ValueError("SECRET_PATH_TOKEN")):
            at = self.prepared()
            self.assertTrue(any("BOT_SOURCE_REJECTED" in error.value for error in at.error))
            self.assertNotIn("SECRET", " ".join(error.value for error in at.error))
        with patch(MODULE + "synthetic_fixture", return_value=(self.frame.copy(), self.metadata.copy())), \
             patch(MODULE + "run_rehearsal", side_effect=ValueError("SECRET_ACCOUNT_CONTENT")):
            at = self.prepared()
            at.button(key="bot_run").click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any("BOT_REHEARSAL_REJECTED" in error.value for error in at.error))
            self.assertNotIn("SECRET", " ".join(error.value for error in at.error))
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.get("download_button")), 0)

    def test_report_verification_failure_blocks_all_simulation_outputs(self):
        with patch(MODULE + "synthetic_fixture", return_value=(self.frame.copy(), self.metadata.copy())), \
             patch(MODULE + "run_rehearsal", return_value=self.output()), \
             patch(MODULE + "build_report", return_value=b"changed"), \
             patch(MODULE + "verify_report", side_effect=ValueError("Bad report")):
            at = self.prepared()
            at.button(key="bot_run").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.get("download_button")), 0)
            self.assertTrue(any("BOT_REHEARSAL_REJECTED" in error.value for error in at.error))

    def test_real_offline_engine_and_report_complete_without_external_orders(self):
        at = self.prepared()
        at.button(key="bot_run").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertEqual(len(at.get("plotly_chart")), 2)
        self.assertEqual(len(at.get("download_button")), 1)
        summary = json.loads(at.json[-1].value)
        self.assertEqual(summary["mode"], "OFFLINE_REHEARSAL_ONLY")
        self.assertTrue(summary["synthetic"])
        self.assertEqual(summary["visible_bars"], replay_limit(self.frame))
        self.assertEqual(summary["real_orders_sent"], 0)
        self.assertEqual(summary["paper_orders_sent"], 0)
        self.assertEqual(summary["model_fits"], 0)
        self.assertFalse(summary["holdout_scored"])
        self.assertEqual(summary["ise_reserved_rows"], 108)

    def test_explicit_stress_runs_fixed_cases_and_clears_on_inspection(self):
        with patch(MODULE + "run_stress_suite", wraps=__import__(
                "research_workspace.bot_stress", fromlist=["run_stress_suite"]).run_stress_suite) as stress:
            at = self.prepared()
            stress.assert_not_called()
            at.button(key="bot_stress").click().run()
            self.assertFalse(at.exception)
            self.assertFalse(at.error)
            self.assertEqual(stress.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 1)
            self.assertEqual(len(at.get("download_button")), 1)
            diagnostics = json.loads(at.json[-1].value)
            self.assertEqual(diagnostics["journal_recovery"]["status"], "PASSED")
            at.run()
            self.assertEqual(stress.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 0)

    def test_stress_error_is_sanitized_before_plot_or_download(self):
        with patch(MODULE + "run_stress_suite", side_effect=ValueError("SECRET_PRIVATE_DATA")):
            at = self.prepared()
            at.button(key="bot_stress").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.get("plotly_chart")), 0)
            self.assertEqual(len(at.get("download_button")), 0)
            self.assertTrue(any("BOT_STRESS_REJECTED" in e.value for e in at.error))
            self.assertNotIn("SECRET", " ".join(e.value for e in at.error))

    def test_loaded_alpaca_snapshot_is_prepared_and_report_keeps_source_classification(self):
        # Synthetic bars stand in for an API response; no provider request is made.
        metadata = {**self.metadata, "synthetic": False, "provider_api_response": True,
                    "feed": "iex", "origin": "ALPACA TEST RESPONSE", "currency": "USD"}
        with patch(MODULE + "get_loaded_alpaca_snapshot", return_value=(self.frame.copy(), metadata)), \
             patch(MODULE + "synthetic_fixture") as fixture:
            at = self.prepared()
            self.assertEqual(at.radio(key="bot_source").value, "Alpaca · Piyasa Terminali")
            at.button(key="bot_run").click().run()
            self.assertFalse(at.exception)
            self.assertFalse(at.error)
            summary = json.loads(at.json[-1].value)
            self.assertIs(summary["synthetic"], False)
            self.assertEqual(summary["real_orders_sent"], 0)
            self.assertEqual(summary["ise_reserved_rows"], 108)
            self.assertTrue(any("Alpaca · IEX" in caption.value for caption in at.caption))
            fixture.assert_not_called()

    def test_missing_or_changed_alpaca_source_revokes_prepared_rehearsal(self):
        metadata = {**self.metadata, "synthetic": False, "provider_api_response": True,
                    "feed": "iex", "origin": "ALPACA TEST RESPONSE", "currency": "USD"}
        with patch(MODULE + "get_loaded_alpaca_snapshot", return_value=(self.frame.copy(), metadata)) as read, \
             patch(MODULE + "synthetic_fixture") as fixture, \
             patch(MODULE + "run_rehearsal") as engine:
            at = self.prepared()
            self.assertIn("bot_rehearsal_loaded_data", at.session_state)
            changed = self.frame.copy()
            changed.loc[0, "close"] += .00001
            read.return_value = (changed, metadata)
            at.run()
            self.assertNotIn("bot_rehearsal_loaded_data", at.session_state)
            self.assertEqual(len(at.slider), 0)
            at.button(key="bot_prepare").click().run()
            self.assertIn("bot_rehearsal_loaded_data", at.session_state)
            read.return_value = None
            at.run()
            self.assertNotIn("bot_rehearsal_loaded_data", at.session_state)
            self.assertEqual(len(at.slider), 0)
            self.assertTrue(any("Piyasa Terminali" in item.value for item in at.info))
            engine.assert_not_called()
            fixture.assert_not_called()
