"""Exercise actual SQLite transactions with simulated draft provenance."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from threading import Barrier
import unittest

from research_workspace.bot_intent_outbox import IntentOutbox


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def make_draft(index, report="c", quantity=7):
    stamp = datetime(2026, 10, 1, 15, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    logical = {"plan_sha256": "a" * 64, "source_sha256": "b" * 64,
               "signal_index": index, "signal_at": stamp.isoformat(), "side": "BUY", "symbol": "SPY"}
    content = {**logical, "schema": "tradelab.order-intent-draft.v1", "scope": "OFFLINE_DRAFT_ONLY",
               "dispatch_allowed": False, "report_sha256": report * 64,
               "client_order_id": digest(logical), "quantity": quantity,
               "execution_index": index + 1, "simulated_at": stamp.isoformat(),
               "order_type": "MARKET", "time_in_force": "DAY", "synthetic": True}
    return {"content": content, "sha256": digest(content)}


class IntentOutboxTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name).resolve()
        self.path = self.folder / "intents.sqlite3"
        self.box = IntentOutbox(self.path)

    def test_no_implicit_creation_and_never_replaces_an_existing_store(self):
        self.assertFalse(self.path.exists())
        for action in (self.box.inspect, self.box.halt, lambda: self.box.enqueue([make_draft(0)])):
            with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_MISSING"):
                action()
            self.assertFalse(self.path.exists())
        self.box.create()
        self.box.enqueue([make_draft(0)])
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_ALREADY_EXISTS"):
            self.box.create()
        self.assertEqual(self.path.read_bytes(), before)

    def test_reopens_idempotently_and_retains_cancelled_identity(self):
        self.box.create()
        draft = make_draft(0)
        self.assertEqual(self.box.enqueue([draft, draft]), {"inserted": 1, "duplicates": 1})
        reopened = IntentOutbox(self.path)
        snapshot = reopened.inspect()
        self.assertEqual(snapshot["drafts"], [{"status": "STAGED", "draft": draft}])
        self.assertIs(snapshot["dispatch_allowed"], False)
        identity = draft["content"]["client_order_id"]
        self.assertTrue(reopened.cancel(identity))
        self.assertFalse(reopened.cancel(identity))
        self.assertEqual(self.box.enqueue([draft]), {"inserted": 0, "duplicates": 1})
        self.assertEqual(self.box.inspect()["drafts"], [{"status": "CANCELLED", "draft": draft}])
        self.assertEqual(self.box.inspect()["event_count"], 2)

    def test_conflicting_provenance_rolls_back_earlier_new_draft_in_batch(self):
        self.box.create()
        self.box.enqueue([make_draft(0)])
        before = self.box.inspect()
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_IDENTITY_CONFLICT"):
            self.box.enqueue([make_draft(1), make_draft(0, report="d")])
        self.assertEqual(self.box.inspect(), before)

    def test_invalid_draft_cannot_partially_stage_or_enable_dispatch(self):
        self.box.create()
        invalid = make_draft(1)
        invalid["content"]["dispatch_allowed"] = True
        invalid["sha256"] = digest(invalid["content"])
        with self.assertRaises(ValueError):
            self.box.enqueue([make_draft(0), invalid])
        self.assertEqual(self.box.inspect()["drafts"], [])

    def test_empty_verified_batch_leaves_no_event_in_an_active_store(self):
        self.box.create()
        before = self.box.inspect()
        self.assertEqual(self.box.enqueue([]), {"inserted": 0, "duplicates": 0})
        self.assertEqual(self.box.inspect(), before)
        self.box.halt()
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_HALTED"):
            self.box.enqueue([])

    def test_concurrent_retries_stage_one_durable_record(self):
        self.box.create()
        rendezvous = Barrier(2, timeout=5)

        def retry():
            reopened = IntentOutbox(self.path)
            rendezvous.wait()
            return reopened.enqueue([make_draft(0)])

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(retry) for _ in range(2)]
            results = [future.result(timeout=12) for future in futures]
        self.assertCountEqual(results, [{"inserted": 1, "duplicates": 0}, {"inserted": 0, "duplicates": 1}])
        self.assertEqual(self.box.inspect()["event_count"], 1)

    def test_halt_cancels_in_one_event_and_survives_reopen(self):
        self.box.create()
        first, second = make_draft(0), make_draft(1)
        self.box.enqueue([first, second])
        self.box.cancel(first["content"]["client_order_id"])
        self.assertEqual(self.box.halt(), {"cancelled": 1, "halted": True})
        reopened = IntentOutbox(self.path)
        snapshot = reopened.inspect()
        self.assertTrue(snapshot["halted"])
        self.assertEqual(snapshot["event_count"], 4)
        self.assertEqual([row["status"] for row in snapshot["drafts"]], ["CANCELLED", "CANCELLED"])
        self.assertEqual(reopened.halt(), {"cancelled": 0, "halted": True})
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_HALTED"):
            reopened.enqueue([make_draft(2)])
        self.assertEqual(reopened.inspect(), snapshot)

    def test_tampered_chain_blocks_all_operations(self):
        self.box.create()
        self.box.enqueue([make_draft(0)])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE intent_events SET payload = '{}' WHERE sequence = 1")
        for action in (self.box.inspect, self.box.halt, lambda: self.box.enqueue([make_draft(1)])):
            with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_INTEGRITY_REJECTED"):
                action()

    def test_rehashed_illegal_transition_is_still_rejected(self):
        self.box.create()
        self.box.enqueue([make_draft(0)])
        self.box.halt()
        head = self.box.inspect()["head_sha256"]
        forged = {"sequence": 3, "previous_sha256": head, "kind": "STAGED", "draft": make_draft(1)}
        forged_head = digest(forged)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("INSERT INTO intent_events VALUES (3, ?, ?)", (canonical(forged), forged_head))
            conn.execute("UPDATE checkpoint SET event_count=3, head_sha256=?", (forged_head,))
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_INTEGRITY_REJECTED"):
            self.box.inspect()

    def test_external_expected_head_detects_restored_valid_prefix(self):
        self.box.create()
        draft = make_draft(0)
        self.box.enqueue([draft])
        earlier = self.path.read_bytes()
        self.box.halt()
        expected = self.box.inspect()["head_sha256"]
        self.path.write_bytes(earlier)
        before = self.box.inspect()
        self.assertFalse(before["halted"])
        operations = (lambda: self.box.inspect(expected_head=expected),
                      lambda: self.box.recover(expected_head=expected),
                      lambda: self.box.enqueue([make_draft(1)], expected_head=expected),
                      lambda: self.box.cancel(draft["content"]["client_order_id"], expected_head=expected),
                      lambda: self.box.halt(expected_head=expected))
        for action in operations:
            with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_EXPECTED_HEAD_MISMATCH"):
                action()
        self.assertEqual(self.box.inspect(), before)

    def test_concurrent_writers_with_the_same_expected_head_compare_under_lock(self):
        self.box.create()
        expected = self.box.inspect()["head_sha256"]
        rendezvous = Barrier(2, timeout=5)

        def stage(index):
            store = IntentOutbox(self.path)
            rendezvous.wait()
            try:
                return store.enqueue([make_draft(index)], expected_head=expected)
            except ValueError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(stage, index) for index in (0, 1)]
            results = [future.result(timeout=12) for future in futures]
        self.assertCountEqual(results, [{"inserted": 1, "duplicates": 0}, "BOT_OUTBOX_EXPECTED_HEAD_MISMATCH"])
        self.assertEqual(self.box.inspect()["event_count"], 1)

    def test_recover_rolls_back_a_process_crash_after_sqlite_pages_spill(self):
        self.box.create()
        self.box.enqueue([make_draft(0)])
        before = self.box.inspect()
        committed_bytes = self.path.read_bytes()
        abrupt_writer = """\
import os, sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
conn.execute('PRAGMA cache_size=1')
conn.execute('PRAGMA cache_spill=ON')
conn.execute('BEGIN IMMEDIATE')
conn.execute('UPDATE checkpoint SET event_count=0')
for sequence in range(2, 80):
    conn.execute('INSERT INTO intent_events VALUES (?, ?, ?)', (sequence, 'x' * 4000, '0' * 64))
os._exit(0)
"""
        subprocess.run([sys.executable, "-B", "-c", abrupt_writer, str(self.path)],
                       check=True, timeout=20, capture_output=True)
        journal = self.path.with_name(self.path.name + "-journal")
        self.assertTrue(journal.is_file())
        uncommitted_bytes = self.path.read_bytes()
        self.assertNotEqual(uncommitted_bytes, committed_bytes)
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_DATABASE_REJECTED"):
            self.box.inspect()
        self.assertEqual(self.path.read_bytes(), uncommitted_bytes)
        reopened = IntentOutbox(self.path)
        self.assertEqual(reopened.recover(expected_head=before["head_sha256"]), before)
        self.assertFalse(journal.exists())
        self.assertEqual(reopened.inspect(), before)

    def test_private_path_gate_rejects_relative_unc_and_git_directories(self):
        repo = self.folder / "repo"
        repo.mkdir()
        (repo / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        for target in ("relative.sqlite3", r"\\example.invalid\share\orders.sqlite3", repo / "orders.sqlite3"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                IntentOutbox(target)

    def test_refuses_linked_database_and_unrelated_sqlite_schema(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE unrelated(value TEXT)")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_SCHEMA_REJECTED"):
            self.box.enqueue([make_draft(0)])
        self.assertEqual(self.path.read_bytes(), before)
        linked = self.folder / "linked.sqlite3"
        try:
            linked.hardlink_to(self.path)
        except OSError:
            self.skipTest("Hard links unavailable in the test directory")
        with self.assertRaisesRegex(ValueError, "BOT_OUTBOX_LOCAL_PATH_REQUIRED"):
            IntentOutbox(linked)


if __name__ == "__main__":
    unittest.main()
