"""Durable local storage for verified offline order drafts.

The event log reconstructs status and checks the saved head on every open.
An externally retained head also detects a rewritten or restored older copy.
"""
from contextlib import closing, contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile

from research_workspace.bot_order_draft import validate_order_draft
from research_workspace.equity_data import MAX_BARS


_APPLICATION_ID = 0x544C4F31
_VERSION = 1
_ZERO = "0" * 64
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_BATCH = MAX_BARS
_MAX_EVENTS = 10_000
_MAX_EVENT_BYTES = 4_096
_CHECKPOINT_SCHEMA = (
    "CREATE TABLE checkpoint (id INTEGER PRIMARY KEY CHECK (id = 1), "
    "event_count INTEGER NOT NULL, head_sha256 TEXT NOT NULL)"
)
_EVENT_SCHEMA = (
    "CREATE TABLE intent_events (sequence INTEGER PRIMARY KEY, "
    "payload TEXT NOT NULL, sha256 TEXT NOT NULL)"
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _valid_digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _lstat(path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _checked_path(value):
    """Check ancestors before descending and keep the database outside Git."""
    path = Path(value)
    if (not path.is_absolute() or str(path).startswith(("\\\\", "//")) or
            path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"} or
            any(part.casefold() in {"..", ".git"} for part in path.parts[1:])):
        raise ValueError("BOT_OUTBOX_LOCAL_PATH_REQUIRED")
    if os.name == "nt":
        import ctypes
        if (ctypes.windll.kernel32.GetDriveTypeW(path.anchor) not in (2, 3, 6) or
                path.is_reserved() or
                any(":" in part or part.endswith((".", " ")) for part in path.parts[1:])):
            raise ValueError("BOT_OUTBOX_LOCAL_PATH_REQUIRED")
    for parent in reversed(path.parents):
        info = _lstat(parent)
        if info is None or _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("BOT_OUTBOX_LOCAL_PATH_REQUIRED")
        if _lstat(parent / ".git") is not None:
            raise ValueError("BOT_OUTBOX_PRIVATE_PATH_REQUIRED")
    for suffix in ("", "-journal", "-wal", "-shm"):
        info = _lstat(path.with_name(path.name + suffix))
        if info is not None and (_linked(info) or not stat.S_ISREG(info.st_mode) or
                                 info.st_nlink != 1 or suffix in ("-wal", "-shm")):
            raise ValueError("BOT_OUTBOX_LOCAL_PATH_REQUIRED")
    return path


def _connect(path, *, write):
    mode = "rw" if write else "ro"
    conn = sqlite3.connect(f"{path.as_uri()}?mode={mode}", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA trusted_schema=OFF")
        if write:
            conn.execute("PRAGMA synchronous=FULL")
        else:
            conn.execute("PRAGMA query_only=ON")
        return conn
    except BaseException:
        conn.close()
        raise


def _checked_draft(draft):
    content = validate_order_draft(draft)
    identity = content["client_order_id"]
    if (not _valid_digest(identity) or content.get("dispatch_allowed") is not False or
            content.get("scope") != "OFFLINE_DRAFT_ONLY"):
        raise ValueError("BOT_OUTBOX_DRAFT_REJECTED")
    return identity, {"content": content, "sha256": _sha(_canonical(content))}


def _load_state(conn):
    app_id = conn.execute("PRAGMA application_id").fetchone()[0]
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    schema = conn.execute("SELECT type, name, sql FROM sqlite_schema LIMIT 3").fetchall()
    if (app_id != _APPLICATION_ID or version != _VERSION or
            conn.execute("PRAGMA journal_mode").fetchone()[0] != "delete" or
            len(schema) != 2 or set(schema) != {
                ("table", "checkpoint", _CHECKPOINT_SCHEMA),
                ("table", "intent_events", _EVENT_SCHEMA),
            }):
        raise ValueError("BOT_OUTBOX_SCHEMA_REJECTED")
    rows = conn.execute("SELECT id, event_count, head_sha256 FROM checkpoint LIMIT 2").fetchall()
    if len(rows) != 1:
        raise ValueError("BOT_OUTBOX_INTEGRITY_REJECTED")
    singleton, count, expected_head = rows[0]
    if (singleton != 1 or type(count) is not int or not 0 <= count <= _MAX_EVENTS or
            not _valid_digest(expected_head)):
        raise ValueError("BOT_OUTBOX_INTEGRITY_REJECTED")

    drafts = {}
    previous = _ZERO
    halted = False
    seen = 0
    records = conn.execute(
        "SELECT sequence, CASE WHEN length(CAST(payload AS BLOB)) <= ? THEN payload END, "
        "CASE WHEN length(CAST(sha256 AS BLOB)) = 64 THEN sha256 END "
        "FROM intent_events ORDER BY sequence LIMIT ?", (_MAX_EVENT_BYTES, _MAX_EVENTS + 1),
    )
    for sequence, raw, digest in records:
        seen += 1
        if (seen > count or sequence != seen or type(raw) is not str or
                not _valid_digest(digest) or not hmac.compare_digest(digest, _sha(raw))):
            raise ValueError("BOT_OUTBOX_INTEGRITY_REJECTED")
        try:
            event = json.loads(raw)
            if (type(event) is not dict or _canonical(event) != raw or
                    event.get("previous_sha256") != previous or
                    type(event.get("sequence")) is not int or event["sequence"] != sequence or halted):
                raise ValueError("Outbox chain or transition")
            kind = event.get("kind")
            base = {"sequence", "kind", "previous_sha256"}
            if kind == "STAGED" and set(event) == base | {"draft"}:
                identity, draft = _checked_draft(event["draft"])
                if identity in drafts:
                    raise ValueError("Duplicate staged identity")
                drafts[identity] = {"status": "STAGED", "draft": draft}
            elif kind == "CANCELLED" and set(event) == base | {"client_order_id"}:
                identity = event["client_order_id"]
                if identity not in drafts or drafts[identity]["status"] != "STAGED":
                    raise ValueError("Invalid cancellation")
                drafts[identity]["status"] = "CANCELLED"
            elif kind == "HALTED" and set(event) == base:
                halted = True
                for row in drafts.values():
                    row["status"] = "CANCELLED"
            else:
                raise ValueError("Unknown outbox event")
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise ValueError("BOT_OUTBOX_INTEGRITY_REJECTED") from exc
        previous = digest
    if seen != count or not hmac.compare_digest(previous, expected_head):
        raise ValueError("BOT_OUTBOX_INTEGRITY_REJECTED")
    return {"halted": halted, "drafts": drafts, "event_count": seen, "head_sha256": previous}


def _append(conn, state, kind, **fields):
    sequence = state["event_count"] + 1
    if sequence > _MAX_EVENTS:
        raise ValueError("BOT_OUTBOX_CAPACITY_REACHED")
    event = {"kind": kind, "sequence": sequence, "previous_sha256": state["head_sha256"], **fields}
    raw = _canonical(event)
    if len(raw.encode("utf-8")) > _MAX_EVENT_BYTES:
        raise ValueError("BOT_OUTBOX_EVENT_TOO_LARGE")
    digest = _sha(raw)
    conn.execute("INSERT INTO intent_events VALUES (?, ?, ?)", (sequence, raw, digest))
    conn.execute("UPDATE checkpoint SET event_count = ?, head_sha256 = ? WHERE id = 1", (sequence, digest))
    state["event_count"], state["head_sha256"] = sequence, digest


class IntentOutbox:
    """One local database with immutable drafts and a durable halt latch."""

    def __init__(self, path):
        self._path = _checked_path(path)

    def create(self):
        """Publish a new initialized store exclusively after SQLite commits."""
        path = _checked_path(self._path)
        if _lstat(path) is not None:
            raise ValueError("BOT_OUTBOX_ALREADY_EXISTS")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".intent-outbox-", suffix=".tmp", dir=path.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with closing(_connect(temporary, write=True)) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                conn.execute(f"PRAGMA user_version={_VERSION}")
                conn.execute(_CHECKPOINT_SCHEMA)
                conn.execute(_EVENT_SCHEMA)
                conn.execute("INSERT INTO checkpoint VALUES (1, 0, ?)", (_ZERO,))
            _checked_path(path)
            if os.name == "nt":
                os.rename(temporary, path)  # Windows rename never replaces an existing file.
            else:
                os.link(temporary, path)  # Exclusive atomic publication on the same filesystem.
        except FileExistsError:
            raise ValueError("BOT_OUTBOX_ALREADY_EXISTS") from None
        except sqlite3.Error:
            raise ValueError("BOT_OUTBOX_CREATE_REJECTED") from None
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def _transaction(self, *, write, expected_head=None):
        path = _checked_path(self._path)
        if _lstat(path) is None:
            raise ValueError("BOT_OUTBOX_MISSING")
        try:
            with closing(_connect(path, write=write)) as conn, conn:
                conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                state = _load_state(conn)
                if expected_head is not None:
                    if not _valid_digest(expected_head):
                        raise ValueError("BOT_OUTBOX_EXPECTED_HEAD_INVALID")
                    if not hmac.compare_digest(expected_head, state["head_sha256"]):
                        raise ValueError("BOT_OUTBOX_EXPECTED_HEAD_MISMATCH")
                yield conn, state
        except sqlite3.Error:
            raise ValueError("BOT_OUTBOX_DATABASE_REJECTED") from None

    def enqueue(self, drafts, *, expected_head=None):
        """Insert a batch atomically. Identical retries never duplicate an intent."""
        if type(drafts) not in (list, tuple) or len(drafts) > _MAX_BATCH:
            raise ValueError("BOT_OUTBOX_BATCH_REJECTED")
        verified = [_checked_draft(draft) for draft in drafts]
        with self._transaction(write=True, expected_head=expected_head) as (conn, state):
            if state["halted"]:
                raise ValueError("BOT_OUTBOX_HALTED")
            inserted = duplicates = 0
            for identity, draft in verified:
                existing = state["drafts"].get(identity)
                if existing is not None:
                    if _canonical(existing["draft"]) != _canonical(draft):
                        raise ValueError("BOT_OUTBOX_IDENTITY_CONFLICT")
                    duplicates += 1
                    continue
                # Preserve capacity for the halt event even when the store is full.
                if state["event_count"] >= _MAX_EVENTS - 1:
                    raise ValueError("BOT_OUTBOX_CAPACITY_REACHED")
                _append(conn, state, "STAGED", draft=draft)
                state["drafts"][identity] = {"status": "STAGED", "draft": draft}
                inserted += 1
        return {"inserted": inserted, "duplicates": duplicates}

    def _snapshot(self, *, write, expected_head):
        with self._transaction(write=write, expected_head=expected_head) as (_, state):
            return {**state, "drafts": list(state["drafts"].values()), "dispatch_allowed": False}

    def inspect(self, expected_head=None):
        """Read and verify a snapshot against the optional retained head."""
        return self._snapshot(write=False, expected_head=expected_head)

    def recover(self, expected_head=None):
        """Permit SQLite to roll back an interrupted write, then verify the resulting store."""
        return self._snapshot(write=True, expected_head=expected_head)

    def cancel(self, client_order_id, *, expected_head=None):
        if not _valid_digest(client_order_id):
            raise ValueError("BOT_OUTBOX_IDENTITY_INVALID")
        with self._transaction(write=True, expected_head=expected_head) as (conn, state):
            row = state["drafts"].get(client_order_id)
            if row is None:
                raise ValueError("BOT_OUTBOX_IDENTITY_UNKNOWN")
            if row["status"] == "CANCELLED":
                return False
            if state["event_count"] >= _MAX_EVENTS - 1:
                raise ValueError("BOT_OUTBOX_CAPACITY_REACHED")
            _append(conn, state, "CANCELLED", client_order_id=client_order_id)
        return True

    def halt(self, *, expected_head=None):
        """Latch and cancel all staged drafts in a single durable transition."""
        with self._transaction(write=True, expected_head=expected_head) as (conn, state):
            if state["halted"]:
                return {"cancelled": 0, "halted": True}
            cancelled = sum(row["status"] == "STAGED" for row in state["drafts"].values())
            _append(conn, state, "HALTED")
        return {"cancelled": cancelled, "halted": True}
