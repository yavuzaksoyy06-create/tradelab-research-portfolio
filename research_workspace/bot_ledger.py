"""Reconstruct an offline account from its event journal, without broker access.

The hash chain detects accidental changes; semantic accounting checks also reject
inconsistent journals whose hashes were recomputed. This is prefix verification,
not authentication, durable broker recovery or permission to submit an order.
"""
from datetime import datetime
import hashlib
import hmac
import json
import math
import re

_ZERO = "0" * 64
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = {"START", "INTENT", "FILL", "HALT", "CANCEL", "REJECT"}
_SELL_REASONS = {"SIGNAL_EXIT", "MANUAL_HALT", "LOSS_HALT", "STOP_GAP", "TARGET_GAP",
                 "STOP_FIRST", "STOP", "TARGET", "SESSION_END", "TIME_EXIT"}
_TOLERANCE = 1e-7
MAX_JOURNAL_EVENTS = 50_000


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _number(value, *, positive=False, nonnegative=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Numeric field")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ValueError("Numeric range")
    return float(value)


def _integer(value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Integer field")
    return value


def _hash(value):
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("Hash field")
    return value


def _same(actual, expected):
    if abs(_number(actual) - expected) > _TOLERANCE:
        raise ValueError("Account mismatch")


def recover_ledger(journal, expected_head=None):
    """Return independently reconstructed cash/position and unresolved intents.

    `expected_head` binds a previously recorded terminal digest and detects a
    correctly hashed truncation. Without it, only the supplied prefix is known.
    Values in `cash_after`, `position_after` and `realized_pnl` are assertions to
    check, never the source of the reconstructed balances.
    """
    try:
        if not isinstance(journal, list) or not 1 <= len(journal) <= MAX_JOURNAL_EVENTS:
            raise ValueError("Journal size")
        if expected_head is not None:
            _hash(expected_head)
        previous, last_stamp, last_bar = _ZERO, None, -1
        cash, quantity, entry_cost, total_fees, realized = 0., 0, 0., 0., 0.
        initial, policy_hash, symbol, synthetic = None, None, None, None
        pending, seen_ids, consumed = {}, set(), set()
        halted, buy_fills, sell_fills = False, 0, 0
        for sequence, record in enumerate(journal):
            if not isinstance(record, dict):
                raise ValueError("Record type")
            fields = {key: value for key, value in record.items() if key != "sha256"}
            digest = _hash(record["sha256"])
            if (_integer(record["sequence"]) != sequence or record["previous_sha256"] != previous or
                    not hmac.compare_digest(digest, _digest(fields))):
                raise ValueError("Chain")
            previous = digest
            kind = record["kind"]
            if kind not in _KINDS:
                raise ValueError("Event kind")
            bar = _integer(record["bar_index"])
            if not isinstance(record["timestamp"], str):
                raise ValueError("Timestamp field")
            stamp = datetime.fromisoformat(record["timestamp"])
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("Naive timestamp")
            if bar < last_bar or last_stamp is not None and stamp < last_stamp:
                raise ValueError("Nonmonotonic journal")
            last_stamp, last_bar = stamp, bar
            if sequence == 0:
                if kind != "START" or bar != 0:
                    raise ValueError("Missing initial state")
                initial = cash = _number(record["starting_cash"], positive=True)
                policy_hash = _hash(record["policy_sha256"])
                symbol = record["symbol"]
                synthetic = record["synthetic"]
                if not isinstance(symbol, str) or not symbol or type(synthetic) is not bool:
                    raise ValueError("Initial source identity")
                continue
            if kind == "START":
                raise ValueError("Account reset")
            if kind == "INTENT":
                identity = _hash(record["id"])
                side = record["side"]
                signal = _integer(record["signal_index"])
                execution = _integer(record["execute_index"])
                if (identity in seen_ids or pending or signal != bar or execution <= signal or
                        side not in ("BUY", "SELL") or
                        side == "BUY" and (halted or quantity != 0) or side == "SELL" and quantity == 0):
                    raise ValueError("Intent state")
                seen_ids.add(identity)
                pending[identity] = {"id": identity, "side": side, "signal_index": signal,
                                     "execute_index": execution}
            elif kind in ("CANCEL", "REJECT"):
                identity = _hash(record["intent_id"])
                if identity not in pending or identity in consumed:
                    raise ValueError("Unowned intent transition")
                if not isinstance(record["reason"], str) or not record["reason"]:
                    raise ValueError("Missing transition reason")
                consumed.add(identity)
                pending.pop(identity)
            elif kind == "HALT":
                if halted or not isinstance(record["reason"], str) or not record["reason"]:
                    raise ValueError("Halt state")
                if "equity" in record:
                    _number(record["equity"], nonnegative=True)
                halted = True
            elif kind == "FILL":
                side = record["side"]
                count = _integer(record["quantity"], minimum=1)
                price = _number(record["price"], positive=True)
                commission = _number(record["fee"], nonnegative=True)
                notional = count * price
                if not math.isfinite(notional) or commission >= notional:
                    raise ValueError("Invalid fill notional")
                identity = record["intent_id"]
                if identity is not None:
                    _hash(identity)
                    intent = pending.get(identity)
                    if (intent is None or identity in consumed or intent["side"] != side or
                            intent["signal_index"] >= bar or intent["execute_index"] != bar):
                        raise ValueError("Noncausal or repeated fill")
                    consumed.add(identity)
                    pending.pop(identity)
                if side == "BUY":
                    if halted or quantity != 0 or identity is None:
                        raise ValueError("Entry state")
                    stop = _number(record["stop"], positive=True)
                    target = _number(record["target"], positive=True)
                    _number(record["planned_risk"], positive=True)
                    _same(record["equity_before"], cash)
                    if not stop < price < target:
                        raise ValueError("Entry geometry")
                    quantity, entry_cost = count, notional + commission
                    cash -= entry_cost
                    buy_fills += 1
                elif side == "SELL":
                    if quantity != count or record["reason"] not in _SELL_REASONS or pending:
                        raise ValueError("Exit state")
                    if record["reason"] == "SIGNAL_EXIT" and identity is None:
                        raise ValueError("Unowned signal exit")
                    pnl = notional - commission - entry_cost
                    _same(record["realized_pnl"], pnl)
                    cash += notional - commission
                    realized += pnl
                    quantity, entry_cost = 0, 0.
                    sell_fills += 1
                else:
                    raise ValueError("Fill side")
                total_fees += commission
                if not all(math.isfinite(value) for value in (cash, entry_cost, total_fees, realized)) or cash < -_TOLERANCE:
                    raise ValueError("Account invariant")
                _same(record["cash_after"], cash)
                if _integer(record["position_after"]) != quantity:
                    raise ValueError("Position assertion")
        if expected_head is not None and not hmac.compare_digest(previous, expected_head):
            raise ValueError("Unexpected terminal head")
        return {"schema": "tradelab.offline-ledger-recovery.v1", "verified": True,
                "verification_scope": "EXPECTED_HEAD" if expected_head is not None else "SUPPLIED_PREFIX_ONLY",
                "complete_prefix_only": expected_head is None, "journal_head_sha256": previous,
                "journal_events": len(journal), "policy_sha256": policy_hash, "symbol": symbol,
                "synthetic": synthetic, "starting_cash": initial, "ending_cash": cash,
                "ending_position": quantity, "entry_cost": entry_cost, "total_fees": total_fees,
                "realized_pnl": realized, "halted": halted, "pending_intents": list(pending.values()),
                "buy_fills": buy_fills, "sell_fills": sell_fills,
                "last_event_bar_index": last_bar, "last_event_timestamp": last_stamp.isoformat(),
                "broker_recovery_supported": False, "orders_enabled": False}
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError, RecursionError):
        raise ValueError("BOT_LEDGER_REJECTED") from None
