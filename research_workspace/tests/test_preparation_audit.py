"""Adversarial review checks use simulated snapshots, never private market data."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import unittest
from unittest.mock import patch

from research_workspace.equity_data import MAX_BYTES, synthetic_fixture
from research_workspace.stage7_history import load_private, save_private
from research_workspace.stage7_review import _digests, review_snapshot


class PreparationAuditTests(unittest.TestCase):
    def snapshot(self, directory):
        frame, meta = synthetic_fixture()
        meta.update(synthetic=False, feed="sip", adjustment="split",
                    expected_bars=len(frame), received_bars=len(frame))
        save_private(frame, meta, directory)
        return directory

    def test_transient_snapshot_change_cannot_misbind_report_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            manifest = folder / "manifest.json"
            original = manifest.read_bytes()
            changed = json.loads(original)
            changed["symbol"] = "QQQ"
            pinned = _digests(folder)
            calls = []

            def transient(_):
                calls.append(None)
                if len(calls) == 1:
                    # Snapshot A is hashed, then a valid B is read by the loader.
                    manifest.write_text(json.dumps(changed), encoding="utf-8")
                else:
                    # Restoring A before the after-hash defeated the old check.
                    manifest.write_bytes(original)
                return pinned

            with patch("research_workspace.stage7_review._digests", side_effect=transient):
                report = review_snapshot(folder)
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["reason"], "SNAPSHOT_CHANGED")

    def test_loader_bounds_actual_read_even_when_stat_reports_smaller_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            (folder / "bars.csv").write_bytes(b"x" * (MAX_BYTES + 1))
            stat = Path.stat

            def small(path, *args, **kwargs):
                return SimpleNamespace(st_size=0) if path.name == "bars.csv" else stat(path, *args, **kwargs)

            with patch.object(Path, "stat", small):
                with self.assertRaisesRegex(ValueError, "bounded input size"):
                    load_private(folder)

    def test_manifest_byte_count_must_match_consumed_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self.snapshot(Path(tmp) / "snapshot")
            path = folder / "manifest.json"
            meta = json.loads(path.read_text(encoding="utf-8"))
            meta["bytes"] = 0
            path.write_text(json.dumps(meta), encoding="utf-8")
            self.assertEqual(review_snapshot(folder).get("reason"), "MANIFEST_MISMATCH")

    def test_optional_coverage_metadata_cannot_contradict_validated_bars(self):
        for field, value in (("missing_bars", 1), ("sessions", 999), ("received_bars", True)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                folder = self.snapshot(Path(tmp) / "snapshot")
                path = folder / "manifest.json"
                meta = json.loads(path.read_text(encoding="utf-8"))
                meta[field] = value
                path.write_text(json.dumps(meta), encoding="utf-8")
                self.assertEqual(review_snapshot(folder).get("reason"), "COVERAGE_MISMATCH")
