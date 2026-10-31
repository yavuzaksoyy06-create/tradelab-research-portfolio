"""Render only scored UCI validation observations, with source credit and baselines."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from research_workspace.ise_source import read_snapshot
from research_workspace.ise_ml import evaluate


def build(snapshot, output):
    frame, meta = read_snapshot(snapshot)
    summary, rows = evaluate(frame, meta)
    if rows.empty or rows.origin_index.max() >= 428:
        raise ValueError("Validation-only chart required")
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    plt.style.use("dark_background")
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), gridspec_kw={"height_ratios": [2, 1, 1.4]})
    fig.patch.set_facecolor("#0b1322")
    for ax in axes:
        ax.set_facecolor("#101c2e")
        ax.grid(alpha=.15)
    axes[0].plot(rows.date, rows.actual_return, color="#8ebcef", lw=1.3, label="Observed index return")
    axes[0].plot(rows.date, rows.prediction, color="#edc57e", lw=1.4, label="Retrospective ridge prediction")
    for name, marker, color in (("LONG", "^", "#44d2a1"), ("WATCH", "o", "#edc57e"), ("CASH", "s", "#ec8e99")):
        selected = rows.loc[rows.signal == name]
        axes[0].scatter(selected.date, selected.prediction, marker=marker, s=23, color=color, label=name, zorder=3)
    axes[0].set_ylabel("Source return units")
    axes[0].legend(loc="lower left", fontsize=8, ncol=3)
    axes[0].set_title("Real historical observations and fixed research signals", loc="left", fontsize=12)
    axes[1].bar(rows.date, rows.actual_return - rows.prediction, color="#929ce6", width=1.7)
    axes[1].axhline(0, color="white", lw=.7)
    axes[1].set_ylabel("Actual − prediction")
    labels, values = [], []
    for name in ("ridge", "train_mean", "zero", "persistence"):
        labels.append(name.replace("_", " "))
        values.append(summary["metrics"][name]["rmse"])
    axes[2].barh(labels, values, color=["#edc57e", "#8ebcef", "#44d2a1", "#929ce6"])
    axes[2].set_xlabel("Validation RMSE (lower is better)")
    axes[2].invert_yaxis()
    fig.suptitle("Istanbul index ML · 107 chronological validation observations", fontsize=17, x=.08, ha="left")
    fig.text(.08, .925, summary["evaluation_first_date"] + " to " + summary["evaluation_last_date"] +
             " | final 108 observations excluded | no parameter search", fontsize=9, color="#b4c5d9")
    accuracy = summary["metrics"]["ridge"]["directional_accuracy"]
    reference = summary["metrics"]["train_mean"]["directional_accuracy"]
    fig.text(.08, .045,
             f"Directional accuracy: ridge {accuracy:.1%}; train-mean baseline {reference:.1%}. No tradable-edge claim.\n"
             "Source: Akbilgic (2013), UCI 247, DOI 10.24432/C54P4J, CC BY 4.0. Derived visualization.\n"
             "Return definition unverified: no reconstructed prices, financial P&L or calibrated probabilities.",
             fontsize=9, color="#b4c5d9")
    fig.subplots_adjust(top=.88, bottom=.15, left=.12, right=.96, hspace=.5)
    fig.savefig(target / "ise-ml-validation.png", dpi=160)
    plt.close(fig)
    (target / "ise-ml-validation.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(args.snapshot, args.output)
