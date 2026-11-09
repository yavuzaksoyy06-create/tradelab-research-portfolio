"""Integration tests for frozen-plan replay and the offline intent contract."""

import json
import unittest

import pandas as pd

from research_workspace.bot_order_draft import build_order_drafts, validate_order_draft
from research_workspace.bot_rehearsal import _sha, build_report, run_rehearsal, verify_report
from research_workspace.bot_strategy import make_strategy_plan
from research_workspace.equity_data import synthetic_fixture


class OrderDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.metadata = synthetic_fixture()
        cls.plan = make_strategy_plan("Bounded EMA", "SPY", max_position_bps=500, planned_risk_bps=15)
        cls.result = run_rehearsal(cls.frame, cls.metadata, plan=cls.plan)
        cls.payload = build_report(*cls.result)

    def test_frozen_plan_drives_risk_caps_and_binds_to_ledger(self):
        summary, _, journal = self.result
        self.assertEqual(summary["strategy_plan"], self.plan)
        self.assertEqual(summary["policy"]["strategy_plan_sha256"], self.plan["sha256"])
        self.assertEqual(journal[0]["policy_sha256"], summary["policy_sha256"])
        buys = [e for e in journal if e["kind"] == "FILL" and e["side"] == "BUY"]
        self.assertTrue(buys)
        for fill in buys:
            self.assertLessEqual(fill["planned_risk"], fill["equity_before"] * .0015)
            self.assertLessEqual(fill["price"] * fill["quantity"] + fill["fee"], fill["equity_before"] * .05)
        self.assertEqual(verify_report(self.payload)["summary"], summary)

    def test_channel_plan_uses_closed_prefix_and_produces_distinct_intents(self):
        plan = make_strategy_plan("Range break", "SPY", rule="channel_breakout")
        full = run_rehearsal(self.frame, self.metadata, plan=plan)
        changed = self.frame.copy()
        changed.loc[60:, ["open", "high", "low", "close"]] *= 3
        prefix = run_rehearsal(changed, self.metadata, plan=plan, visible_count=60)
        pd.testing.assert_frame_equal(prefix[1], full[1].iloc[:60].reset_index(drop=True))
        self.assertEqual(prefix[2], [event for event in full[2] if event["bar_index"] < 60])
        channel = [e["bar_index"] for e in full[2] if e["kind"] == "INTENT"]
        ema = [e["bar_index"] for e in self.result[2] if e["kind"] == "INTENT"]
        self.assertTrue(channel)
        self.assertNotEqual(channel, ema)

    def test_plan_symbol_and_recomputed_report_hash_cannot_change_risk_binding(self):
        other_symbol = make_strategy_plan("Other asset", "QQQ")
        with self.assertRaisesRegex(ValueError, "SYMBOL_MISMATCH"):
            run_rehearsal(self.frame, self.metadata, plan=other_symbol)
        modified = json.loads(self.payload)
        modified["content"]["summary"]["strategy_plan"] = make_strategy_plan("Different cap", "SPY")
        modified["sha256"] = _sha(modified["content"])
        with self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
            verify_report(json.dumps(modified).encode())
        with self.assertRaisesRegex(ValueError, "PLAN_MISMATCH"):
            build_order_drafts(self.payload, make_strategy_plan("Different cap", "SPY"))

    def test_drafts_represent_only_sized_signal_fills_and_are_deterministic(self):
        _, _, journal = self.result
        drafts = build_order_drafts(self.payload, self.plan)
        self.assertEqual(drafts, build_order_drafts(self.payload, self.plan))
        fills = [e for e in journal if e["kind"] == "FILL" and e["intent_id"] is not None]
        self.assertGreater(len(fills), 0)
        self.assertEqual(len(fills), len(drafts))
        self.assertLess(len(fills), sum(e["kind"] == "FILL" for e in journal))
        for fill, draft in zip(fills, drafts):
            content = validate_order_draft(draft)
            self.assertEqual(content["quantity"], fill["quantity"])
            self.assertEqual(content["execution_index"], content["signal_index"] + 1)
            self.assertEqual(content["simulated_at"], content["signal_at"])
            self.assertIs(content["dispatch_allowed"], False)
            self.assertTrue(content["synthetic"])

    def test_delayed_report_drafts_require_exact_index_and_clock_lag(self):
        payload = build_report(*run_rehearsal(self.frame, self.metadata, plan=self.plan, scenario="delay_1_bar"))
        drafts = build_order_drafts(payload, self.plan)
        self.assertTrue(drafts)
        for draft in drafts:
            row = validate_order_draft(draft)
            self.assertEqual(row["execution_index"] - row["signal_index"], 2)
            self.assertEqual(pd.Timestamp(row["simulated_at"]) - pd.Timestamp(row["signal_at"]), pd.Timedelta(minutes=15))

    def test_pending_close_is_preserved_without_invented_draft(self):
        first = next(e for e in self.result[2] if e["kind"] == "INTENT")
        short = run_rehearsal(self.frame, self.metadata, plan=self.plan, visible_count=first["bar_index"] + 1)
        self.assertIsNotNone(short[0]["pending_intent"])
        self.assertEqual(build_order_drafts(build_report(*short), self.plan), [])
        old_payload = build_report(*run_rehearsal(self.frame, self.metadata, visible_count=30))
        self.assertNotIn("strategy_plan", verify_report(old_payload)["summary"])
        with self.assertRaisesRegex(ValueError, "PLAN_MISMATCH"):
            build_order_drafts(old_payload, self.plan)

    def test_rehashed_draft_cannot_gain_dispatch_or_violate_causality(self):
        draft = build_order_drafts(self.payload, self.plan)[0]
        for key, replacement in (("dispatch_allowed", True), ("quantity", True),
                                 ("simulated_at", "2026-10-26T14:30:00+00:00"),
                                 ("execution_index", draft["content"]["signal_index"])):
            with self.subTest(key=key):
                content = {**draft["content"], key: replacement}
                with self.assertRaises(ValueError):
                    validate_order_draft({"content": content, "sha256": _sha(content)})

    def test_duplicate_report_fields_are_rejected_before_draft_conversion(self):
        duplicate = self.payload.replace(b'"holdout_scored":false', b'"holdout_scored":true,"holdout_scored":false', 1)
        self.assertNotEqual(duplicate, self.payload)
        with self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
            build_order_drafts(duplicate, self.plan)

    def test_rehashed_report_cannot_include_sealed_curve_or_move_replay_bound(self):
        for change in ("sealed_date", "reserved_rows"):
            with self.subTest(change=change):
                document = json.loads(self.payload)
                report = document["content"]
                if change == "sealed_date":
                    report["curve"][-1]["timestamp"] = "2026-10-26T14:30:00+00:00"
                else:
                    report["summary"]["reserved_snapshot_bars"] = -1
                document["sha256"] = _sha(report)
                with self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
                    build_order_drafts(json.dumps(document).encode(), self.plan)
