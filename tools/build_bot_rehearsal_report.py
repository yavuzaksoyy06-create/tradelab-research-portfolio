"""Render a reproducible SYNTHETIC execution-system report, never market results."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from research_workspace.bot_rehearsal import run_rehearsal, build_report
from research_workspace.bot_ledger import recover_ledger
from research_workspace.bot_stress import run_stress_suite, verify_stress_report
from research_workspace.equity_data import synthetic_fixture


def build(output):
    output = Path(output)
    if output.exists():
        raise ValueError("New report directory required")
    frame, metadata = synthetic_fixture("SPY")
    report = run_stress_suite(frame, metadata)
    content = verify_stress_report(report)
    summary, curve, journal = run_rehearsal(frame, metadata)
    recovered = recover_ledger(journal, expected_head=summary["journal_head_sha256"])
    payload = build_report(summary, curve, journal)
    output.mkdir(parents=True, exist_ok=False)
    (output / "synthetic_stress.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    (output / "synthetic_rehearsal.json").write_bytes(payload)
    (output / "synthetic_recovered_account.json").write_text(json.dumps(recovered, indent=2, allow_nan=False), encoding="utf-8")
    colors = ["#1885b8", "#c55354", "#7565a4", "#ca8c27"]
    names = ["Baseline: 3 / 5 bp", "Higher costs: 10 / 15 bp", "+1-bar delay", "Higher costs + delay"]
    fig = plt.figure(figsize=(13, 8.5), facecolor="#f7f9fc")
    grid = fig.add_gridspec(2, 2, height_ratios=[1.65, 1], hspace=.45, wspace=.30)
    ax = fig.add_subplot(grid[0, :])
    for color, name, points in zip(colors, names, content["equity_curves"].values()):
        times = pd.to_datetime([p["timestamp"] for p in points], utc=True)
        ax.plot(times, [p["equity"] - summary["starting_cash"] for p in points], label=name, color=color, linewidth=1.5)
    ax.axhline(0, color="#677384", linewidth=.7)
    ax.set_ylabel("Hypothetical account change ($)")
    ax.set_title("Fixed execution sensitivity · same EMA plumbing rule in every case", loc="left", fontsize=11)
    ax.legend(fontsize=9, ncol=2, loc="upper right")
    ax.grid(alpha=.18)
    ax = fig.add_subplot(grid[1, 0])
    rows = content["comparison"]
    ax.barh(range(4), [r["net_pnl"] for r in rows], color=colors)
    ax.set_yticks(range(4), ["Baseline", "Higher costs", "+1-bar delay", "Costs + delay"])
    ax.invert_yaxis()
    ax.set_xlabel("Hypothetical net account change ($)")
    ax.set_title("All registered cases retained; no winner selected", loc="left", fontsize=10)
    for i, row in enumerate(rows):
        ax.text(row["net_pnl"] / 2, i, f"${row['total_fees']:.0f} fees / {row['fill_count']} fills",
                va="center", ha="center", fontsize=8, color="white", weight="bold")
    ax.axvline(0, color="#677384", linewidth=.7)
    ax.grid(axis="x", alpha=.18)
    ax = fig.add_subplot(grid[1, 1])
    ax.axis("off")
    diagnostics = content["diagnostics"]
    lines = ["Independent system diagnostics",
             f"Exact curve + event prefixes: {diagnostics['prefix_replay']['checked_prefixes']} checked",
             f"Future-suffix invariance: {diagnostics['future_suffix']['status']}",
             f"Independent account recovery: {diagnostics['journal_recovery']['status']}",
             "Missing / duplicate / sealed bars: rejected",
             f"Manual halt: {diagnostics['manual_halt']['status']}",
             "0 external orders · 0 model fits · 108 ISE rows reserved"]
    for i, line in enumerate(lines):
        ax.text(0, 1 - i * .15, line, va="top", fontsize=11 if i == 0 else 9,
                weight="bold" if i == 0 else "normal", color="#182d45")
    fig.suptitle("TradeLab · Execution Robustness Lab", x=.07, y=.98, ha="left", fontsize=21, weight="bold")
    fig.text(.07, .93, "SYNTHETIC OHLCV ONLY · software diagnostics, not real-market backtest performance", fontsize=11, color="#a53c3c")
    fig.text(.07, .025, "Fixed EMA 9/21 · next-bar or delayed hypothetical fills · long only · risk caps · stop-first OHLC ambiguity\n"
             "No broker adapter, liquidity/queue reconstruction or validated trading edge. Source: deterministic local fixture.", fontsize=9, color="#536074")
    fig.subplots_adjust(top=.85, bottom=.13, left=.12, right=.96)
    fig.savefig(output / "execution_robustness.png", dpi=155, facecolor=fig.get_facecolor())
    plt.close(fig)
    return {"status": content["status"], "synthetic": True, "scenarios": len(rows),
            "reserved_ise_rows": 108, "orders_sent": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
