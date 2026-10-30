"""Explicit preparation actions, sanitized failures and read-only UI behavior."""
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from research_workspace.equity_data import synthetic_fixture
from research_workspace.stage7_history import save_private


SCRIPT = "from research_workspace.stage7_preparation_ui import render_preparation\nrender_preparation()"


class Stage7PreparationUITests(unittest.TestCase):
    def setUp(self):
        # A local bind is an explicit prerequisite for server-filesystem review.
        local = patch("research_workspace.stage7_preparation_ui.st.get_option", return_value="127.0.0.1")
        local.start()
        self.addCleanup(local.stop)

    @contextmanager
    def no_analysis_or_network(self):
        with patch("research_workspace.stage7_validation.evaluate_history",
                   side_effect=AssertionError("Preparation must not evaluate")), \
             patch("research_workspace.stage7_validation.fit_frequency",
                   side_effect=AssertionError("Preparation must not fit")), \
             patch("research_workspace.stage7_history.read_alpaca_history",
                   side_effect=AssertionError("Preparation must not download")):
            yield

    def make_app(self):
        return AppTest.from_string(SCRIPT, default_timeout=60).run()

    def test_initial_render_performs_no_plan_or_review(self):
        with patch("research_workspace.stage7_preparation_ui.collection_plan") as plan, \
             patch("research_workspace.stage7_preparation_ui.review_snapshot") as review, \
             self.no_analysis_or_network():
            at = self.make_app()
            self.assertFalse(at.exception)
            plan.assert_not_called()
            review.assert_not_called()
            self.assertEqual(len(at.json), 0)

    def test_plan_submits_exact_fields_and_clears_on_invalid_resubmission(self):
        with self.no_analysis_or_network():
            at = self.make_app()
            at.selectbox(key="stage7_plan_symbol").set_value("QQQ")
            at.selectbox(key="stage7_plan_feed").set_value("sip")
            at.date_input(key="stage7_plan_start").set_value(date(2025, 1, 2))
            at.date_input(key="stage7_plan_end").set_value(date(2025, 1, 10))
            at.button(key="stage7_plan_submit").click().run()
            self.assertFalse(at.exception)
            report = json.loads(at.json[0].value)
            self.assertEqual((report["symbol"], report["feed"]), ("QQQ", "sip"))
            self.assertEqual(report["first_session"], "2025-01-02")
            self.assertEqual(report["last_session"], "2025-01-10")
            # The pinned exchange calendar also excludes 9 January 2025.
            self.assertEqual(report["sessions"], 6)
            self.assertEqual(report["network_requests_performed"], 0)
            at.date_input(key="stage7_plan_end").set_value(date(2024, 12, 31))
            at.button(key="stage7_plan_submit").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.json), 0)
            self.assertTrue(at.warning or at.error)

    def test_unrelated_rerun_drops_previous_plan_without_reexecuting(self):
        with self.no_analysis_or_network():
            at = self.make_app()
            at.button(key="stage7_plan_submit").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.json), 1)
            with patch("research_workspace.stage7_preparation_ui.collection_plan") as plan:
                at.run()
                plan.assert_not_called()
            self.assertEqual(len(at.json), 0)

    def test_plan_failure_does_not_display_arbitrary_exception(self):
        with patch("research_workspace.stage7_preparation_ui.collection_plan",
                   side_effect=ValueError("SECRET_PROVIDER_BODY private-path")):
            at = self.make_app()
            at.button(key="stage7_plan_submit").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.json), 0)
            text = " ".join(item.value for kind in (at.warning, at.error) for item in kind)
            self.assertNotIn("SECRET_PROVIDER_BODY", text)
            self.assertNotIn("private-path", text)
            self.assertTrue(text)

    def test_review_uses_existing_fixture_without_mutating_or_evaluating(self):
        with tempfile.TemporaryDirectory() as tmp, self.no_analysis_or_network():
            folder = Path(tmp) / "snapshot"
            frame, meta = synthetic_fixture()
            # Simulated input tests UI mechanics, never historical market results.
            meta.update(synthetic=False, feed="sip", adjustment="split",
                        expected_bars=len(frame), received_bars=len(frame))
            save_private(frame, meta, folder)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            at = self.make_app()
            at.text_input(key="stage7_review_path").set_value(str(folder))
            at.button(key="stage7_review_submit").click().run()
            self.assertFalse(at.exception)
            report = json.loads(at.json[0].value)
            self.assertEqual(report["status"], "verified_structure")
            self.assertEqual(report["eligibility_reason"], "INSUFFICIENT_SESSIONS")
            self.assertFalse(report["diagnostic_eligible"])
            self.assertFalse(report["model_evaluated"])
            self.assertFalse(report["outcomes_computed"])
            self.assertTrue({"close", "volume", "return", "origin"}.isdisjoint(report))
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_missing_snapshot_rejection_has_no_local_path(self):
        with tempfile.TemporaryDirectory() as tmp, self.no_analysis_or_network():
            at = self.make_app()
            at.text_input(key="stage7_review_path").set_value(str(Path(tmp) / "SECRET_PATH"))
            at.button(key="stage7_review_submit").click().run()
            self.assertFalse(at.exception)
            report = json.loads(at.json[0].value)
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["reason"], "MISSING_OR_UNREADABLE_FILES")
            self.assertNotIn("SECRET_PATH", at.json[0].value)

    def test_nonlocal_bind_disables_filesystem_review_but_keeps_offline_plan(self):
        with patch("research_workspace.stage7_preparation_ui.st.get_option", return_value="0.0.0.0"), \
             patch("research_workspace.stage7_preparation_ui.review_snapshot") as review:
            at = self.make_app()
            self.assertFalse(at.exception)
            self.assertFalse(any(i.key == "stage7_review_path" for i in at.text_input))
            self.assertTrue(at.button(key="stage7_review_submit").disabled)
            review.assert_not_called()
            at.button(key="stage7_plan_submit").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(json.loads(at.json[0].value)["network_requests_performed"], 0)
            review.assert_not_called()

    def test_preparation_is_available_before_no_upload_early_return(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        with self.no_analysis_or_network():
            at = AppTest.from_file(str(app), default_timeout=60).run()
            at.radio(key="page").set_value("Equity Research").run()
            at.radio(key="equity_mode").set_value("Upload my OHLCV CSV").run()
            self.assertFalse(at.exception)
            self.assertIn("Stage 7 · Veri Hazırlığı", [h.value for h in at.subheader])
            self.assertTrue(any(b.key == "stage7_plan_submit" for b in at.button))
            self.assertTrue(any("No file selected" in e.value for e in at.info))
            self.assertEqual(len(at.get("plotly_chart")), 0)

    def test_relative_and_unc_paths_are_rejected_before_backend(self):
        for path in ("relative/snapshot", r"\\server\share\snapshot", "//server/share/snapshot", ""):
            with self.subTest(path=path), \
                 patch("research_workspace.stage7_preparation_ui.review_snapshot") as review:
                at = self.make_app()
                at.text_input(key="stage7_review_path").set_value(path)
                at.button(key="stage7_review_submit").click().run()
                self.assertFalse(at.exception)
                review.assert_not_called()
                self.assertEqual(len(at.json), 0)
                self.assertTrue(any("LOCAL_PATH_REQUIRED" in e.value for e in at.error))

    def test_review_exception_is_sanitized_and_previous_report_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.stage7_preparation_ui.review_snapshot") as review:
            review.return_value = {"status": "verified_structure", "diagnostic_eligible": False}
            at = self.make_app()
            at.text_input(key="stage7_review_path").set_value(tmp)
            at.button(key="stage7_review_submit").click().run()
            self.assertEqual(len(at.json), 1)
            review.side_effect = OSError("SECRET_ERROR_BODY private-path")
            at.button(key="stage7_review_submit").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.json), 0)
            text = " ".join(e.value for e in at.error)
            self.assertIn("REVIEW_FAILED", text)
            self.assertNotIn("SECRET_ERROR_BODY", text)
            self.assertNotIn("private-path", text)

    def test_symlinked_snapshot_files_are_blocked_before_review(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.stage7_preparation_ui.review_snapshot") as review:
            original = Path.is_symlink

            for name in ("bars.csv", "manifest.json"):
                with self.subTest(file=name):
                    def symbolic_file(path):
                        return path.name == name or original(path)

                    at = self.make_app()
                    at.text_input(key="stage7_review_path").set_value(tmp)
                    with patch.object(Path, "is_symlink", symbolic_file):
                        at.button(key="stage7_review_submit").click().run()
                    self.assertFalse(at.exception)
                    review.assert_not_called()
                    self.assertEqual(len(at.json), 0)
                    self.assertTrue(any("LOCAL_PATH_REQUIRED" in e.value for e in at.error))
