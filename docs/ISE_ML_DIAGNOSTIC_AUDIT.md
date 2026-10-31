# Post-hoc ML diagnostic and signal audit

This descriptive extension was added **after** the first UCI validation result was observed. It does not modify the registered model, features, signal threshold, periods, resampling specification or data. Its tables cannot be treated as an independently registered confirmatory experiment. Re-evaluation reproduced the original validation summary exactly.

## Actual stability findings

Across the six expanding validation windows, the Ridge model reduces squared error relative to the training-mean baseline in three and increases it in three. Aggregate directional counts are 53 true-positive, 38 false-positive, 9 false-negative and 7 true-negative. Positive labels are common: plain accuracy of 56.1% corresponds to balanced accuracy of only 50.5%.

| Historical label | Observations | Empirical positive-return share |
| --- | ---: | ---: |
| LONG | 19 | 52.63% |
| WATCH | 72 | 59.72% |
| CASH | 16 | 56.25% |

These are observed group fractions, **not calibrated forecast probabilities**, financial returns or trading approval. They do not show that LONG dominates WATCH or justify changing the threshold. Small groups and source preprocessing limit interpretation. [Exact descriptive results](images/ise_ml/ise-ml-diagnostics.json) preserve the fold and signal tables, including source-unit means.

## Application behavior

The historical signal inspector selects only an already-scored visible observation. It shows its retrospective prediction, research label, training cutoff, feature cutoff and three largest signed linear contributions. Changing the inspector selection reuses the same report without fitting another model.

The in-memory report is bound to registration identity and replay count. Changing the cursor or source, failing a reload, explicitly reloading even the same snapshot, or leaving loopback mode invalidates the report. A fresh model evaluation always requires the explicit evaluation button. A matching report can survive a display-only rerun; it never extends itself into hidden dates.

## Additional safeguards and tests

Diagnostic inputs must be the contiguous visible validation prefix beginning at row 321, below row 428, with consistent fold numbers and fixed signal definitions. Invalid dates, reserved indices, nonfinite statistics and relabeled signals are rejected. Empty input reports unavailable metrics instead of invented success.

Seven diagnostic tests include independent count/weighted-error reconciliation and an imbalanced example where 90% plain accuracy is only 50% balanced accuracy. Two additional AppTests verify inspector interaction does not refit, and same-path reload cannot reuse an old report. Existing replay/holdout and source tests remain in force. No economic P&L, current forecast, order execution or holdout release is added.
