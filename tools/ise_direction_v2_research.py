"""Run the registered v2 comparison on an existing pinned private source; no collection."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_workspace.ise_source import read_snapshot
from research_workspace.ise_direction_v2 import evaluate_v2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--visible-count", type=int)
    args = parser.parse_args()
    try:
        frame, meta = read_snapshot(args.snapshot)
        summary, _ = evaluate_v2(frame, meta, visible_count=args.visible_count)
        print(json.dumps(summary, indent=2, allow_nan=False))
        return 0
    except Exception:
        print("V2 experiment rejected. Check source identity, registered specification and chronology.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
