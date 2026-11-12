"""Execution sensitivity and causal diagnostics; no market claims or accounts."""
import copy
import json
import unittest
from unittest.mock import patch

import pandas as pd

from research_workspace import bot_stress as stress
from research_workspace.bot_rehearsal import run_rehearsal
from research_workspace.bot_strategy import make_strategy_plan
from research_workspace.equity_data import synthetic_fixture
from research_workspace.stage7_events import research_partition


class BotStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.meta = synthetic_fixture()
        cls.report = stress.run_stress_suite(cls.frame, cls.meta)

    def test_registered_cases_do_not_select_winner_or_promote_model(self):
        report = self.report["content"]
        self.assertNotIn("strategy_plan", report)
        self.assertEqual(report["status"], "PASSED_DIAGNOSTICS")
        self.assertEqual(report["scenarios"], list(stress.SCENARIOS))
        expected = ((3., 5., 0), (10., 15., 0), (3., 5., 1), (10., 15., 1))
        for row, settings in zip(report["comparison"], expected):
            self.assertEqual((row["fee_bps"], row["slippage_bps"], row["additional_delay_bars"]), settings)
            self.assertTrue(row["synthetic"])
            self.assertEqual(row["real_orders_sent"], 0)
            self.assertEqual(row["paper_orders_sent"], 0)
            self.assertEqual(row["model_fits"], 0)
        self.assertFalse(report["strategy_promoted"])
        self.assertFalse(report["winning_scenario_selected"])
        self.assertFalse(report["holdout_scored"])
        self.assertEqual(report["ise_reserved_rows"], 108)
        self.assertFalse(report["source_independently_verified"])
        self.assertFalse(report["point_in_time_vintage_verified"])

    def test_statistics_match_independent_baseline_accounting(self):
        summary, curve, journal = run_rehearsal(self.frame, self.meta)
        row = self.report["content"]["comparison"][0]
        path = [100000., *curve.equity.tolist()]
        drawdowns = [value / max(path[:i+1]) - 1 for i, value in enumerate(path)][1:]
        self.assertAlmostEqual(row["max_drawdown"], min(drawdowns), places=14)
        self.assertAlmostEqual(row["net_pnl"], summary["realized_pnl"] + summary["unrealized_pnl"], places=8)
        fills = [event for event in journal if event["kind"] == "FILL"]
        self.assertEqual(row["fill_count"], len(fills))
        self.assertAlmostEqual(row["total_fees"], sum(event["fee"] for event in fills), places=9)
        self.assertAlmostEqual(row["mean_gross_exposure"], sum(
            float(point.position * point.close / point.equity) for point in curve.itertuples()) / len(curve), places=14)
        self.assertEqual(row["entries"], row["exits"])
        self.assertGreater(self.report["content"]["comparison"][1]["total_fees"], row["total_fees"])

    def test_prefixes_future_suffix_and_halt_are_exercised(self):
        diagnostics = self.report["content"]["diagnostics"]
        self.assertEqual(diagnostics["prefix_replay"]["checked_prefixes"], 3)
        self.assertTrue(all(row["passed"] for row in diagnostics["prefix_replay"]["checks"]))
        self.assertEqual(diagnostics["future_suffix"]["status"], "PASSED")
        self.assertTrue(diagnostics["future_suffix"]["artificial_scenario"])
        self.assertEqual(diagnostics["manual_halt"]["status"], "PASSED")
        self.assertEqual(diagnostics["manual_halt"]["entries_after_halt"], 0)
        self.assertEqual(diagnostics["manual_halt"]["ending_position"], 0)
        self.assertEqual([row["case"] for row in diagnostics["source_guards"]],
                         ["missing_bar", "duplicate_bar", "sealed_date"])
        self.assertTrue(all(row["passed"] for row in diagnostics["source_guards"]))
        self.assertEqual(diagnostics["journal_recovery"]["status"], "PASSED")
        self.assertEqual(len(diagnostics["journal_recovery"]["cases"]), 4)
        self.assertTrue(all(row["terminal_head_verified"] and row["passed"] for row in
                            diagnostics["journal_recovery"]["cases"]))

    def test_rehashed_account_corruption_is_a_failed_diagnostic(self):
        def corrupt(*args, **kwargs):
            summary, curve, journal = run_rehearsal(*args, **kwargs)
            if kwargs.get("scenario") == "baseline":
                journal = copy.deepcopy(journal)
                next(event for event in journal if event["kind"] == "FILL")["cash_after"] += 1
                previous = "0" * 64
                for event in journal:
                    event["previous_sha256"] = previous
                    event["sha256"] = stress._sha({key: value for key, value in event.items() if key != "sha256"})
                    previous = event["sha256"]
                summary = {**summary, "journal_head_sha256": previous}
            return summary, curve, journal
        with patch.object(stress, "run_rehearsal", side_effect=corrupt):
            report = stress.run_stress_suite(self.frame, self.meta)["content"]
        self.assertEqual(report["status"], "FAILED_DIAGNOSTICS")
        recovery = report["diagnostics"]["journal_recovery"]
        self.assertEqual(recovery["status"], "FAILED")
        self.assertEqual(recovery["cases"][0]["status"], "REJECTED_SEMANTICS")
        self.assertTrue(all(case["passed"] for case in recovery["cases"][1:]))

    def test_causal_probe_detects_a_future_dependent_curve(self):
        n = len(self.frame)
        def corrupt(*args, **kwargs):
            summary, curve, journal = run_rehearsal(*args, **kwargs)
            if kwargs.get("visible_count", n) < n:
                curve = curve.copy()
                curve.loc[0, "equity"] += 1
            return summary, curve, journal
        with patch.object(stress, "run_rehearsal", side_effect=corrupt):
            report = stress.run_stress_suite(self.frame, self.meta)["content"]
        self.assertEqual(report["status"], "FAILED_DIAGNOSTICS")
        self.assertEqual(report["diagnostics"]["prefix_replay"]["status"], "FAILED")
        self.assertEqual(report["diagnostics"]["future_suffix"]["status"], "FAILED")

    def test_event_probe_detects_omitted_final_close_intent(self):
        n = len(self.frame)
        def corrupt(*args, **kwargs):
            summary, curve, journal = run_rehearsal(*args, **kwargs)
            if kwargs.get("visible_count", n) < n:
                journal = journal[:-1]
            return summary, curve, journal
        with patch.object(stress, "run_rehearsal", side_effect=corrupt):
            report = stress.run_stress_suite(self.frame, self.meta)["content"]
        self.assertEqual(report["status"], "FAILED_DIAGNOSTICS")
        self.assertTrue(any(not row["journal_identical"] for row in report["diagnostics"]["prefix_replay"]["checks"]))

    def test_guard_probe_reports_acceptance_instead_of_claiming_pass(self):
        with patch.object(stress, "validated_history", return_value=self.frame):
            report = stress.run_stress_suite(self.frame, self.meta)["content"]
        self.assertEqual(report["status"], "FAILED_DIAGNOSTICS")
        self.assertTrue(all(row["status"] == "UNEXPECTEDLY_ACCEPTED" for row in report["diagnostics"]["source_guards"]))

    def test_registered_source_mutation_is_rejected_without_rebinding(self):
        meta = {**self.meta, "research_partition": research_partition(self.frame)}
        before = copy.deepcopy(meta)
        report = stress.run_stress_suite(self.frame, meta)["content"]
        probe = report["diagnostics"]["future_suffix"]
        self.assertEqual(probe["status"], "REJECTED_AT_SOURCE_BINDING")
        self.assertTrue(probe["source_binding_preserved"])
        self.assertEqual(meta, before)

    def test_repeatability_inputs_and_export_tamper_checks(self):
        frame = self.frame.copy(deep=True)
        metadata = copy.deepcopy(self.meta)
        report = stress.run_stress_suite(frame, metadata)
        self.assertEqual(report, self.report)
        self.assertEqual(stress.verify_stress_report(report), report["content"])
        json.dumps(report, allow_nan=False)
        pd.testing.assert_frame_equal(frame, self.frame)
        self.assertEqual(metadata, self.meta)
        broken = copy.deepcopy(report)
        broken["content"]["comparison"][0]["net_pnl"] += 1
        with self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
            stress.verify_stress_report(broken)
        broken = copy.deepcopy(report)
        broken["content"]["comparison"][0]["real_orders_sent"] = True
        broken["sha256"] = stress._sha(broken["content"])
        with self.assertRaises(ValueError):
            stress.verify_stress_report(broken)

    def test_tiny_prefix_is_partial_and_invalid_count_never_runs_engine(self):
        report = stress.run_stress_suite(self.frame, self.meta, visible_count=1)["content"]
        self.assertEqual(report["status"], "PARTIAL_DIAGNOSTICS")
        self.assertEqual(report["diagnostics"]["manual_halt"]["status"], "NOT_EXERCISED_NO_ELIGIBLE_ENTRY")
        with patch.object(stress, "run_rehearsal") as engine:
            for count in (True, 0, -1, len(self.frame) + 1, 3.5):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    stress.run_stress_suite(self.frame, self.meta, visible_count=count)
            engine.assert_not_called()

    def test_stress_freezes_one_plan_across_cases_and_causal_probes(self):
        plan = make_strategy_plan("QQQ channel", "QQQ", rule="channel_breakout",
                                  fast=2, slow=6, max_position_bps=700, planned_risk_bps=20)
        frame, metadata = synthetic_fixture("QQQ")
        with patch.object(stress, "run_rehearsal", wraps=run_rehearsal) as replay:
            report = stress.run_stress_suite(frame, metadata, visible_count=130, plan=plan)
        content = stress.verify_stress_report(report)
        self.assertEqual(content["strategy_plan"], plan)
        self.assertEqual(content["status"], "PASSED_DIAGNOSTICS")
        self.assertEqual(content["diagnostics"]["prefix_replay"]["status"], "PASSED")
        self.assertEqual(content["diagnostics"]["future_suffix"]["status"], "PASSED")
        self.assertEqual(content["diagnostics"]["manual_halt"]["status"], "PASSED")
        self.assertGreater(replay.call_count, len(stress.SCENARIOS))
        for call in replay.call_args_list:
            self.assertEqual(call.kwargs["plan"], plan)
            self.assertIsNot(call.kwargs["plan"], plan)
        for row in content["comparison"]:
            expected, _, _ = run_rehearsal(frame, metadata, visible_count=130,
                                            plan=plan, scenario=row["scenario"])
            self.assertEqual(row["policy_sha256"], expected["policy_sha256"])
            self.assertEqual(row["ending_equity"], expected["ending_equity"])

        for replacement in (None, make_strategy_plan("Renamed", "QQQ", rule="channel_breakout",
                                                      fast=2, slow=6, max_position_bps=700,
                                                      planned_risk_bps=20)):
            with self.subTest(replacement=replacement):
                broken = copy.deepcopy(report)
                del broken["content"]["strategy_plan"]
                if replacement is not None:
                    broken["content"]["strategy_plan"] = replacement
                broken["sha256"] = stress._sha(broken["content"])
                with self.assertRaisesRegex(ValueError, "BOT_STRESS_REPORT_REJECTED"):
                    stress.verify_stress_report(broken)

    def test_wrong_symbol_and_invalid_plan_never_reach_rehearsal(self):
        plan = make_strategy_plan("Wrong symbol", "MSFT")
        invalid = dict(plan, sha256="0" * 64)
        with patch.object(stress, "run_rehearsal") as replay:
            with self.assertRaisesRegex(ValueError, "BOT_STRESS_STRATEGY_SYMBOL_MISMATCH"):
                stress.run_stress_suite(self.frame, self.meta, plan=plan)
            with self.assertRaisesRegex(ValueError, "BOT_STRATEGY_PLAN_DIGEST"):
                stress.run_stress_suite(self.frame, self.meta, plan=invalid)
            replay.assert_not_called()
