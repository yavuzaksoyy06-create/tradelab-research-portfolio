"""Explicit offline rehearsal, stress and report verification; no broker actions."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_workspace.bot_rehearsal import (
    MAX_REPORT_BYTES, SCENARIOS, build_report, run_rehearsal, verify_report,
)
from research_workspace.equity_data import MAX_BYTES, SYMBOLS, read_uploaded_csv, synthetic_fixture
from research_workspace.bot_strategy import MAX_STRATEGY_PLAN_BYTES, decode_strategy_plan
from research_workspace.stage7_preparation_ui import _local_directory


def _local_file(value):
    path = Path(value)
    if (not path.is_absolute() or not _local_directory(str(path.parent)) or
            path.is_symlink() or path.is_junction()):
        raise ValueError("Local file required")
    return path


def _read(value, maximum):
    with _local_file(value).open("rb") as stream:
        content = stream.read(maximum + 1)
    if not 0 < len(content) <= maximum:
        raise ValueError("Input size")
    return content


def _read_plan(path):
    return decode_strategy_plan(_read(path, MAX_STRATEGY_PLAN_BYTES))


def _outbox(args):
    from research_workspace.bot_intent_outbox import IntentOutbox
    from research_workspace.bot_order_draft import build_order_drafts

    outbox = IntentOutbox(args.db)
    if args.operation == "init":
        outbox.create()
        result = outbox.inspect()
    elif args.operation == "stage":
        drafts = build_order_drafts(_read(args.report, MAX_REPORT_BYTES), _read_plan(args.plan))
        result = outbox.enqueue(drafts, expected_head=args.expected_head)
    elif args.operation == "inspect":
        result = outbox.inspect(expected_head=args.expected_head)
    elif args.operation == "recover":
        result = outbox.recover(expected_head=args.expected_head)
    elif args.operation == "cancel":
        result = {"cancelled": outbox.cancel(args.client_order_id, expected_head=args.expected_head)}
    else:
        result = outbox.halt(expected_head=args.expected_head)
    print(json.dumps({"operation": args.operation, "dispatch_allowed": False, "result": result}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("rehearsal", "stress"):
        command = sub.add_parser(name)
        command.add_argument("--csv", help="Absolute local path; absent means explicitly synthetic demo")
        command.add_argument("--symbol", choices=SYMBOLS, help="Default SPY or the frozen plan's symbol")
        command.add_argument("--plan", help="Absolute local frozen strategy plan JSON")
        command.add_argument("--visible-count", type=int)
        command.add_argument("--output", required=True, help="Absolute new JSON file; existing files are never replaced")
        if name == "rehearsal":
            command.add_argument("--halt-at", type=int)
            command.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    command = sub.add_parser("verify")
    command.add_argument("--report", required=True, help="Absolute local rehearsal report")
    outbox = sub.add_parser("outbox", help="Local offline draft queue")
    operations = outbox.add_subparsers(dest="operation", required=True)
    for operation in ("init", "stage", "inspect", "recover", "cancel", "halt"):
        command = operations.add_parser(operation)
        command.add_argument("--db", required=True, help="Absolute local SQLite file outside Git")
        if operation != "init":
            command.add_argument("--expected-head", help="Previously retained outbox head hash")
        if operation == "stage":
            command.add_argument("--plan", required=True)
            command.add_argument("--report", required=True)
        elif operation == "cancel":
            command.add_argument("--client-order-id", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "outbox":
            return _outbox(args)
        if args.action == "verify":
            payload = _read(args.report, MAX_REPORT_BYTES)
            envelope = json.loads(payload.decode("utf-8"))
            if isinstance(envelope, dict) and envelope.get("content", {}).get("schema") == "tradelab.offline-execution-stress.v1":
                from research_workspace.bot_stress import verify_stress_report
                content = verify_stress_report(envelope)
                count = content["visible_bars"]
            else:
                content = verify_report(payload)
                count = content["summary"]["visible_bars"]
            print(json.dumps({"status": "VERIFIED_OFFLINE_REPORT", "visible_bars": count,
                              "real_orders_sent": 0, "paper_orders_sent": 0}))
            return 0
        target = _local_file(args.output)
        if target.exists():
            raise ValueError("Exclusive new report required")
        plan = _read_plan(args.plan) if args.plan else None
        symbol = args.symbol or (plan["content"]["symbol"] if plan is not None else "SPY")
        if plan is not None and plan["content"]["symbol"] != symbol:
            raise ValueError("Plan symbol mismatch")
        if args.csv:
            frame, metadata = read_uploaded_csv(_read(args.csv, MAX_BYTES), symbol)
        else:
            frame, metadata = synthetic_fixture(symbol)
        plan_option = {"plan": plan} if plan is not None else {}
        if args.action == "rehearsal":
            summary, curve, journal = run_rehearsal(frame, metadata, visible_count=args.visible_count,
                                                    halt_at=args.halt_at, scenario=args.scenario, **plan_option)
            payload = build_report(summary, curve, journal)
        else:
            from research_workspace.bot_stress import run_stress_suite
            result = run_stress_suite(frame, metadata, visible_count=args.visible_count, **plan_option)
            payload = json.dumps(result, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
        with target.open("xb") as stream:
            stream.write(payload)
        print(json.dumps({"status": "OFFLINE_REPORT_CREATED", "action": args.action,
                          "synthetic": metadata["synthetic"], "bytes": len(payload),
                          "real_orders_sent": 0, "paper_orders_sent": 0}))
        return 0
    except Exception:
        print("BOT_COMMAND_REJECTED: local input, protected boundaries, new output path or integrity checks failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
