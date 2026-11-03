"""Deterministic, in-memory execution rehearsal. No broker or network adapter.

The fixed EMA rule exercises plumbing, not a validated strategy. Only existing
completed US OHLCV history is accepted; ISE return observations are not prices.
"""
from dataclasses import asdict, dataclass, replace
import hashlib
import hmac
import json
import math

import pandas as pd

from research_workspace.stage7_events import validated_history, replay_limit, fingerprint


@dataclass(frozen=True)
class RehearsalPolicy:
    version: str = "tradelab.offline-rehearsal.v1"
    starting_cash: float = 100_000.0
    maximum_position_fraction: float = .10
    planned_risk_fraction: float = .005
    stop_fraction: float = .02
    target_fraction: float = .04
    fee_bps: float = 3.0
    slippage_bps: float = 5.0
    session_loss_fraction: float = .02
    maximum_holding_bars: int = 4
    fast_ema: int = 9
    slow_ema: int = 21


_POLICY = RehearsalPolicy()
_ZERO = "0" * 64
MAX_REPORT_BYTES = 10_000_000
SCENARIOS = ("baseline", "high_cost", "delay_1_bar", "high_cost_delay_1_bar")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _scenario_policy(scenario):
    if type(scenario) is not str or scenario not in SCENARIOS:
        raise ValueError("BOT_SCENARIO_UNREGISTERED")
    high_cost = scenario in ("high_cost", "high_cost_delay_1_bar")
    delay = 1 if scenario in ("delay_1_bar", "high_cost_delay_1_bar") else 0
    policy = replace(_POLICY, fee_bps=10., slippage_bps=15.) if high_cost else _POLICY
    return policy, delay, {**asdict(policy), "additional_delay_bars": delay}


def readiness_report():
    """Informational blockers; no setting, clock or report can enable orders."""
    return {"mode": "OFFLINE_REHEARSAL_ONLY", "broker_adapter_present": False,
            "real_orders_enabled": False, "paper_orders_enabled": False,
            "model_promoted": False, "reserved_ise_rows": 108,
            "prospective_gate": "2027-01-21 21:15:00+00:00",
            "future_evaluation_enabled": False,
            "blockers": ["V2_PRIMARY_EDGE_NOT_ESTABLISHED",
                         "V2_VALIDATION_REUSED_NOT_INDEPENDENT",
                         "ISE_INDEX_RETURNS_NOT_EXECUTABLE_OHLCV",
                         "NO_VALIDATED_EXECUTION_STRATEGY",
                         "NO_BROKER_ADAPTER_OR_ORDER_PERMISSION"]}


def run_rehearsal(frame, metadata, *, visible_count=None, halt_at=None, scenario="baseline"):
    """Replay fixed long/flat EMA plumbing with next-bar fills and one position.

    Full-snapshot validation and holdout allocation precede prefix slicing.
    No model fitting, downloads, persistence or external orders occur here.
    """
    p, delay, policy = _scenario_policy(scenario)
    clean = validated_history(frame, metadata)
    boundary = replay_limit(clean)
    if visible_count is None:
        visible_count = boundary
    if type(visible_count) is not int or not 1 <= visible_count <= boundary:
        raise ValueError("BOT_VISIBLE_PREFIX_RESERVED_OR_INVALID")
    if halt_at is not None and (type(halt_at) is not int or not 0 <= halt_at < visible_count):
        raise ValueError("BOT_HALT_INDEX_INVALID")
    bars = clean.iloc[:visible_count].copy()
    policy_hash = _sha(policy)
    fee, slip = p.fee_bps / 10_000, p.slippage_bps / 10_000
    fast = bars.close.ewm(span=p.fast_ema, adjust=False, min_periods=p.fast_ema).mean()
    slow = bars.close.ewm(span=p.slow_ema, adjust=False, min_periods=p.slow_ema).mean()
    cash, quantity, entry_cost, stop, target, held = p.starting_cash, 0, 0., 0., 0., 0
    pending, halted, session, day_equity = None, False, None, p.starting_cash
    journal, curve, used_ids = [], [], set()
    total_fees, realized = 0., 0.

    def event(kind, i, stamp, **values):
        record = {"sequence": len(journal), "kind": kind, "bar_index": int(i),
                  "timestamp": stamp.isoformat(), "previous_sha256": journal[-1]["sha256"] if journal else _ZERO,
                  **values}
        record["sha256"] = _sha(record)
        journal.append(record)

    def fill_exit(i, row, raw_price, reason, intent_id=None):
        nonlocal cash, quantity, entry_cost, total_fees, realized, pending
        stamp = row.timestamp if reason in ("SIGNAL_EXIT", "MANUAL_HALT", "LOSS_HALT", "STOP_GAP", "TARGET_GAP") else row.bar_end
        if pending:
            event("CANCEL", i, stamp, intent_id=pending["id"], reason="POSITION_CLOSED")
            pending = None
        price = float(raw_price) * (1 - slip)
        commission = quantity * price * fee
        proceeds = quantity * price - commission
        pnl = proceeds - entry_cost
        cash += proceeds
        total_fees += commission
        realized += pnl
        event("FILL", i, stamp,
              side="SELL", quantity=quantity, price=price, fee=commission, reason=reason,
              intent_id=intent_id, cash_after=cash, position_after=0, realized_pnl=pnl)
        quantity, entry_cost = 0, 0.

    event("START", 0, bars.timestamp.iloc[0], starting_cash=cash,
          symbol=metadata["symbol"], synthetic=metadata["synthetic"], policy_sha256=policy_hash)
    for i, row in enumerate(bars.itertuples(index=False)):
        final_session_bar = row.bar_end == row.session_close
        if session != row.session:
            if quantity:
                raise ValueError("BOT_UNEXPECTED_OVERNIGHT_POSITION")
            session, day_equity = row.session, cash
        if halt_at == i and not halted:
            halted = True
            event("HALT", i, row.timestamp, reason="MANUAL_HALT")
        if halted and pending:
            event("CANCEL", i, row.timestamp, intent_id=pending["id"], reason="HALTED")
            pending = None
        exited = False
        if halted and quantity:
            fill_exit(i, row, row.open, "MANUAL_HALT" if halt_at == i else "LOSS_HALT")
            pending, exited = None, True
        if pending and pending["execute_index"] <= i:
            intent = pending
            pending = None
            if intent["id"] in used_ids or intent["signal_index"] >= i or intent["execute_index"] != i:
                raise ValueError("BOT_DUPLICATE_OR_NONCAUSAL_INTENT")
            used_ids.add(intent["id"])
            if intent["side"] == "SELL" and quantity:
                fill_exit(i, row, row.open, "SIGNAL_EXIT", intent["id"])
                exited = True
            elif intent["side"] == "BUY" and not quantity and not halted:
                price = float(row.open) * (1 + slip)
                equity = cash
                # Recheck at the actual opening price, including adverse costs.
                unit_loss = price - price * (1 - p.stop_fraction) * (1 - slip) + price * fee * 2
                quantity = min(math.floor(equity * p.maximum_position_fraction / (price * (1 + fee))),
                               math.floor(equity * p.planned_risk_fraction / unit_loss),
                               math.floor(cash / (price * (1 + fee)))) if not final_session_bar else 0
                if quantity > 0:
                    commission = quantity * price * fee
                    entry_cost = quantity * price + commission
                    cash -= entry_cost
                    total_fees += commission
                    stop, target, held = price * (1 - p.stop_fraction), price * (1 + p.target_fraction), 0
                    event("FILL", i, row.timestamp, side="BUY", quantity=quantity, price=price,
                          fee=commission, reason="EMA_PLUMBING_ONLY", intent_id=intent["id"],
                          cash_after=cash, position_after=quantity, stop=stop, target=target,
                          planned_risk=quantity * unit_loss, equity_before=equity)
                else:
                    event("REJECT", i, row.timestamp, intent_id=intent["id"], reason="SIZE_OR_SESSION_LIMIT")
        if quantity:
            held += 1
            # Gaps precede intrabar tests; both stop/target touched means stop first.
            if row.open <= stop:
                fill_exit(i, row, row.open, "STOP_GAP")
            elif row.open >= target:
                fill_exit(i, row, target, "TARGET_GAP")
            elif row.low <= stop:
                fill_exit(i, row, stop, "STOP_FIRST" if row.high >= target else "STOP")
            elif row.high >= target:
                fill_exit(i, row, target, "TARGET")
            elif final_session_bar or held >= p.maximum_holding_bars:
                fill_exit(i, row, row.close, "SESSION_END" if final_session_bar else "TIME_EXIT")
            if not quantity:
                exited = True
        equity = cash + quantity * float(row.close)
        if not all(math.isfinite(v) for v in (cash, equity, total_fees, realized)) or cash < -1e-8 or quantity < 0:
            raise ValueError("BOT_ACCOUNTING_INVARIANT")
        if not halted and equity <= day_equity * (1 - p.session_loss_fraction):
            halted = True
            event("HALT", i, row.bar_end, reason="SESSION_LOSS_LIMIT", equity=equity)
        if pending and (final_session_bar or halted):
            event("CANCEL", i, row.bar_end, intent_id=pending["id"],
                  reason="HALTED" if halted else "SESSION_END")
            pending = None
        curve.append({"timestamp": row.bar_end, "close": float(row.close), "cash": cash,
                      "position": quantity, "equity": equity, "halted": halted})
        # Signals see only the completed close. No entry on the last session bar,
        # and no replacement entry on an exit bar. The final visible close may
        # create an unfilled intent; it never requires or reads a future bar.
        if not pending and not final_session_bar and not halted and not exited and pd.notna(slow.iloc[i]):
            side = "BUY" if fast.iloc[i] > slow.iloc[i] and quantity == 0 else (
                "SELL" if fast.iloc[i] <= slow.iloc[i] and quantity > 0 else None)
            if side:
                intent = {"side": side, "signal_index": i, "execute_index": i + 1 + delay}
                intent["id"] = _sha({"symbol": metadata["symbol"], "observed_at": row.bar_end.isoformat(),
                                     "side": side, "policy_sha256": policy_hash})
                pending = intent
                event("INTENT", i, row.bar_end, **intent)
    curve = pd.DataFrame(curve)
    summary = {"schema": p.version, "mode": "OFFLINE_REHEARSAL_ONLY", "symbol": metadata["symbol"],
               "synthetic": metadata["synthetic"], "source_independently_verified": False,
               "scenario": scenario, "execution_assumptions": {"fee_bps": p.fee_bps,
                   "slippage_bps": p.slippage_bps, "additional_delay_bars": delay},
               "dataset_sha256": fingerprint(clean), "visible_prefix_sha256": fingerprint(bars),
               "snapshot_bars": len(clean), "replay_limit": boundary, "visible_bars": len(bars),
               "reserved_snapshot_bars": len(clean) - boundary, "policy": policy, "policy_sha256": policy_hash,
               "starting_cash": p.starting_cash, "ending_cash": cash, "ending_position": quantity,
               "ending_equity": float(curve.equity.iloc[-1]), "realized_pnl": realized,
               "unrealized_pnl": quantity * float(bars.close.iloc[-1]) - entry_cost,
               "total_fees": total_fees, "halted": halted, "pending_intent": pending,
               "journal_events": len(journal),
               "journal_head_sha256": journal[-1]["sha256"], "real_orders_sent": 0, "paper_orders_sent": 0,
               "model_fits": 0, "holdout_scored": False, "ise_reserved_rows": 108,
               "strategy_validated": False, "economic_performance_claim": False,
               "limitations": ["EMA rule and risk numbers test execution plumbing; they are not optimized or validated",
                               "Historical OHLC cannot reconstruct intrabar path, spread, latency or queue priority",
                               "Gap losses can exceed planned risk; halts cannot guarantee a maximum loss",
                               "Open replay-end positions are marked, not fabricated as completed exits",
                               "No external orders, connection, credentials or durable live recovery"]}
    if abs(summary["ending_equity"] - p.starting_cash - realized - summary["unrealized_pnl"]) > 1e-7:
        raise ValueError("BOT_PNL_RECONCILIATION")
    return summary, curve, journal


def build_report(summary, curve, journal):
    """Export caller-owned evidence in memory; never write or overwrite a file."""
    records = curve.copy()
    records["timestamp"] = records.timestamp.map(lambda v: v.isoformat())
    content = {"schema": "tradelab.offline-rehearsal.report.v1", "summary": summary,
               "curve": records.to_dict(orient="records"), "journal": journal}
    payload = _canonical({"content": content, "sha256": _sha(content)})
    verify_report(payload)
    return payload


def verify_report(payload):
    """Detect accidental report/event edits, not authenticate a malicious owner."""
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_REPORT_BYTES:
        raise ValueError("BOT_REPORT_SIZE")
    try:
        report = json.loads(payload.decode("utf-8"))
        if set(report) != {"content", "sha256"} or not hmac.compare_digest(report["sha256"], _sha(report["content"])):
            raise ValueError("Digest")
        content, previous = report["content"], _ZERO
        if content["schema"] != "tradelab.offline-rehearsal.report.v1":
            raise ValueError("Schema")
        for i, record in enumerate(content["journal"]):
            fields = {k: v for k, v in record.items() if k != "sha256"}
            if (type(record["sequence"]) is not int or record["sequence"] != i or
                    record["previous_sha256"] != previous or not hmac.compare_digest(record["sha256"], _sha(fields))):
                raise ValueError("Chain")
            previous = record["sha256"]
        summary = content["summary"]
        if (not content["journal"] or summary["journal_head_sha256"] != previous or
                summary["journal_events"] != len(content["journal"]) or
                summary["visible_bars"] != len(content["curve"]) or
                summary["mode"] != "OFFLINE_REHEARSAL_ONLY" or
                any(type(summary[k]) is not int or summary[k] != 0 for k in ("real_orders_sent", "paper_orders_sent", "model_fits")) or
                summary["holdout_scored"] is not False or summary["strategy_validated"] is not False):
            raise ValueError("Bounds")
        from research_workspace.bot_ledger import recover_ledger
        recovered = recover_ledger(content["journal"], expected_head=previous)
        expected_policy, delay, policy = _scenario_policy(summary["scenario"])
        if (summary["policy"] != policy or summary["policy_sha256"] != _sha(policy) or
                recovered["policy_sha256"] != summary["policy_sha256"] or
                recovered["symbol"] != summary["symbol"] or
                type(summary["synthetic"]) is not bool or recovered["synthetic"] != summary["synthetic"] or
                recovered["ending_position"] != summary["ending_position"] or
                recovered["halted"] is not summary["halted"] or
                recovered["pending_intents"] != ([] if summary["pending_intent"] is None else [summary["pending_intent"]])):
            raise ValueError("Recovered identity")
        if any(intent["execute_index"] < summary["visible_bars"] for intent in recovered["pending_intents"]):
            raise ValueError("Overdue pending intent")
        for record in content["journal"]:
            if record["kind"] == "INTENT" and record["execute_index"] != record["signal_index"] + 1 + delay:
                raise ValueError("Registered delay")
            if record["kind"] != "FILL":
                continue
            notional = record["quantity"] * record["price"]
            if abs(record["fee"] - notional * expected_policy.fee_bps / 10_000) > 1e-7:
                raise ValueError("Registered fee")
            if record["side"] == "BUY":
                unit_loss = record["price"] - record["stop"] * (1 - expected_policy.slippage_bps / 10_000) + record["price"] * expected_policy.fee_bps / 10_000 * 2
                if (abs(record["stop"] - record["price"] * (1 - expected_policy.stop_fraction)) > 1e-7 or
                        abs(record["target"] - record["price"] * (1 + expected_policy.target_fraction)) > 1e-7 or
                        notional + record["fee"] > record["equity_before"] * expected_policy.maximum_position_fraction + 1e-7 or
                        abs(record["planned_risk"] - record["quantity"] * unit_loss) > 1e-7 or
                        record["planned_risk"] > record["equity_before"] * expected_policy.planned_risk_fraction + 1e-7):
                    raise ValueError("Registered risk limits")
        for key in ("starting_cash", "ending_cash", "realized_pnl", "total_fees"):
            if type(summary[key]) not in (float, int) or abs(summary[key] - recovered[key]) > 1e-7:
                raise ValueError("Recovered balances")
        cash, qty, halted, event_index, prior_stamp = recovered["starting_cash"], 0, False, 0, None
        if type(summary["visible_bars"]) is not int or not 0 < summary["visible_bars"] <= summary["replay_limit"]:
            raise ValueError("Replay bound")
        for i, row in enumerate(content["curve"]):
            if set(row) != {"timestamp", "close", "cash", "position", "equity", "halted"}:
                raise ValueError("Curve schema")
            stamp = pd.Timestamp(row["timestamp"])
            if pd.isna(stamp) or stamp.tzinfo is None or prior_stamp is not None and stamp <= prior_stamp:
                raise ValueError("Curve time")
            prior_stamp = stamp
            while event_index < len(content["journal"]) and content["journal"][event_index]["bar_index"] <= i:
                record = content["journal"][event_index]
                if record["kind"] == "FILL":
                    cash, qty = record["cash_after"], record["position_after"]
                elif record["kind"] == "HALT":
                    halted = True
                event_index += 1
            if (type(row["position"]) is not int or row["position"] != qty or row["halted"] is not halted or
                    any(type(row[k]) not in (float, int) or not math.isfinite(row[k]) for k in ("cash", "equity", "close")) or
                    row["close"] <= 0 or abs(row["cash"] - cash) > 1e-7 or
                    abs(row["equity"] - cash - qty * row["close"]) > 1e-7):
                raise ValueError("Curve accounting")
        if event_index != len(content["journal"]) or not content["curve"]:
            raise ValueError("Unseen journal event")
        last = content["curve"][-1]
        if (abs(summary["ending_equity"] - last["equity"]) > 1e-7 or
                abs(summary["unrealized_pnl"] - qty * last["close"] + recovered["entry_cost"]) > 1e-7):
            raise ValueError("Curve end balance")
        return content
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, OverflowError):
        raise ValueError("BOT_REPORT_REJECTED") from None
