"""Independent accounting reconstruction and rehashed adversarial event journals."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from research_workspace.bot_ledger import recover_ledger
from research_workspace.bot_rehearsal import run_rehearsal
from research_workspace.equity_data import synthetic_fixture


def digest(value):
    # Test oracle deliberately does not import the production hash function.
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rehash(records):
    previous = "0" * 64
    for sequence, event in enumerate(records):
        event["sequence"], event["previous_sha256"] = sequence, previous
        event["sha256"] = digest({key: value for key, value in event.items() if key != "sha256"})
        previous = event["sha256"]
    return records


class BotLedgerTests(unittest.TestCase):
    def pack(self):
        start = datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc)
        def stamp(bar, close=False):
            return (start + timedelta(minutes=15 * (bar + int(close)))).isoformat()
        journal = [
            {"kind": "START", "bar_index": 0, "timestamp": stamp(0), "starting_cash": 1000.,
             "policy_sha256": "1" * 64, "symbol": "SPY", "synthetic": True},
            {"kind": "INTENT", "bar_index": 20, "timestamp": stamp(20, True),
             "id": "2" * 64, "side": "BUY", "signal_index": 20, "execute_index": 21},
            {"kind": "FILL", "bar_index": 21, "timestamp": stamp(21), "side": "BUY",
             "quantity": 5, "price": 100., "fee": 1., "reason": "EMA_PLUMBING_ONLY",
             "intent_id": "2" * 64, "cash_after": 499., "position_after": 5,
             "stop": 98., "target": 104., "planned_risk": 12., "equity_before": 1000.},
            {"kind": "INTENT", "bar_index": 22, "timestamp": stamp(22, True),
             "id": "3" * 64, "side": "SELL", "signal_index": 22, "execute_index": 23},
            {"kind": "FILL", "bar_index": 23, "timestamp": stamp(23), "side": "SELL",
             "quantity": 5, "price": 103., "fee": 1., "reason": "SIGNAL_EXIT",
             "intent_id": "3" * 64, "cash_after": 1013., "position_after": 0, "realized_pnl": 13.},
        ]
        return rehash(journal)

    def test_independent_fill_math_recovers_account_not_asserted_balances(self):
        journal = self.pack()
        report = recover_ledger(journal, journal[-1]["sha256"])
        self.assertEqual(report["starting_cash"], 1000.)
        self.assertEqual(report["ending_cash"], 1000 - 5*100 - 1 + 5*103 - 1)
        self.assertEqual(report["total_fees"], 2.)
        self.assertEqual(report["realized_pnl"], 13.)
        self.assertEqual(report["ending_position"], 0)
        self.assertEqual(report["buy_fills"], 1)
        self.assertEqual(report["sell_fills"], 1)
        self.assertFalse(report["complete_prefix_only"])
        self.assertFalse(report["broker_recovery_supported"])
        self.assertFalse(report["orders_enabled"])

    def test_expected_head_rejects_valid_truncation_without_claiming_completeness(self):
        journal = self.pack()
        prefix = journal[:3]
        recovered = recover_ledger(prefix)
        self.assertTrue(recovered["complete_prefix_only"])
        self.assertEqual(recovered["ending_position"], 5)
        self.assertEqual(recovered["entry_cost"], 501.)
        with self.assertRaisesRegex(ValueError, "BOT_LEDGER_REJECTED"):
            recover_ledger(prefix, journal[-1]["sha256"])
        pending = recover_ledger(journal[:2])["pending_intents"]
        self.assertEqual(pending, [{"id": "2"*64, "side": "BUY", "signal_index": 20, "execute_index": 21}])

    def test_mutated_unrehashed_chain_and_wrong_sequence_rejected(self):
        for change in ("cash_after", "sequence", "previous_sha256", "sha256"):
            journal = self.pack()
            journal[2][change] = 50 if change in ("cash_after", "sequence") else "f"*64
            with self.subTest(change=change), self.assertRaises(ValueError):
                recover_ledger(journal)

    def test_rehashed_false_cash_position_fee_and_realized_assertions_rejected(self):
        for index, field, value in ((2, "cash_after", 999.), (2, "position_after", 4),
                                    (4, "realized_pnl", 14.), (4, "fee", -1.),
                                    (2, "equity_before", 2000.), (2, "quantity", True),
                                    (4, "quantity", 6), (2, "price", 0.)):
            journal = self.pack()
            journal[index][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                recover_ledger(rehash(journal))

    def test_rehashed_duplicate_ids_fills_or_hidden_account_reset_rejected(self):
        journal = self.pack()
        journal.append({**deepcopy(journal[1]), "bar_index": 24, "signal_index": 24, "execute_index": 25,
                        "timestamp": "2026-10-05T19:45:00+00:00"})
        with self.assertRaises(ValueError):
            recover_ledger(rehash(journal))
        journal = self.pack()
        journal.insert(3, deepcopy(journal[2]))
        with self.assertRaises(ValueError):
            recover_ledger(rehash(journal))
        journal = self.pack()
        journal.append({**deepcopy(journal[0]), "bar_index": 24, "timestamp": "2026-10-05T19:45:00+00:00"})
        with self.assertRaises(ValueError):
            recover_ledger(rehash(journal))

    def test_noncausal_or_unowned_fills_and_overwritten_intents_rejected(self):
        for change in ("same_bar", "wrong_execution", "wrong_owner", "overwritten"):
            journal = self.pack()
            if change == "same_bar":
                journal[1]["signal_index"] = journal[1]["bar_index"] = 21
            elif change == "wrong_execution":
                journal[1]["execute_index"] = 22
            elif change == "wrong_owner":
                journal[2]["intent_id"] = "9"*64
            else:
                extra = {**deepcopy(journal[1]), "id": "8"*64}
                journal.insert(2, extra)
            with self.subTest(change=change), self.assertRaises(ValueError):
                recover_ledger(rehash(journal))

    def test_halt_blocks_even_rehashed_future_entry(self):
        journal = self.pack()
        journal.insert(2, {"kind": "HALT", "bar_index": 21, "timestamp": journal[2]["timestamp"], "reason": "MANUAL_HALT"})
        with self.assertRaises(ValueError):
            recover_ledger(rehash(journal))
        # A halted, explicitly cancelled pending entry is a valid flat prefix.
        journal = journal[:3]
        journal.append({"kind": "CANCEL", "bar_index": 21, "timestamp": journal[2]["timestamp"],
                        "intent_id": "2"*64, "reason": "HALTED"})
        result = recover_ledger(rehash(journal))
        self.assertTrue(result["halted"])
        self.assertEqual(result["pending_intents"], [])
        self.assertEqual(result["ending_cash"], 1000.)

    def test_repeated_cancel_reject_or_consumed_intent_is_invalid(self):
        for kind in ("CANCEL", "REJECT"):
            journal = self.pack()[:2]
            event = {"kind": kind, "bar_index": 21, "timestamp": "2026-10-05T18:45:00+00:00",
                     "intent_id": "2"*64, "reason": "TEST_REJECTION"}
            journal.append(event)
            result = recover_ledger(rehash(journal))
            self.assertEqual(result["pending_intents"], [])
            journal.append(deepcopy(event))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                recover_ledger(rehash(journal))

    def test_malformed_types_nonfinite_and_time_reversal_fail_closed(self):
        for field, value in (("timestamp", "2026-10-05T13:30:00"), ("bar_index", True),
                             ("kind", "RESET"), ("synthetic", 1), ("starting_cash", False)):
            journal = self.pack()
            journal[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                recover_ledger(rehash(journal))
        for field, value in (("timestamp", "2026-10-05T13:00:00+00:00"), ("bar_index", 19)):
            journal = self.pack()
            journal[2][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                recover_ledger(rehash(journal))
        journal = self.pack()
        journal[2]["fee"] = float("nan")
        with self.assertRaises(ValueError):
            recover_ledger(journal)
        for invalid in (None, [], {}, [None]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                recover_ledger(invalid)

    def test_real_rehearsal_journal_reconciles_including_open_prefix_and_halt(self):
        frame, metadata = synthetic_fixture()
        cases = [(len(frame), None, scenario) for scenario in
                 ("baseline", "high_cost", "delay_1_bar", "high_cost_delay_1_bar")]
        cases += [(23, None, "baseline"), (80, 40, "baseline")]
        for visible, halt, scenario in cases:
            with self.subTest(visible=visible, halt=halt, scenario=scenario):
                summary, _, journal = run_rehearsal(frame, metadata, visible_count=visible, halt_at=halt, scenario=scenario)
                recovered = recover_ledger(journal, summary["journal_head_sha256"])
                for key in ("starting_cash", "ending_cash", "ending_position", "total_fees", "realized_pnl", "halted"):
                    self.assertEqual(recovered[key], summary[key])
                expected = [summary["pending_intent"]] if summary["pending_intent"] else []
                self.assertEqual(recovered["pending_intents"], expected)

    def test_full_exit_on_entry_bar_is_supported_without_inventing_intrabar_path(self):
        journal = self.pack()[:3]
        journal.append({"kind": "FILL", "bar_index": 21, "timestamp": "2026-10-05T19:00:00+00:00",
                        "side": "SELL", "quantity": 5, "price": 98., "fee": 1., "reason": "STOP_FIRST",
                        "intent_id": None, "cash_after": 988., "position_after": 0, "realized_pnl": -12.})
        result = recover_ledger(rehash(journal))
        self.assertEqual(result["ending_position"], 0)
        self.assertEqual(result["realized_pnl"], -12.)
