"""Planning/review is offline, read-only and distinct from outcome evaluation."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from research_workspace.equity_data import synthetic_fixture
from research_workspace.stage7_history import collection_plan, save_private
from research_workspace.stage7_review import review_snapshot
from tools.stage7_research import main


class Stage7ReviewTests(unittest.TestCase):
    def snapshot(self, folder):
        frame, meta = synthetic_fixture()
        meta.update(synthetic=False, feed="sip", adjustment="split",
                    expected_bars=len(frame), received_bars=len(frame))
        # Simulated provider fixture; never a real historical result.
        save_private(frame, meta, folder)
        return folder

    def test_plan_is_bounded_and_requires_no_credentials_or_transport(self):
        with patch("research_workspace.stage7_history.read_alpaca_history",
                   side_effect=AssertionError("Planning must not download")):
            plan = collection_plan("SPY", "2025-01-02", "2025-06-25", feed="sip")
        self.assertEqual(plan["network_requests_performed"], 0)
        self.assertEqual(sum(b["expected_bars"] for b in plan["batches"]), plan["expected_bars"])
        self.assertLessEqual(plan["sessions"], 120)
        self.assertFalse(plan["entitlement_verified"])

    def test_plan_rejects_sealed_or_oversized_dates(self):
        for start, end in (("2026-10-20", "2026-10-27"), ("2025-01-01", "2026-01-01")):
            with self.assertRaises(ValueError):
                collection_plan("SPY", start, end, feed="iex")

    def test_review_is_read_only_price_free_and_does_not_evaluate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            with patch("research_workspace.stage7_validation.fit_frequency",
                       side_effect=AssertionError("Review must not fit")):
                report = review_snapshot(folder)
            self.assertEqual(report["status"], "verified_structure")
            self.assertFalse(report["diagnostic_eligible"])
            self.assertEqual(report["eligibility_reason"], "INSUFFICIENT_SESSIONS")
            self.assertFalse(report["model_evaluated"])
            self.assertFalse(report["outcomes_computed"])
            self.assertTrue({"close", "return", "volume", "origin"}.isdisjoint(report))
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
            self.assertEqual(report["csv_sha256"], hashlib.sha256(before["bars.csv"]).hexdigest())

    def test_hash_mismatch_has_controlled_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            with (folder / "bars.csv").open("ab") as f:
                f.write(b"\n")
            self.assertEqual(review_snapshot(folder)["reason"], "HASH_MISMATCH")

    def test_unregistered_legacy_snapshot_is_not_ready_for_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            path = folder / "manifest.json"
            meta = json.loads(path.read_text(encoding="utf-8"))
            del meta["research_partition"]
            path.write_text(json.dumps(meta), encoding="utf-8")
            report = review_snapshot(folder)
            self.assertFalse(report["partition_registered"])
            self.assertEqual(report["eligibility_reason"], "MISSING_REGISTRATION")

    def test_no_raw_path_or_error_body_in_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = review_snapshot(Path(tmp) / "SECRET_PATH")
            self.assertEqual(report["reason"], "MISSING_OR_UNREADABLE_FILES")
            self.assertNotIn("SECRET", json.dumps(report))

    def test_changed_files_during_review_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            from research_workspace.stage7_review import _digests
            good = _digests(folder)
            with patch("research_workspace.stage7_review._digests",
                       side_effect=[good, {**good, "bars.csv": "changed"}]):
                self.assertEqual(review_snapshot(folder)["reason"], "SNAPSHOT_CHANGED")

    def test_cli_plan_and_review_are_separate_from_evaluate(self):
        with patch("tools.stage7_research.evaluate_history", side_effect=AssertionError("No evaluation")):
            out = StringIO()
            with patch("sys.argv", ["stage7_research.py", "plan", "--symbol", "SPY", "--feed", "sip",
                                    "--start", "2026-10-05", "--end", "2026-10-16"]), redirect_stdout(out):
                self.assertEqual(main(), 0)
            self.assertEqual(json.loads(out.getvalue())["sessions"], 10)
            with tempfile.TemporaryDirectory() as tmp:
                folder = self.snapshot(Path(tmp) / "snapshot")
                out = StringIO()
                with patch("sys.argv", ["stage7_research.py", "review", "--snapshot", str(folder)]), redirect_stdout(out):
                    self.assertEqual(main(), 0)
                self.assertFalse(json.loads(out.getvalue())["model_evaluated"])
