"""Adversarial Stage 7 regressions: no real data, no network, no frozen execution."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from research_workspace.tests.test_stage7_research import long_fixture
from research_workspace.equity_data import synthetic_fixture
from research_workspace.stage7_events import event_dataset, research_partition
from research_workspace.stage7_validation import split_plan, evaluate_history
from research_workspace.stage7_history import save_private, load_private


class Stage7AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame = long_fixture()
        _, cls.meta = synthetic_fixture()

    def test_replay_never_labels_reserved_holdout_or_crossing_horizons(self):
        boundary = split_plan(self.frame)["holdout_start"]
        data = event_dataset(self.frame, self.meta)
        leaked = [r for r in data["records"] if r["features"]["index"] + r["horizon"] >= boundary
                  and r["outcome"]["up"] is not None]
        self.assertEqual(leaked, [], "Replay exposed reserved historical outcomes")
        self.assertTrue(all(r["features"]["index"] < boundary for r in data["records"]))

    def test_validation_replay_uses_full_snapshot_partition(self):
        count = len(self.frame.loc[self.frame.session.isin(list(dict.fromkeys(self.frame.session))[:90])])
        report = evaluate_history(self.frame, self.meta, visible_count=count)
        self.assertEqual(report["plan"]["holdout_start"], split_plan(self.frame)["holdout_start"])
        for result in report["horizons"].values():
            self.assertTrue(all(f["stop"] <= count for f in result["folds"]))

    def test_event_helper_rejects_negative_indices_instead_of_reading_tail(self):
        from research_workspace.stage7_events import outcome
        record = {"index": -5, "close": 100, "event": {"type": "none", "zone": None}}
        with self.assertRaises(ValueError):
            outcome(self.frame, record, 4)

    def test_writer_rejects_sealed_data_before_creating_directory(self):
        frame, meta = synthetic_fixture()
        frame["timestamp"] = frame.timestamp + pd.Timedelta(days=40)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sealed"
            with self.assertRaises(ValueError):
                save_private(frame, meta, target)
            self.assertFalse(target.exists())

    def test_writer_does_not_persist_arbitrary_credentials(self):
        frame, meta = synthetic_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot"
            save_private(frame, {**meta, "api_key": "CANARY_SECRET"}, target)
            self.assertNotIn("CANARY_SECRET", (target / "manifest.json").read_text(encoding="utf-8"))

    def test_chart_cursor_stops_before_reserved_holdout(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        with patch("research_workspace.equity_ui.synthetic_fixture",
                   return_value=(self.frame, self.meta)):
            at = AppTest.from_file(str(app), default_timeout=60).run()
            at.radio(key="page").set_value("Equity Research").run()
            self.assertFalse(at.exception)
            slider = next(s for s in at.slider if "As-of replay" in s.label)
            self.assertEqual(slider.max, split_plan(self.frame)["holdout_start"])

    def test_registered_snapshot_cannot_be_truncated_or_replaced(self):
        meta = {**self.meta, "research_partition": research_partition(self.frame)}
        changed = self.frame.copy()
        changed.loc[changed.index[-1], "volume"] += 1
        shortened = self.frame.iloc[:-26]
        for bad in (changed, shortened):
            for call in (evaluate_history, event_dataset):
                with self.subTest(call=call.__name__), self.assertRaisesRegex(ValueError, "Registered snapshot"):
                    call(bad, meta)

    def test_real_history_without_registration_cannot_fit(self):
        meta = {**self.meta, "synthetic": False, "feed": "sip", "adjustment": "split"}
        with patch("research_workspace.stage7_validation.fit_frequency",
                   side_effect=AssertionError("Unregistered data reached model")):
            report = evaluate_history(self.frame, meta)
        self.assertEqual(report["horizons"], {})
        self.assertIn("registration required", report["reason"])

    def test_private_roundtrip_preserves_registered_partition_and_filters_nested_headers(self):
        meta = {**self.meta, "synthetic": False, "feed": "sip", "adjustment": "split",
                "received_bars": len(self.frame), "expected_bars": len(self.frame),
                "batches": [{"first_session": str(self.frame.session.iloc[0]),
                             "headers": {"api_key": "NESTED_CANARY"}}]}
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot"
            manifest = save_private(self.frame, meta, target)
            clean, loaded = load_private(target)
            self.assertEqual(manifest["research_partition"], research_partition(clean))
            self.assertEqual(loaded["research_partition"], research_partition(self.frame))
            self.assertNotIn("NESTED_CANARY", (target / "manifest.json").read_text(encoding="utf-8"))
