"""Render the registered v2 comparison; no tuning and no reserved observations."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from research_workspace.ise_source import read_snapshot
from research_workspace.ise_direction_v2 import evaluate_v2


def build(snapshot, output):
    folder = Path(snapshot)
    def digests():
        result = {}
        for name, limit in (("manifest.json", 100_000), ("bars.csv", 500_000), ("source.zip", 200_000)):
            with (folder / name).open("rb") as stream:
                payload = stream.read(limit + 1)
            if len(payload) > limit:
                raise ValueError("Source size bound")
            result[name] = hashlib.sha256(payload).hexdigest()
        return result
    before = digests()
    frame, meta = read_snapshot(folder)
    summary, curve = evaluate_v2(frame, meta)
    if before != digests() or summary["holdout_scored"] or curve.origin_index.max() >= 428:
        raise ValueError("Source or holdout mismatch")
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    plt.style.use("dark_background")
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={"height_ratios": [1, 1, 1.6]})
    fig.patch.set_facecolor("#0b1322")
    for ax in axes:
        ax.set_facecolor("#101c2e")
        ax.grid(alpha=.15)
    names = ["logistic", "train_prior", "majority", "persistence"]
    colors = ["#e8bd72", "#43d6a6", "#8ebcef", "#b5a0e7"]
    axes[0].barh(names, [summary["metrics"][n]["brier"] for n in names], color=colors)
    axes[0].set_xlabel("Brier error (lower is better); hard references are 0/1 scores")
    axes[0].invert_yaxis()
    all_names = [*names, "v1_ridge_sign"]
    axes[1].barh(all_names, [summary["metrics"][n]["balanced_accuracy"] for n in all_names], color=[*colors, "#ed8f99"])
    axes[1].axvline(.5, ls="--", color="white", lw=.8)
    axes[1].set_xlim(0, 1)
    axes[1].set_xlabel("Balanced directional accuracy")
    axes[1].invert_yaxis()
    axes[2].plot(curve.date, curve.score, color=colors[0], label="Uncalibrated logistic score")
    axes[2].plot(curve.date, curve.threshold, color=colors[1], ls="--", label="Training-selected threshold")
    axes[2].scatter(curve.date, curve.actual_up, s=12, color="#8ebcef", alpha=.7, label="Observed direction (1/0)")
    axes[2].set_ylim(-.05, 1.05)
    axes[2].legend(fontsize=8, loc="center left")
    fig.suptitle("Istanbul direction v2: registered exploratory comparison", fontsize=16, x=.13, ha="left")
    lower, upper = summary["brier_improvement_95_block_interval"]
    fig.text(.13, .91, f"107 reused validation observations | final 108 excluded | paired improvement interval [{lower:.6f}, {upper:.6f}]", fontsize=9)
    conclusion = ("Primary Brier improvement not established." if lower <= 0 else
                  "Positive interval on reused validation; no independent confirmation.")
    fig.text(.13, .045, conclusion + " Same inspected validation, not a fresh independent test.\n"
             "Source: Akbilgic (2013), UCI 247, DOI 10.24432/C54P4J, CC BY 4.0. Derived visualization.\n"
             "No calibrated probability, financial P&L, live forecast or order execution claim.", fontsize=9, color="#b4c5d9")
    fig.subplots_adjust(top=.86, bottom=.15, left=.15, right=.96, hspace=.58)
    fig.savefig(out / "comparison.png", dpi=160)
    plt.close(fig)
    return {"source_files_unchanged": True, "experiment_sha256": summary["experiment_sha256"],
            "evaluated_rows": len(curve), "holdout_scored": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    print(json.dumps(build(a.snapshot, a.output)))
