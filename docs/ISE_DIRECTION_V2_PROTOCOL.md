# Registered exploratory direction experiment v2

Registered before any v2 evaluation on real observations; simulated software tests are separate. Baseline `055e436`; the v1 result has already been inspected. This experiment does not modify v1, the reserved 108 observations, frozen V4/V4.1, the BIST-stock 2025 holdout or the 2027-01-21 21:15 UTC gate. The [machine-readable specification](../research_workspace/ise_direction_v2_spec.json) is committed with this document. Numeric clipping, Armijo coefficient and exact threshold equality behavior were clarified during implementation, before the first real v2 evaluation.

## Question and limits

Can a compact direction model with training-only nested selection improve on simple direction references on the previously inspected UCI validation period? Direction is a distinct target from v1's continuous-return regression. This is **exploratory reused validation, not a fresh independent test**. Computationally chronological selection cannot undo prior human inspection. No reliable-alpha, calibrated-probability or trading-release claim follows from a favorable comparison.

Source: the same pinned UCI 247 snapshot, Akbilgic (2013), DOI 10.24432/C54P4J, CC BY 4.0. Target is `ise_try > 0`; zero is nonpositive. Features are only target lag two, lag three, prior-five mean, prior-twenty mean and prior-twenty population standard deviation. Rolling windows end at observation t-2. Foreign-index features are excluded to reduce complexity and exposure to source-provided foreign-series filling. That does not establish point-in-time vintage or return semantics.

## Fixed outer and inner chronology

Keep v1's first 321 development rows, 107 validation rows (321–427), final 108 reserved rows, feature warm-up at index 22 and six outer windows starting at 321, 341, 361, 381, 401 and 421. Outer windows have at most 20 rows and are capped by visible replay and index 428.

For outer start s, let E=s-2 be the exclusive eligible training end. Final outer training indices are [22,E). Inner validation windows are exactly [E-150,E-100), [E-100,E-50), [E-50,E). Each inner training range is [22,inner_start-2). The first inner fit therefore has 145 training observations and pooled inner validation has 150 observations. Each scaler is fitted on its own training subset. Later outer windows may use earlier completed outer observations; no **current or future outer-block label** enters selection or fitting.

## Model and bounded selection

Use unweighted L2 logistic regression with objective: sum of binary negative log likelihood plus alpha/2 times squared standardized coefficient norm. The intercept is unpenalized. Use training-only population standard deviation, mapping a near-zero scale to one. Solver is deterministic Newton/Armijo, maximum 100 iterations, gradient infinity tolerance 1e-8 and at most 32 step halvings; unfinished or nonfinite fits fail closed. Single-class training uses the declared Laplace-frequency fallback and reports it.

Alpha candidates are exactly 1, 10 and 100. Minimize pooled inner Brier score; ties within 1e-12 prefer the larger alpha. For the selected alpha only, choose decision threshold from 0.4, 0.5 and 0.6 by pooled inner balanced accuracy; ties within 1e-12 prefer closest to 0.5, then larger threshold. A one-class inner pool uses threshold 0.5. Log every candidate score, exact boundary, selected setting and convergence status. No search beyond this registered family/grid or post-result threshold/model edits.

The direction rule is strictly `score > threshold`; equality is nonpositive. Numerical scores and log-loss inputs are clipped to [1e-12, 1-1e-12]. Armijo uses coefficient 1e-4. These are numerical/decision conventions, not extra tuned candidates.

A simulated full-fold test exposed floating-point stagnation near an optimum: objective changes were smaller than rounding precision while the gradient remained just above tolerance. Before any real v2 run, the solver was clarified to accept a near-equal objective endpoint only when its gradient actually meets the same 1e-8 tolerance and its objective is within eight float64 epsilon units scaled by the current objective. The tolerance and iteration limit were not relaxed.

## References, evidence and outcome interpretation

References: smoothed training positive frequency, hard training majority, hard lag-two direction and the unchanged v1 Ridge sign. v1 gets direction metrics only; its regression output is not a probability. Hard-reference log loss is clipped at epsilon 1e-12 and explicitly labeled. No reference is selected after inspecting results.

Primary metric: paired Brier improvement versus smoothed training frequency. Secondary: log loss, balanced/plain accuracy, five fixed calibration bins/ECE, per-fold training/outer error gap and positive prediction share. The paired moving-block interval uses block length 20, 500 replicates and seed 7. It is a dependent small-sample descriptive interval, not a new confirmatory significance test or multiplicity-adjusted discovery. Report unfavorable results as well as favorable ones; no guarantee of improvement is made.

Raw model scores remain uncalibrated. Labels are historical UP/NONPOSITIVE research classifications, not broker instructions or current recommendations. Source return construction remains unverified, so no price reconstruction, transaction-cost P&L or profitability claim is allowed. Final holdout remains unscored regardless of outcome.

Tests must independently verify logistic optimization, inner-scaler isolation, selection ties, one-class behavior, current/future-label exclusion, prefix/suffix invariance, immutable spec binding, reserved-row rejection and unchanged v1 files/results. The actual run occurs only after this registration checkpoint and implementation checks.

Method references: [chronological splitting and gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html), [threshold tuning and overfitting](https://scikit-learn.org/stable/modules/classification_threshold.html), [Brier score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html). The implementation is NumPy; these references do not imply scikit-learn ran the experiment.
