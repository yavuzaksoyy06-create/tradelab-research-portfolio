"""Exclusive local evidence publication and sanitized offline command errors."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.bot_rehearsal import main


class BotCommandTests(unittest.TestCase):
    def test_demo_report_verifies_and_existing_output_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            target = Path(tmp) / "rehearsal.json"
            self.assertEqual(main(["rehearsal", "--output", str(target), "--visible-count", "40"]), 0)
            original = target.read_bytes()
            self.assertEqual(main(["verify", "--report", str(target)]), 0)
            self.assertEqual(main(["rehearsal", "--output", str(target)]), 1)
            self.assertEqual(target.read_bytes(), original)

    def test_failure_does_not_create_output_or_print_private_details(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(StringIO()), redirect_stderr(StringIO()) as error:
            target = Path(tmp) / "not-created.json"
            with patch("tools.bot_rehearsal.synthetic_fixture", side_effect=ValueError("SECRET_PRIVATE_PATH")):
                self.assertEqual(main(["rehearsal", "--output", str(target)]), 1)
            self.assertFalse(target.exists())
            self.assertNotIn("SECRET", error.getvalue())

    def test_relative_or_network_output_rejected_before_source_load(self):
        with patch("tools.bot_rehearsal.synthetic_fixture") as data, redirect_stderr(StringIO()):
            for destination in ("relative.json", r"\\server\share\report.json"):
                self.assertEqual(main(["rehearsal", "--output", destination]), 1)
            data.assert_not_called()

    def test_stress_cli_publishes_and_verifies_fixed_case_report(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            target = Path(tmp) / "stress.json"
            self.assertEqual(main(["stress", "--output", str(target), "--visible-count", "50"]), 0)
            self.assertEqual(main(["verify", "--report", str(target)]), 0)
