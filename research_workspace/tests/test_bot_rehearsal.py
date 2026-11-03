"""Offline execution accounting and adversarial causal boundaries; simulated bars."""
import hashlib
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research_workspace import bot_rehearsal as bot
from research_workspace.equity_data import synthetic_fixture, REQUIRED
from research_workspace.stage7_events import replay_limit
from research_sr_v4.data import expected_grid


class BotRehearsalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.meta = synthetic_fixture()

    def trend(self):
        frame = self.frame.copy()
        close = 100 + np.arange(len(frame)) * .1
        frame["open"] = close - .05
        frame["close"] = close
        frame["high"] = close + .2
        frame["low"] = close - .2
        return frame

    def test_first_fill_follows_completed_signal_and_integer_risk_caps(self):
        s, c, j = bot.run_rehearsal(self.trend(), self.meta)
        intents = {e["id"]: e for e in j if e["kind"] == "INTENT"}
        fills = [e for e in j if e["kind"] == "FILL"]
        first = next(e for e in fills if e["side"] == "BUY")
        self.assertEqual(first["bar_index"], 21)
        for fill in fills:
            if fill["side"] == "BUY":
                intent = intents[fill["intent_id"]]
                self.assertEqual(fill["bar_index"], intent["signal_index"] + 1)
                self.assertEqual(fill["timestamp"], intent["timestamp"])
                self.assertIs(type(fill["quantity"]), int)
                self.assertGreater(fill["quantity"], 0)
                self.assertLessEqual(fill["quantity"] * fill["price"] + fill["fee"], fill["equity_before"] * .1 + 1e-8)
                self.assertLessEqual(fill["planned_risk"], fill["equity_before"] * .005 + 1e-8)
        ids = [e["intent_id"] for e in fills if e["intent_id"] is not None]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(s["strategy_validated"])
        self.assertFalse(s["economic_performance_claim"])
        self.assertEqual(s["real_orders_sent"], 0)
        self.assertEqual(s["paper_orders_sent"], 0)

    def test_independent_cash_fee_position_and_pnl_ledger(self):
        s, c, j = bot.run_rehearsal(self.frame, self.meta)
        cash, qty, fees = 100_000., 0, 0.
        for e in j:
            if e["kind"] != "FILL":
                continue
            notional = e["quantity"] * e["price"]
            self.assertAlmostEqual(e["fee"], notional * .0003, places=10)
            if e["side"] == "BUY":
                self.assertEqual(qty, 0)
                cash -= notional + e["fee"]
                qty = e["quantity"]
            else:
                self.assertEqual(qty, e["quantity"])
                cash += notional - e["fee"]
                qty = 0
            fees += e["fee"]
            self.assertAlmostEqual(e["cash_after"], cash, places=9)
            self.assertEqual(e["position_after"], qty)
        self.assertAlmostEqual(s["ending_cash"], cash, places=9)
        self.assertAlmostEqual(s["total_fees"], fees, places=9)
        self.assertEqual(s["ending_position"], qty)
        np.testing.assert_allclose(c.equity, c.cash + c.position * c.close, rtol=0, atol=1e-8)
        self.assertAlmostEqual(s["ending_equity"] - 100_000, s["realized_pnl"] + s["unrealized_pnl"], places=8)

    def test_both_intrabar_levels_choose_stop_and_adverse_slippage(self):
        frame = self.trend()
        frame.loc[21, ["high", "low"]] = [110., 95.]
        _, _, journal = bot.run_rehearsal(frame, self.meta, visible_count=25)
        buy, sell = [e for e in journal if e["kind"] == "FILL"][:2]
        self.assertEqual(sell["reason"], "STOP_FIRST")
        self.assertEqual(buy["bar_index"], sell["bar_index"])
        self.assertAlmostEqual(sell["price"], buy["stop"] * .9995)

    def test_open_gap_loss_uses_open_and_latches_risk_halt(self):
        frame = self.trend()
        frame.loc[22, ["open", "high", "low", "close"]] = [70., 70.5, 69., 70.]
        s, _, journal = bot.run_rehearsal(frame, self.meta)
        gap = next(e for e in journal if e.get("reason") == "STOP_GAP")
        self.assertAlmostEqual(gap["price"], 70 * .9995)
        self.assertLess(gap["realized_pnl"], -2000)
        halt = next(e for e in journal if e["kind"] == "HALT")
        self.assertEqual(halt["reason"], "SESSION_LOSS_LIMIT")
        self.assertTrue(s["halted"])
        self.assertFalse(any(e["kind"] == "FILL" and e["side"] == "BUY" and e["sequence"] > halt["sequence"] for e in journal))

    def test_manual_halt_cancels_pending_entry_and_closes_open_position(self):
        for at, expected_buys, expected_sells in ((21, 0, 0), (22, 1, 1)):
            s, _, j = bot.run_rehearsal(self.trend(), self.meta, visible_count=40, halt_at=at)
            self.assertTrue(s["halted"])
            self.assertEqual(s["ending_position"], 0)
            self.assertEqual(sum(e["kind"] == "FILL" and e["side"] == "BUY" for e in j), expected_buys)
            self.assertEqual(sum(e["kind"] == "FILL" and e["side"] == "SELL" for e in j), expected_sells)
            if at == 21:
                self.assertTrue(any(e["kind"] == "CANCEL" for e in j))
            else:
                self.assertTrue(any(e.get("reason") == "MANUAL_HALT" and e["kind"] == "FILL" for e in j))

    def test_time_exit_session_flatten_and_unfinished_replay_marks(self):
        frame = self.trend()
        s, c, j = bot.run_rehearsal(frame, self.meta)
        buys = [e for e in j if e["kind"] == "FILL" and e["side"] == "BUY"]
        sells = [e for e in j if e["kind"] == "FILL" and e["side"] == "SELL"]
        self.assertEqual(sells[0]["reason"], "TIME_EXIT")
        self.assertEqual(sells[0]["bar_index"] - buys[0]["bar_index"], 3)
        session_ends = frame.index[frame.bar_end == frame.session_close]
        self.assertTrue((c.loc[session_ends, "position"] == 0).all())
        short, prefix, events = bot.run_rehearsal(frame, self.meta, visible_count=23)
        self.assertGreater(short["ending_position"], 0)
        self.assertFalse(any(e["kind"] == "FILL" and e["side"] == "SELL" for e in events))
        pd.testing.assert_frame_equal(prefix, c.iloc[:23].reset_index(drop=True))

    def test_prefix_invariance_and_repeat_runs_do_not_mutate_inputs(self):
        frame = self.trend()
        before = frame.copy(deep=True)
        first, curve, journal = bot.run_rehearsal(frame, self.meta, visible_count=60)
        changed = frame.copy()
        changed.loc[60:, ["open", "high", "low", "close"]] *= 10
        _, again, _ = bot.run_rehearsal(changed, self.meta, visible_count=60)
        pd.testing.assert_frame_equal(curve, again)
        second, repeated, events = bot.run_rehearsal(frame, self.meta, visible_count=60)
        self.assertEqual(first, second)
        self.assertEqual(journal, events)
        pd.testing.assert_frame_equal(curve, repeated)
        pd.testing.assert_frame_equal(frame, before)

    def test_last_completed_close_emits_unfilled_intent_without_future_bar(self):
        frame = self.trend()
        short, _, journal = bot.run_rehearsal(frame, self.meta, visible_count=21)
        _, _, full = bot.run_rehearsal(frame, self.meta, visible_count=30)
        first_signal = next(e for e in full if e["kind"] == "INTENT")
        self.assertEqual(first_signal["bar_index"], 20)
        self.assertEqual(journal[-1], first_signal)
        self.assertEqual(short["pending_intent"]["execute_index"], 21)
        self.assertEqual(short["ending_position"], 0)

    def test_full_snapshot_holdout_cannot_be_moved_by_replay(self):
        grid = expected_grid("2025-01-02", "2025-06-30")
        sessions = grid.session.drop_duplicates().iloc[:80]
        frame = grid[grid.session.isin(sessions)].copy()
        frame["open"], frame["high"], frame["low"], frame["close"], frame["volume"] = 100., 101., 99., 100., 1000.
        boundary = replay_limit(frame)
        self.assertEqual(frame.iloc[boundary:].session.nunique(), 20)
        s, c, _ = bot.run_rehearsal(frame, self.meta, visible_count=30)
        self.assertEqual(s["replay_limit"], boundary)
        self.assertEqual(s["reserved_snapshot_bars"], len(frame) - boundary)
        self.assertEqual(len(c), 30)
        with self.assertRaisesRegex(ValueError, "RESERVED"):
            bot.run_rehearsal(frame, self.meta, visible_count=boundary + 1)

    def test_invalid_indices_sealed_dates_and_return_only_data_fail(self):
        for count in (True, 0, -1, len(self.frame) + 1, 5.):
            with self.subTest(count=count), self.assertRaises(ValueError):
                bot.run_rehearsal(self.frame, self.meta, visible_count=count)
        for halt in (True, -1, 30, 2.5):
            with self.subTest(halt=halt), self.assertRaises(ValueError):
                bot.run_rehearsal(self.frame, self.meta, visible_count=30, halt_at=halt)
        sealed = self.frame.copy()
        sealed["timestamp"] = sealed.timestamp + pd.Timedelta(days=30)
        with self.assertRaisesRegex(ValueError, "sealed"):
            bot.run_rehearsal(sealed, self.meta)
        with self.assertRaises((ValueError, AttributeError, KeyError)):
            bot.run_rehearsal(pd.DataFrame({"date": ["2010-01-04"], "ise_try": [.01]}), {"orders_enabled": False})

    def test_report_outer_digest_chain_and_bounds_are_verified(self):
        s, c, j = bot.run_rehearsal(self.frame, self.meta)
        payload = bot.build_report(s, c, j)
        self.assertEqual(bot.verify_report(payload)["summary"], s)
        for outer_rehash in (False, True):
            report = json.loads(payload)
            report["content"]["journal"][0]["starting_cash"] = 1
            if outer_rehash:
                report["sha256"] = bot._sha(report["content"])
            with self.subTest(rehash=outer_rehash), self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
                bot.verify_report(json.dumps(report).encode())
        report = json.loads(payload)
        report["content"]["summary"]["real_orders_sent"] = True
        report["sha256"] = bot._sha(report["content"])
        with self.assertRaises(ValueError):
            bot.verify_report(json.dumps(report).encode())
        for bad in (b"", b"\xff", b"[]", b"{}"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bot.verify_report(bad)

    def test_no_external_adapter_even_after_gate_clock_or_readiness_changes(self):
        status = bot.readiness_report()
        self.assertFalse(status["broker_adapter_present"])
        self.assertFalse(status["real_orders_enabled"])
        self.assertFalse(status["paper_orders_enabled"])
        self.assertEqual(status["reserved_ise_rows"], 108)
        status["real_orders_enabled"] = True
        with patch("socket.socket", side_effect=AssertionError("No network in offline replay")):
            summary, _, _ = bot.run_rehearsal(self.frame, self.meta, visible_count=30)
        self.assertEqual(summary["real_orders_sent"], 0)
        self.assertFalse(bot.readiness_report()["real_orders_enabled"])

    def test_delayed_intent_cancels_at_session_boundary_before_next_session(self):
        frame = self.trend()
        # First entry at22, stop exit23, fresh intent24 would execute26;
        # the closing bar25 must cancel it rather than carry it overnight.
        frame.loc[23, "low"] = 90.
        s, _, journal = bot.run_rehearsal(frame, self.meta, visible_count=28, scenario="delay_1_bar")
        crossing = next(e for e in journal if e["kind"] == "INTENT" and e["bar_index"] == 24)
        cancel = next(e for e in journal if e["kind"] == "CANCEL" and e["intent_id"] == crossing["id"])
        self.assertEqual(cancel["bar_index"], 25)
        self.assertEqual(cancel["reason"], "SESSION_END")
        self.assertFalse(any(e["kind"] == "FILL" and e["intent_id"] == crossing["id"] for e in journal))
        for event in journal:
            if event["kind"] == "INTENT":
                self.assertEqual(event["execute_index"], event["signal_index"] + 2)
        self.assertEqual(s["execution_assumptions"]["additional_delay_bars"], 1)

    def test_rehashed_curve_and_summary_cannot_forge_recovered_account(self):
        s, c, j = bot.run_rehearsal(self.frame, self.meta)
        report = json.loads(bot.build_report(s, c, j))
        for field in ("ending_cash", "total_fees", "policy_sha256"):
            broken = json.loads(json.dumps(report))
            value = broken["content"]["summary"][field]
            broken["content"]["summary"][field] = "0" * 64 if isinstance(value, str) else value + 10
            broken["sha256"] = bot._sha(broken["content"])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
                bot.verify_report(json.dumps(broken).encode())
        report["content"]["curve"][23]["cash"] += 1
        report["sha256"] = bot._sha(report["content"])
        with self.assertRaisesRegex(ValueError, "REPORT_REJECTED"):
            bot.verify_report(json.dumps(report).encode())

    def test_registered_scenarios_export_consistent_risk_cost_and_delay(self):
        for scenario in bot.SCENARIOS:
            with self.subTest(scenario=scenario):
                s, c, j = bot.run_rehearsal(self.frame, self.meta, scenario=scenario)
                self.assertEqual(bot.verify_report(bot.build_report(s, c, j))["summary"], s)
        for scenario in ("live", "paper", None, True, "custom_cheap_case"):
            with self.subTest(invalid=scenario), self.assertRaisesRegex(ValueError, "UNREGISTERED"):
                bot.run_rehearsal(self.frame, self.meta, scenario=scenario)
