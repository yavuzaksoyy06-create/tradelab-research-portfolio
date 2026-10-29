"""Explicit local research CLI. No network without the collect --allow-download action."""
from pathlib import Path
import argparse
import json
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research_workspace.stage7_history import collect_history, save_private, load_private
from research_workspace.stage7_validation import evaluate_history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--symbol", choices=["SPY", "MSFT", "QQQ"], required=True)
    collect.add_argument("--feed", choices=["iex", "sip"], required=True)
    collect.add_argument("--start", required=True)
    collect.add_argument("--end", required=True)
    collect.add_argument("--output", required=True)
    collect.add_argument("--allow-download", action="store_true")
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--snapshot", required=True)
    args = parser.parse_args()
    try:
        if args.action == "collect":
            frame, meta = collect_history(
                args.symbol, args.start, args.end, feed=args.feed,
                api_key=os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID"),
                api_secret=os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY"),
                explicit_download=args.allow_download)
            manifest = save_private(frame, meta, args.output)
            print(json.dumps({"status": "saved privately", "sha256": manifest["csv_sha256"],
                              "bars": manifest["received_bars"]}))
        else:
            frame, manifest = load_private(args.snapshot)
            print(json.dumps(evaluate_history(frame, manifest), indent=2, allow_nan=False))
    except Exception:
        # Do not print exception bodies, credentials, paths or provider responses.
        print("Research operation rejected. Check bounds, complete coverage, entitlement, snapshot hash and private destination.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
