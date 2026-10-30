"""Explicit entitled local BIST import/evaluation. No network or orders."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_workspace.bist_research import CONSTANTS, MAX_BYTES, SYMBOLS, analyze
from research_workspace.bist_store import register, read_snapshot
from research_workspace.stage7_preparation_ui import _local_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("register")
    create.add_argument("--input", required=True)
    create.add_argument("--symbol", choices=SYMBOLS, required=True)
    create.add_argument("--provider", required=True)
    create.add_argument("--source-url", required=True)
    create.add_argument("--license-reference", required=True)
    create.add_argument("--output", required=True)
    create.add_argument("--confirm-local-research-rights", action="store_true")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    try:
        if args.action == "register":
            if args.confirm_local_research_rights is not True:
                raise ValueError("Explicit rights acknowledgement required")
            source = Path(args.input)
            if (not _local_directory(str(source.parent)) or source.is_symlink() or
                    source.is_junction() or not source.is_file()):
                raise ValueError("Local regular source file required")
            with source.open("rb") as stream:
                payload = stream.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError("Bounded CSV required")
            manifest = {**CONSTANTS, "symbol": args.symbol, "provider": args.provider,
                        "source_url": args.source_url, "license_reference": args.license_reference,
                        "csv_sha256": hashlib.sha256(payload).hexdigest()}
            saved = register(payload, manifest, args.output)
            report = {"status": "registered_privately", "protocol": saved["protocol"],
                      "csv_sha256": saved["csv_sha256"], "bars": saved["bars"]}
        else:
            frame, manifest = read_snapshot(args.snapshot)
            report, _ = analyze(frame, manifest)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Exception:
        # Never echo provider content, local paths, arbitrary metadata or raw errors.
        print("BIST operation rejected. Check rights, local paths, source metadata, coverage and hashes.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
