"""Exclusive local evidence publication and sanitized offline command errors."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.bot_rehearsal import main
from research_workspace.bot_strategy import encode_strategy_plan, make_strategy_plan


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

    def test_frozen_plan_cli_stages_once_and_halt_survives_reopen(self):
        def invoke(args, *, code=0):
            with redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()):
                self.assertEqual(main(args), code)
            return json.loads(output.getvalue()) if code == 0 else None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, report, database = (str(root / name) for name in ("plan.json", "rehearsal.json", "intent.sqlite3"))
            Path(plan).write_bytes(encode_strategy_plan(make_strategy_plan("CLI channel", "QQQ", rule="channel_breakout")))
            run = ["rehearsal", "--plan", plan, "--output", report]
            self.assertTrue(invoke(run)["synthetic"])
            initial = invoke(["outbox", "init", "--db", database])["result"]["head_sha256"]
            stage = ["outbox", "stage", "--db", database, "--plan", plan, "--report", report]
            staged = invoke(stage + ["--expected-head", initial])["result"]
            self.assertGreater(staged["inserted"], 0)
            invoke(stage + ["--expected-head", initial], code=1)
            self.assertEqual(invoke(stage)["result"], {"inserted": 0, "duplicates": staged["inserted"]})
            inspected = invoke(["outbox", "inspect", "--db", database])["result"]
            self.assertEqual(inspected["drafts"][0]["draft"]["content"]["symbol"], "QQQ")
            halted = invoke(["outbox", "halt", "--db", database, "--expected-head", inspected["head_sha256"]])
            self.assertEqual(halted["result"]["cancelled"], staged["inserted"])
            recovered = invoke(["outbox", "recover", "--db", database])["result"]
            self.assertTrue(recovered["halted"])
            self.assertTrue(all(row["status"] == "CANCELLED" for row in recovered["drafts"]))
            invoke(stage, code=1)
