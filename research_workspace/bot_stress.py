"""Fixed-scenario execution diagnostics, never a strategy optimizer or broker.

Runs against the same validated snapshot and eligible prefix. Artificial suffix
changes are explicitly metamorphic tests, not additional market observations.
"""
import hashlib
import hmac
import json
import math

import numpy as np
import pandas as pd

from research_workspace.bot_rehearsal import run_rehearsal
from research_workspace.bot_ledger import recover_ledger
from research_workspace.stage7_events import validated_history, replay_limit

SCENARIOS = ("baseline", "high_cost", "delay_1_bar", "high_cost_delay_1_bar")
MAX_REPORT_BYTES = 8_000_000


def _sha(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _statistics(summary, curve, journal):
    equity = curve.equity.to_numpy(dtype=float)
    initial = float(summary["starting_cash"])
    peaks = np.maximum.accumulate(np.r_[initial, equity])[1:]
    exposure = curve.position.to_numpy(dtype=float) * curve.close.to_numpy(dtype=float) / equity
    fills = [event for event in journal if event["kind"] == "FILL"]
    return {"scenario": summary["scenario"], "synthetic": summary["synthetic"],
            "fee_bps": float(summary["execution_assumptions"]["fee_bps"]),
            "slippage_bps": float(summary["execution_assumptions"]["slippage_bps"]),
            "additional_delay_bars": int(summary["execution_assumptions"]["additional_delay_bars"]),
            "ending_equity": float(equity[-1]), "net_pnl": float(equity[-1] - initial),
            "net_return": float(equity[-1] / initial - 1),
            "max_drawdown": float(np.min(equity / peaks - 1)),
            "mean_gross_exposure": float(exposure.mean()),
            "maximum_gross_exposure": float(exposure.max()),
            "bars_with_position_share": float((curve.position > 0).mean()),
            "total_fees": float(summary["total_fees"]), "fill_count": len(fills),
            "entries": sum(event["side"] == "BUY" for event in fills),
            "exits": sum(event["side"] == "SELL" for event in fills),
            "rejections": sum(event["kind"] == "REJECT" for event in journal),
            "cancellations": sum(event["kind"] == "CANCEL" for event in journal),
            "ending_position": int(summary["ending_position"]),
            "pending_intent": summary["pending_intent"] is not None,
            "halted": bool(summary["halted"]), "policy_sha256": summary["policy_sha256"],
            "real_orders_sent": 0, "paper_orders_sent": 0, "model_fits": 0}


def _same_curve(first, second):
    try:
        pd.testing.assert_frame_equal(first.reset_index(drop=True), second.reset_index(drop=True),
                                      check_exact=True)
    except AssertionError:
        return False
    return True


def _prefix_audit(frame, metadata, summary, curve, journal):
    n = summary["visible_bars"]
    counts = sorted({count for count in (21, n // 2, n - 1) if 1 <= count < n})
    checks = []
    for count in counts:
        prefix_summary, prefix_curve, prefix_events = run_rehearsal(frame, metadata, visible_count=count)
        curve_equal = _same_curve(prefix_curve, curve.iloc[:count])
        expected_events = [event for event in journal if event["bar_index"] < count]
        journal_equal = prefix_events == expected_events
        checks.append({"visible_bars": count, "curve_identical": curve_equal,
                       "journal_identical": journal_equal,
                       "full_snapshot_replay_limit_preserved": prefix_summary["replay_limit"] == summary["replay_limit"],
                       "passed": curve_equal and journal_equal and prefix_summary["replay_limit"] == summary["replay_limit"]})
    return {"checks": checks, "checked_prefixes": len(checks),
            "status": "PASSED" if checks and all(check["passed"] for check in checks) else
                      "INSUFFICIENT_PREFIXES" if not checks else "FAILED"}


def _future_suffix_audit(frame, metadata, summary, baseline_curve):
    count = summary["visible_bars"] // 2
    if count < 1 or count >= summary["visible_bars"]:
        return {"status": "INSUFFICIENT_PREFIXES", "checked_prefixes": 0}
    altered = frame.copy(deep=True)
    # Only the already-eligible visible suffix changes. The snapshot holdout is
    # never perturbed or scored. Multiplication preserves valid OHLC geometry.
    columns = ["open", "high", "low", "close"]
    altered.loc[altered.index[count:summary["visible_bars"]], columns] *= 1.25
    try:
        _, changed_curve, _ = run_rehearsal(altered, metadata, visible_count=count)
    except ValueError as exc:
        # A source-bound immutable snapshot is expected to reject any byte/value
        # change. Keep its registration intact rather than forging a new one.
        if (metadata.get("research_partition") is not None and
                str(exc) == "Registered snapshot changed; research partition cannot move"):
            return {"status": "REJECTED_AT_SOURCE_BINDING", "checked_prefixes": 0,
                    "source_binding_preserved": True, "artificial_scenario": True}
        raise
    equal = _same_curve(changed_curve, baseline_curve.iloc[:count])
    return {"status": "PASSED" if equal else "FAILED", "checked_prefixes": 1,
            "visible_bars": count, "modified_eligible_suffix_first_index": count,
            "modified_eligible_suffix_end_exclusive": summary["visible_bars"],
            "curve_identical": equal, "artificial_scenario": True}


def _source_guards(frame, metadata):
    checks = []
    missing = frame.drop(index=frame.index[0]).reset_index(drop=True)
    duplicate = pd.concat([frame.iloc[:1], frame], ignore_index=True)
    sealed = frame.copy(deep=True)
    sealed.loc[sealed.index[0], "timestamp"] = pd.Timestamp("2026-10-26T13:30:00Z")
    for name, altered in (("missing_bar", missing), ("duplicate_bar", duplicate), ("sealed_date", sealed)):
        try:
            validated_history(altered, metadata)
        except ValueError:
            checks.append({"case": name, "passed": True, "status": "REJECTED_BEFORE_REHEARSAL"})
        else:
            checks.append({"case": name, "passed": False, "status": "UNEXPECTEDLY_ACCEPTED"})
    return checks


def _halt_audit(frame, metadata, summary, journal):
    buys = [event for event in journal if event["kind"] == "FILL" and event["side"] == "BUY"]
    available = [event for event in buys if event["bar_index"] + 1 < summary["visible_bars"]]
    if not available:
        return {"status": "NOT_EXERCISED_NO_ELIGIBLE_ENTRY", "orders_sent": 0}
    halt_at = available[0]["bar_index"] + 1
    stopped, _, events = run_rehearsal(frame, metadata, visible_count=summary["visible_bars"], halt_at=halt_at)
    halts = [event for event in events if event["kind"] == "HALT"]
    halted_sequence = halts[0]["sequence"] if halts else -1
    late_entries = [event for event in events if event["kind"] == "FILL" and
                    event["side"] == "BUY" and event["sequence"] > halted_sequence]
    passed = bool(halts and stopped["halted"] and not stopped["ending_position"] and not late_entries)
    return {"status": "PASSED" if passed else "FAILED", "halt_at": halt_at,
            "entries_after_halt": len(late_entries), "ending_position": int(stopped["ending_position"]),
            "orders_sent": 0, "artificial_scenario": True}


def _ledger_audit(outputs):
    cases = []
    for scenario in SCENARIOS:
        summary, _, journal = outputs[scenario]
        try:
            recovered = recover_ledger(journal, expected_head=summary["journal_head_sha256"])
        except ValueError:
            cases.append({"scenario": scenario, "status": "REJECTED_SEMANTICS", "passed": False})
            continue
        numeric = ("starting_cash", "ending_cash", "total_fees", "realized_pnl")
        amounts_match = all(type(summary.get(key)) in (int, float) and math.isfinite(summary[key]) and
                            abs(recovered[key] - summary[key]) <= 1e-7 for key in numeric)
        state_match = (recovered["ending_position"] == summary["ending_position"] and
                       recovered["halted"] is summary["halted"] and
                       recovered["policy_sha256"] == summary["policy_sha256"] and
                       recovered["symbol"] == summary["symbol"] and
                       recovered["synthetic"] is summary["synthetic"] and
                       recovered["pending_intents"] == ([summary["pending_intent"]] if summary["pending_intent"] else []))
        passed = amounts_match and state_match
        cases.append({"scenario": scenario, "status": "PASSED" if passed else "ACCOUNT_MISMATCH", "passed": passed,
                      "cash_fees_realized_match": amounts_match, "position_intents_identity_match": state_match,
                      "terminal_head_verified": True, "recovered_cash": recovered["ending_cash"],
                      "recovered_position": recovered["ending_position"],
                      "broker_recovery_supported": False})
    return {"status": "PASSED" if all(case["passed"] for case in cases) else "FAILED", "cases": cases,
            "scope": "Offline account reconstruction, not durable broker restart or exchange reconciliation"}


def run_stress_suite(frame, metadata, *, visible_count=None):
    """Run a fixed sensitivity grid and integrity probes; never pick a winner.

    Returns JSON-ready, hash-bound evidence. It is not independent validation,
    live recovery, strategy optimization or authorization for external orders.
    """
    clean = validated_history(frame, metadata)
    maximum = replay_limit(clean)
    if visible_count is None:
        visible_count = maximum
    if type(visible_count) is not int or not 1 <= visible_count <= maximum:
        raise ValueError("BOT_STRESS_VISIBLE_PREFIX_RESERVED_OR_INVALID")
    outputs = {scenario: run_rehearsal(clean, metadata, visible_count=visible_count, scenario=scenario)
               for scenario in SCENARIOS}
    baseline, baseline_curve, baseline_journal = outputs["baseline"]
    comparison = [_statistics(*outputs[scenario]) for scenario in SCENARIOS]
    equity_curves = {scenario: [{"timestamp": row.timestamp.isoformat(), "equity": float(row.equity)}
                                for row in curve.itertuples(index=False)]
                     for scenario, (_, curve, _) in outputs.items()}
    diagnostics = {"prefix_replay": _prefix_audit(clean, metadata, baseline, baseline_curve, baseline_journal),
                   "future_suffix": _future_suffix_audit(clean, metadata, baseline, baseline_curve),
                   "source_guards": _source_guards(clean, metadata),
                   "manual_halt": _halt_audit(clean, metadata, baseline, baseline_journal),
                   "journal_recovery": _ledger_audit(outputs)}
    statuses = [diagnostics["prefix_replay"]["status"], diagnostics["future_suffix"]["status"],
                diagnostics["manual_halt"]["status"], diagnostics["journal_recovery"]["status"]]
    failed = "FAILED" in statuses or not all(row["passed"] for row in diagnostics["source_guards"])
    incomplete = any(status.startswith(("INSUFFICIENT", "NOT_EXERCISED")) for status in statuses)
    content = {"schema": "tradelab.offline-execution-stress.v1", "mode": "OFFLINE_DIAGNOSTICS_ONLY",
               "status": "FAILED_DIAGNOSTICS" if failed else "PARTIAL_DIAGNOSTICS" if incomplete else "PASSED_DIAGNOSTICS",
               "symbol": baseline["symbol"], "synthetic": baseline["synthetic"],
               "source_independently_verified": False, "point_in_time_vintage_verified": False,
               "dataset_sha256": baseline["dataset_sha256"],
               "visible_prefix_sha256": baseline["visible_prefix_sha256"],
               "visible_bars": baseline["visible_bars"], "snapshot_bars": baseline["snapshot_bars"],
               "replay_limit": baseline["replay_limit"],
               "reserved_snapshot_bars": baseline["reserved_snapshot_bars"],
               "scenarios": list(SCENARIOS), "comparison": comparison, "equity_curves": equity_curves,
               "diagnostics": diagnostics, "real_orders_sent": 0, "paper_orders_sent": 0,
               "model_fits": 0, "holdout_scored": False, "ise_reserved_rows": 108,
               "strategy_promoted": False, "winning_scenario_selected": False,
               "limitations": ["All scenarios are fixed sensitivity diagnostics, not parameter search or independent testing",
                               "Artificial suffix and halt probes are labelled separately from observed market history",
                               "Costs, latency and OHLC fills are assumptions; liquidity and order queues are not reconstructed",
                               "Passing code diagnostics does not establish a profitable or deployable strategy",
                               "Hashes detect accidental changes, not an owner who can rewrite code and recompute hashes"]}
    report = {"content": content, "sha256": _sha(content)}
    verify_stress_report(report)
    return report


def verify_stress_report(report):
    """Verify exported diagnostic structure and hash; never enable execution."""
    try:
        if not isinstance(report, dict) or set(report) != {"content", "sha256"}:
            raise ValueError("Envelope")
        encoded = json.dumps(report, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_REPORT_BYTES or not hmac.compare_digest(report["sha256"], _sha(report["content"])):
            raise ValueError("Digest")
        content = report["content"]
        if (content["schema"] != "tradelab.offline-execution-stress.v1" or
                content["mode"] != "OFFLINE_DIAGNOSTICS_ONLY" or content["scenarios"] != list(SCENARIOS) or
                content["strategy_promoted"] is not False or content["winning_scenario_selected"] is not False or
                content["holdout_scored"] is not False or
                any(type(content[k]) is not int or content[k] != 0 for k in ("real_orders_sent", "paper_orders_sent", "model_fits")) or
                len(content["comparison"]) != len(SCENARIOS) or
                [row["scenario"] for row in content["comparison"]] != list(SCENARIOS) or
                any(row["synthetic"] is not content["synthetic"] or
                    any(type(row[k]) is not int or row[k] != 0 for k in
                        ("real_orders_sent", "paper_orders_sent", "model_fits"))
                    for row in content["comparison"]) or
                set(content["equity_curves"]) != set(SCENARIOS) or
                any(len(curve) != content["visible_bars"] for curve in content["equity_curves"].values())):
            raise ValueError("Bounds")
        return content
    except (ValueError, TypeError, KeyError, UnicodeError, AttributeError, OverflowError):
        raise ValueError("BOT_STRESS_REPORT_REJECTED") from None
