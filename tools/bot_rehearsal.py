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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("rehearsal", "stress"):
        command = sub.add_parser(name)
        command.add_argument("--csv", help="Absolute local path; absent means explicitly synthetic demo")
        command.add_argument("--symbol", choices=SYMBOLS, default="SPY")
        command.add_argument("--visible-count", type=int)
        command.add_argument("--output", required=True, help="Absolute new JSON file; existing files are never replaced")
        if name == "rehearsal":
            command.add_argument("--halt-at", type=int)
            command.add_argument("--scenario", choices=SCENARIOS, default="baseline")
    command = sub.add_parser("verify")
    command.add_argument("--report", required=True, help="Absolute local rehearsal report")
    args = parser.parse_args(argv)
    try:
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
        if args.csv:
            frame, metadata = read_uploaded_csv(_read(args.csv, MAX_BYTES), args.symbol)
        else:
            frame, metadata = synthetic_fixture(args.symbol)
        if args.action == "rehearsal":
            summary, curve, journal = run_rehearsal(frame, metadata, visible_count=args.visible_count,
                                                    halt_at=args.halt_at, scenario=args.scenario)
            payload = build_report(summary, curve, journal)
        else:
            from research_workspace.bot_stress import run_stress_suite
            result = run_stress_suite(frame, metadata, visible_count=args.visible_count)
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
