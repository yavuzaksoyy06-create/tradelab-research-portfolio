"""Audit the fixed model without tuning; render training/validation fit diagnostics."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from research_workspace.ise_source import read_snapshot
from research_workspace.ise_ml import evaluate


def build(snapshot, output, reference):
    folder = Path(snapshot)
    limits = {"manifest.json": 100_000, "source.zip": 200_000, "bars.csv": 500_000}
    def digests():
        result = {}
        for name, limit in limits.items():
            with (folder / name).open("rb") as stream:
                payload = stream.read(limit + 1)
            if len(payload) > limit:
                raise ValueError("Audit input exceeds source bounds")
            result[name] = hashlib.sha256(payload).hexdigest()
        return result
    before = digests()
    frame, meta = read_snapshot(folder)
    summary, curve = evaluate(frame, meta)
    old = json.loads(Path(reference).read_text(encoding="utf-8"))
    for field in ("metrics", "signal_counts", "mean_squared_error_improvement_vs_train_mean",
                  "mse_improvement_95_block_interval", "evaluation_first_date", "evaluation_last_date"):
        if summary[field] != old[field]:
            raise ValueError("Registered validation results changed")
    after = digests()
    if before != after or summary["holdout_scored"] or curve.origin_index.max() >= 428:
        raise ValueError("Source or holdout boundary mismatch")
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    rows = pd.DataFrame(summary["fold_fit_diagnostics"])
    plt.style.use("dark_background")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor("#0b1322")
    for ax in axes:
        ax.set_facecolor("#101c2e")
        ax.grid(alpha=.15)
    x = rows.fold + 1
    axes[0].plot(x, rows.train_rmse, "o-", label="Training RMSE", color="#8ebcef")
    axes[0].plot(x, rows.validation_rmse, "o-", label="Validation RMSE", color="#edc57e")
    axes[0].plot(x, rows.validation_train_mean_rmse, "--", label="Validation train-mean baseline", color="#44d2a1")
    axes[0].set_xlabel("Fixed chronological window")
    axes[0].set_ylabel("RMSE (source return units)")
    axes[0].legend(fontsize=8)
    axes[1].plot(x, rows.effective_degrees_of_freedom, "o-", color="#b5a0e7")
    axes[1].axhline(23, color="#d0d8e0", ls="--", label="22 features + intercept")
    axes[1].set_xlabel("Fixed chronological window")
    axes[1].set_ylabel("Effective model degrees of freedom")
    axes[1].set_ylim(0, 24)
    axes[1].legend(fontsize=8)
    fig.suptitle("Istanbul index ML audit: fit gap and fixed model flexibility", fontsize=15)
    fig.text(.07, .05, "Descriptive audit, no tuning. Last validation window has 7 observations; others have 20.\n"
             "Source: Akbilgic (2013), UCI 247, CC BY 4.0. Reserved 108 observations excluded. No P&L claim.", fontsize=9)
    fig.subplots_adjust(left=.08, right=.97, top=.86, bottom=.23, wspace=.28)
    fig.savefig(target / "ise-ml-fit-audit.png", dpi=160)
    plt.close(fig)
    report = {"scope": "Post-hoc audit of fixed registered model; no parameter search",
              "source_files_unchanged": True, "legacy_source_registration_preserved":
              summary["registration_sha256"] == old["registration_sha256"],
              "original_validation_metrics_unchanged": True,
              "model_spec_sha256": summary["model_spec_sha256"],
              "experiment_sha256": summary["experiment_sha256"],
              "source_registration_sha256": summary["registration_sha256"],
              "validation_binding_sha256": meta["validation_binding_sha256"],
              "fold_fit_diagnostics": summary["fold_fit_diagnostics"],
              "holdout_scored": False, "orders_enabled": False}
    (target / "ise-ml-fit-audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference", required=True)
    args = parser.parse_args()
    build(args.snapshot, args.output, args.reference)
