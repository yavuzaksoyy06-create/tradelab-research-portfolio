"""Broker-neutral drafts derived from verified, frozen-plan rehearsal reports."""

from datetime import datetime, timedelta, timezone
import hmac
import re

from research_workspace.bot_rehearsal import _sha, verify_report
from research_workspace.bot_strategy import STRATEGY_SYMBOLS, validate_strategy_plan
from research_workspace.equity_data import MAX_BARS
from research_workspace.stage7_events import SEALED_START


_FIXED_FIELDS = {
    "schema": "tradelab.order-intent-draft.v1",
    "scope": "OFFLINE_DRAFT_ONLY",
    "dispatch_allowed": False,
    "order_type": "MARKET",
    "time_in_force": "DAY",
}
_ID_FIELDS = ("plan_sha256", "source_sha256", "signal_index", "signal_at", "side", "symbol")
_DIGEST_FIELDS = ("plan_sha256", "source_sha256", "report_sha256", "client_order_id")
_FIELDS = set(_FIXED_FIELDS) | set(_ID_FIELDS) | set(_DIGEST_FIELDS) | {
    "quantity", "execution_index", "simulated_at", "synthetic",
}
_DIGEST = re.compile(r"[0-9a-f]{64}")


def _timestamp(value):
    if type(value) is not str or len(value) != 25:
        raise ValueError("BOT_DRAFT_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("BOT_DRAFT_TIMESTAMP") from None
    if (stamp.tzinfo != timezone.utc or stamp.isoformat() != value or
            stamp.minute % 15 or stamp.second or stamp.microsecond or
            stamp.date().isoformat() >= SEALED_START):
        raise ValueError("BOT_DRAFT_TIMESTAMP")
    return stamp


def validate_order_draft(draft):
    """Return detached draft fields after checking scope, identity and timing."""
    if type(draft) is not dict or set(draft) != {"content", "sha256"}:
        raise ValueError("BOT_DRAFT_SCHEMA")
    content = draft["content"]
    if type(content) is not dict or set(content) != _FIELDS:
        raise ValueError("BOT_DRAFT_SCHEMA")
    if any(type(content[k]) is not type(v) or content[k] != v for k, v in _FIXED_FIELDS.items()):
        raise ValueError("BOT_DRAFT_SCOPE")
    if (type(content["symbol"]) is not str or content["symbol"] not in STRATEGY_SYMBOLS or
            type(content["side"]) is not str or content["side"] not in ("BUY", "SELL") or
            type(content["synthetic"]) is not bool or type(content["quantity"]) is not int or
            not 1 <= content["quantity"] <= 1_000_000):
        raise ValueError("BOT_DRAFT_FIELDS")
    if any(type(content[k]) is not int or not 0 <= content[k] < MAX_BARS
           for k in ("signal_index", "execution_index")):
        raise ValueError("BOT_DRAFT_INDEX")
    gap = content["execution_index"] - content["signal_index"]
    observed, simulated = _timestamp(content["signal_at"]), _timestamp(content["simulated_at"])
    if gap not in (1, 2) or simulated - observed != timedelta(minutes=15 * (gap - 1)):
        raise ValueError("BOT_DRAFT_CAUSALITY")
    if any(type(value) is not str or not _DIGEST.fullmatch(value)
           for value in (draft["sha256"], *(content[k] for k in _DIGEST_FIELDS))):
        raise ValueError("BOT_DRAFT_DIGEST")
    identity = _sha({k: content[k] for k in _ID_FIELDS})
    if (not hmac.compare_digest(content["client_order_id"], identity) or
            not hmac.compare_digest(draft["sha256"], _sha(content))):
        raise ValueError("BOT_DRAFT_DIGEST")
    return dict(content)


def build_order_drafts(payload, plan):
    """Extract sized, simulated signal fills, including their report provenance.

    Stops, time/session exits and halt exits remain protective events in the
    rehearsal report. An unfilled or cancelled intent has no executable size.
    """
    planned = validate_strategy_plan(plan)
    report = verify_report(payload)
    summary = report["summary"]
    if summary.get("strategy_plan") != plan or summary["symbol"] != planned["symbol"]:
        raise ValueError("BOT_DRAFT_PLAN_MISMATCH")
    report_sha = _sha(report)
    intents = {event["id"]: event for event in report["journal"] if event["kind"] == "INTENT"}
    drafts = []
    for fill in report["journal"]:
        if fill["kind"] != "FILL" or fill["intent_id"] is None:
            continue
        intent = intents[fill["intent_id"]]
        signal, execution = intent["signal_index"], fill["bar_index"]
        expected_reason = "STRATEGY_ENTRY" if fill["side"] == "BUY" else "SIGNAL_EXIT"
        if (fill["reason"] != expected_reason or intent["timestamp"] != report["curve"][signal]["timestamp"] or
                _timestamp(fill["timestamp"]) != _timestamp(report["curve"][execution]["timestamp"]) - timedelta(minutes=15)):
            raise ValueError("BOT_DRAFT_REPORT_TIMING")
        content = {**_FIXED_FIELDS, "plan_sha256": plan["sha256"],
                   "source_sha256": summary["dataset_sha256"], "report_sha256": report_sha,
                   "symbol": summary["symbol"], "side": fill["side"], "quantity": fill["quantity"],
                   "signal_index": signal, "execution_index": execution, "signal_at": intent["timestamp"],
                   "simulated_at": fill["timestamp"], "synthetic": summary["synthetic"]}
        content["client_order_id"] = _sha({k: content[k] for k in _ID_FIELDS})
        draft = {"content": content, "sha256": _sha(content)}
        validate_order_draft(draft)
        drafts.append(draft)
    return drafts
