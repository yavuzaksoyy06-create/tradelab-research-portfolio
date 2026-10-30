"""Private BIST publication checks using simulated, explicitly entitled fixtures."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_workspace.bist_store import register, read_snapshot
from research_workspace.tests import test_bist_research as fixtures
from tools.bist_research import main


class BISTStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.BISTResearchTests.setUpClass()
        cls.fixture = fixtures.BISTResearchTests()

    def test_invalid_input_never_creates_destination(self):
        payload, meta = self.fixture.pack()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "not_created"
            with self.assertRaises(ValueError):
                register(payload + b"\n", meta, folder)
            self.assertFalse(folder.exists())

    def test_git_ancestor_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            (parent / ".git").mkdir()
            folder = parent / "nested" / "snapshot"
            with self.assertRaisesRegex(ValueError, "PRIVATE_DESTINATION_REQUIRED"):
                register(*self.fixture.pack(), folder)
            self.assertFalse(folder.parent.exists())

    def test_registration_roundtrip_is_immutable_and_preserves_original_bytes(self):
        payload, meta = self.fixture.pack(api_key="TEST_SENTINEL_NOT_COPIED")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "snapshot"
            register(payload, meta, folder)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            frame, safe = read_snapshot(folder)
            self.assertEqual(before["bars.csv"], payload)
            self.assertEqual(len(frame), safe["bars"])
            self.assertNotIn("TEST_SENTINEL", before["manifest.json"].decode())
            with self.assertRaises(FileExistsError):
                register(payload, meta, folder)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})

    def test_tampered_bytes_and_registration_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "snapshot"
            register(*self.fixture.pack(), folder)
            bars, manifest = folder / "bars.csv", folder / "manifest.json"
            original = bars.read_bytes()
            bars.write_bytes(original + b"\n")
            with self.assertRaises(ValueError):
                read_snapshot(folder)
            bars.write_bytes(original)
            pristine = json.loads(manifest.read_text(encoding="utf-8"))
            for changes in ({"canonical_sha256": "0" * 64}, {"protocol": "other"}, {"bytes": True},
                            {"registration_sha256": "0" * 64}, {"symbol": "GARAN"}):
                manifest.write_text(json.dumps({**pristine, **changes}), encoding="utf-8")
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    read_snapshot(folder)

    def test_cli_requires_rights_before_any_input_read_and_sanitizes_error(self):
        error = StringIO()
        argv = ["bist_research.py", "register", "--input", "SECRET_SOURCE", "--symbol", "THYAO",
                "--provider", "fixture", "--source-url", "https://example.test/history",
                "--license-reference", "fixture", "--output", "SECRET_DESTINATION"]
        with patch("sys.argv", argv), redirect_stderr(error), \
             patch.object(Path, "open", side_effect=AssertionError("Must not read without rights")) as opened:
            self.assertEqual(main(), 1)
            opened.assert_not_called()
        self.assertNotIn("SECRET", error.getvalue())

    def test_cli_registered_snapshot_evaluation_is_price_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "snapshot"
            register(*self.fixture.pack(), folder)
            out = StringIO()
            with patch("sys.argv", ["bist_research.py", "evaluate", "--snapshot", str(folder)]), redirect_stdout(out):
                self.assertEqual(main(), 0)
            report = json.loads(out.getvalue())
            self.assertFalse(report["orders_enabled"])
            self.assertFalse(report["holdout_scored"])
            self.assertNotIn("adjusted_close", report)
            self.assertNotIn(str(folder), out.getvalue())
