"""Accidental mutable-state corruption must not bypass explicit model checks."""
from contextlib import contextmanager
import hashlib
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from research_workspace.ise_ml import COLUMNS, SOURCE_URL, evaluate, load_csv
from research_workspace.ise_ml_ui import SNAPSHOT_KEY, REPORT_KEY

SCRIPT = "from research_workspace.ise_ml_ui import render\nrender()"


class ISECacheAuditTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(73)
        raw = pd.DataFrame(rng.normal(0, .01, (536, 9)), columns=COLUMNS[1:])
        raw.insert(0, "date", pd.bdate_range("2009-01-05", periods=536))
        payload = raw.to_csv(index=False).encode()
        self.frame, self.meta = load_csv(payload, {
            "source_id": "uci247", "license": "CC-BY-4.0", "source_url": SOURCE_URL,
            "csv_sha256": hashlib.sha256(payload).hexdigest()})
        original = st.get_option
        config = patch("research_workspace.ise_ml_ui.st.get_option",
                       side_effect=lambda key: "127.0.0.1" if key == "server.address" else original(key))
        config.start()
        self.addCleanup(config.stop)

    @contextmanager
    def cached_app(self):
        # These are simulated returns; no real reserved observations are opened.
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_ml_ui.read_snapshot", return_value=(self.frame, self.meta)), \
             patch("research_workspace.ise_ml_ui.evaluate", wraps=evaluate) as model:
            at = AppTest.from_string(SCRIPT, default_timeout=60).run()
            at.text_input(key="ise_snapshot_path").set_value(tmp)
            at.button(key="ise_load").click().run()
            at.slider(key="ise_cursor").set_value(350).run()
            at.button(key="ise_evaluate").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(len(at.get("plotly_chart")), 3)
            yield at, model

    def assert_rejected_without_refit(self, at, model):
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(len(at.get("plotly_chart")), 0)
        self.assertEqual(len(at.json), 0)
        self.assertTrue(any("ISE_CACHE_REJECTED" in e.value for e in at.error))

    def test_changed_loaded_frame_cannot_reuse_cached_report(self):
        with self.cached_app() as (at, model):
            snapshot = at.session_state[SNAPSHOT_KEY]
            snapshot[1].loc[100, "ise_try"] += .05
            self.assert_rejected_without_refit(at, model)

    def test_changed_loaded_metadata_cannot_reuse_cached_report(self):
        with self.cached_app() as (at, model):
            snapshot = at.session_state[SNAPSHOT_KEY]
            snapshot[2]["csv_sha256"] = "0" * 64
            self.assert_rejected_without_refit(at, model)

    def test_changed_summary_is_rejected_before_any_metric_is_displayed(self):
        with self.cached_app() as (at, model):
            cached = at.session_state[REPORT_KEY]
            cached[1]["metrics"]["ridge"]["rmse"] = -1.0
            cached[1]["holdout_scored"] = True
            self.assert_rejected_without_refit(at, model)

    def test_changed_explanation_cutoff_is_not_rendered_from_cache(self):
        with self.cached_app() as (at, model):
            cached = at.session_state[REPORT_KEY]
            last = cached[2].index[-1]
            cached[2].loc[last, "feature_cutoff"] = "2011-12-31"
            cached[2].loc[last, "feature_cutoff_index"] = 535
            self.assert_rejected_without_refit(at, model)
            self.assertFalse(any("2011-12-31" in e.value for e in at.markdown))

    def test_one_ulp_nested_contribution_change_is_not_lost_to_json_rounding(self):
        with self.cached_app() as (at, model):
            cached = at.session_state[REPORT_KEY]
            contribution = cached[2].iloc[-1].top_contributions[0]
            original = contribution["contribution"]
            contribution["contribution"] = float(np.nextafter(original, np.inf))
            self.assertNotEqual(original, contribution["contribution"])
            self.assert_rejected_without_refit(at, model)
