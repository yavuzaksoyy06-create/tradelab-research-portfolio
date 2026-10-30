"""Explicit UCI index-return research CLI; no broker or order endpoint."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_workspace.ise_source import fetch_snapshot, read_snapshot
from research_workspace.ise_ml import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--output", required=True)
    collect.add_argument("--allow-download", action="store_true")
    test = sub.add_parser("evaluate")
    test.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    try:
        if args.action == "collect":
            meta = fetch_snapshot(args.output, explicit_download=args.allow_download)
            result = {"status": "registered_privately", "protocol": meta["protocol"],
                      "csv_sha256": meta["csv_sha256"], "raw_source_sha256": meta["raw_source_sha256"],
                      "rows": meta["rows"]}
        else:
            frame, meta = read_snapshot(args.snapshot)
            result, _ = evaluate(frame, meta)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception:
        print("ISE research rejected. Check explicit collection, source identity, local destination and registration hashes.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
