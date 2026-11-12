"""Registered exploratory direction model with nested chronological selection."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from research_workspace import ise_direction_model as model_core
from research_workspace.ise_direction_model import compact_features, fit_logistic, predict_score
from research_workspace.ise_ml import validate_registration, evaluate as evaluate_v1

SPEC_SHA256 = "4114e3b38427d750345a6e19d128b834b93ba9c78acfbfd649d8f2a9f37eee06"
_SPEC_PATH = Path(__file__).with_name("ise_direction_v2_spec.json")


def experiment_specification():
    with _SPEC_PATH.open("rb") as stream:
        raw = stream.read(20_001)
    if len(raw) > 20_000:
        raise ValueError("ISE_V2_SPEC_CHANGED")
    try:
        spec = json.loads(raw.decode("utf-8"))
        canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("ISE_V2_SPEC_CHANGED") from None
    if hashlib.sha256(canonical).hexdigest() != SPEC_SHA256:
        raise ValueError("ISE_V2_SPEC_CHANGED")
    if (list(model_core.FEATURE_NAMES) != spec["features"] or
            model_core.MAX_ITERATIONS != spec["solver"]["max_iterations"] or
            model_core.GRADIENT_TOLERANCE != spec["solver"]["gradient_infinity_tolerance"] or
            model_core.MAX_BACKTRACKING != spec["solver"]["max_halvings"] or
            model_core.SCORE_EPSILON != spec["score_clip_epsilon"] or
            model_core.ARMIJO_CONSTANT != spec["solver"]["armijo_constant"]):
        raise ValueError("ISE_V2_SPEC_CHANGED")
    return spec


def experiment_sha256(metadata):
    spec = experiment_specification()
    value = {"experiment_id": spec["experiment_id"], "spec_sha256": SPEC_SHA256,
             "source_registration_sha256": metadata.get("registration_sha256"),
             "source_validation_binding_sha256": metadata.get("validation_binding_sha256")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def direction_metrics(actual, called_up):
    actual, called_up = np.asarray(actual), np.asarray(called_up)
    if (actual.ndim != 1 or not len(actual) or actual.shape != called_up.shape or
            not np.isin(actual, (0, 1)).all() or not np.isin(called_up, (0, 1)).all()):
        raise ValueError("ISE_V2_METRIC_INPUT")
    actual, called_up = actual.astype(bool), called_up.astype(bool)
    recalls = [float((called_up[actual == cls] == cls).mean()) for cls in (False, True)
               if np.any(actual == cls)]
    return {"directional_accuracy": float((actual == called_up).mean()),
            "balanced_accuracy": float(np.mean(recalls)) if len(recalls) == 2 else None,
            "positive_prediction_share": float(called_up.mean())}


def score_metrics(actual, scores, called_up, *, score_kind):
    actual, scores = np.asarray(actual, dtype=float), np.asarray(scores, dtype=float)
    if (actual.ndim != 1 or actual.shape != scores.shape or not len(actual) or
            not np.isin(actual, (0, 1)).all() or not np.isfinite(scores).all() or
            ((scores < 0) | (scores > 1)).any()):
        raise ValueError("ISE_V2_METRIC_INPUT")
    clipped = np.clip(scores, 1e-12, 1 - 1e-12)
    bins, ece = [], 0.0
    membership = np.minimum((scores * 5).astype(int), 4)
    for i in range(5):
        chosen = membership == i
        n = int(chosen.sum())
        mean_score = float(scores[chosen].mean()) if n else None
        rate = float(actual[chosen].mean()) if n else None
        if n:
            ece += n / len(actual) * abs(mean_score - rate)
        bins.append({"lower": i / 5, "upper": (i + 1) / 5, "count": n,
                     "mean_score": mean_score, "empirical_positive_share": rate})
    return {**direction_metrics(actual, called_up), "brier": float(np.mean((actual - scores) ** 2)),
            "logloss": float(-np.mean(actual * np.log(clipped) + (1 - actual) * np.log1p(-clipped))),
            "ece_5bins": float(ece), "calibration_bins": bins, "score_kind": score_kind,
            "calibrated_probability": False}


def choose_alpha(candidates):
    best = min(row["pooled_inner_brier"] for row in candidates)
    return max(row["alpha"] for row in candidates if abs(row["pooled_inner_brier"] - best) <= 1e-12)


def choose_threshold(actual, scores, grid):
    records = [{"threshold": float(t), "balanced_accuracy": direction_metrics(actual, scores > t)["balanced_accuracy"]}
               for t in grid]
    if len(np.unique(actual)) < 2:
        return .5, records
    best = max(row["balanced_accuracy"] for row in records)
    eligible = [row["threshold"] for row in records if abs(row["balanced_accuracy"] - best) <= 1e-12]
    return min(eligible, key=lambda t: (abs(t - .5), -t)), records


def _fit(x, labels, alpha):
    model = fit_logistic(x, labels, alpha)
    if model.get("converged") is not True:
        raise ValueError("ISE_V2_SOLVER_NOT_CONVERGED")
    return model


def select_inner(frame, outer_start, spec):
    """Only eligible past labels select alpha and threshold; no current block labels."""
    if (spec != experiment_specification() or type(outer_start) is not int or
            outer_start not in range(spec["validation_start"], spec["holdout_start"], spec["outer_fold_rows"])):
        raise ValueError("ISE_V2_INVALID_INNER_WINDOW")
    end = outer_start - spec["purge_rows"]
    starts = [end - 150, end - 100, end - 50]
    candidates, score_by_alpha, pooled_labels = [], {}, None
    for alpha in spec["alpha_grid"]:
        scores, labels, fits = [], [], []
        for start in starts:
            train = list(range(spec["warmup_start"], start - spec["purge_rows"]))
            targets = list(range(start, start + spec["inner_fold_rows"]))
            y = (frame.ise_try.iloc[train].to_numpy() > 0).astype(float)
            model = _fit(compact_features(frame, train), y, alpha)
            scores.extend(predict_score(model, compact_features(frame, targets)).tolist())
            labels.extend((frame.ise_try.iloc[targets].to_numpy() > 0).astype(float).tolist())
            fits.append({"training_first_index": train[0], "training_end_index": train[-1],
                         "training_rows": len(train), "validation_first_index": targets[0],
                         "validation_end_index": targets[-1], "validation_rows": len(targets),
                         "iterations": int(model["iterations"]), "converged": True,
                         "constant_class": bool(model["constant_class"]), "fit_status": model["fit_status"]})
        scores, pooled_labels = np.asarray(scores), np.asarray(labels)
        score_by_alpha[alpha] = scores
        candidates.append({"alpha": float(alpha), "pooled_inner_rows": len(scores),
                           "pooled_inner_brier": float(np.mean((pooled_labels - scores) ** 2)), "fits": fits})
    alpha = choose_alpha(candidates)
    threshold, threshold_scores = choose_threshold(pooled_labels, score_by_alpha[alpha], spec["threshold_grid"])
    return alpha, threshold, {"outer_start_index": outer_start, "eligible_training_end_exclusive": end,
                             "alpha_candidates": candidates, "threshold_candidates": threshold_scores,
                             "selected_alpha": alpha, "selected_threshold": threshold,
                             "selected_inner_brier": next(c["pooled_inner_brier"] for c in candidates if c["alpha"] == alpha),
                             "inner_label_classes": int(len(np.unique(pooled_labels)))}


def _interval(values):
    if len(values) < 20:
        return None
    rng, n = np.random.default_rng(7), len(values)
    means = []
    for _ in range(500):
        starts = rng.integers(0, n - 20 + 1, size=int(np.ceil(n / 20)))
        means.append(np.concatenate([values[s:s + 20] for s in starts])[:n].mean())
    return [float(x) for x in np.quantile(means, [.025, .975])]


def evaluate_v2(frame, metadata, *, visible_count=None):
    spec = experiment_specification()
    clean = validate_registration(frame, metadata)
    if visible_count is None:
        visible_count = spec["holdout_start"]
    if type(visible_count) is not int or not 0 <= visible_count <= spec["rows"]:
        raise ValueError("ISE_V2_INVALID_VISIBLE_COUNT")
    end = min(visible_count, spec["holdout_start"])
    summary = {"experiment_id": spec["experiment_id"], "spec_sha256": SPEC_SHA256,
               "experiment_sha256": experiment_sha256(metadata),
               "source_registration_sha256": metadata["registration_sha256"],
               "input_rows": spec["rows"], "validation_start": spec["validation_start"],
               "holdout_start": spec["holdout_start"], "reserved_rows": 108,
               "evaluated_rows": max(0, end - spec["validation_start"]),
               "feature_count": len(spec["features"]), "outer_validation_previously_inspected": True,
               "fresh_independent_test": False, "holdout_scored": False,
               "probabilities_publishable": False, "economic_pnl_computed": False,
               "orders_enabled": False, "status": "INSUFFICIENT_VISIBLE_VALIDATION"}
    if end <= spec["validation_start"]:
        return summary, pd.DataFrame()
    rows, traces, fit_diagnostics = [], [], []
    for start in range(spec["validation_start"], end, spec["outer_fold_rows"]):
        alpha, threshold, trace = select_inner(clean, start, spec)
        traces.append(trace)
        train = list(range(spec["warmup_start"], start - spec["purge_rows"]))
        targets = list(range(start, min(start + spec["outer_fold_rows"], end)))
        y = (clean.ise_try.iloc[train].to_numpy() > 0).astype(float)
        model = _fit(compact_features(clean, train), y, alpha)
        x = compact_features(clean, targets)
        scores = predict_score(model, x)
        actual = (clean.ise_try.iloc[targets].to_numpy() > 0).astype(float)
        prior = float((y.sum() + 1) / (len(y) + 2))
        majority = float(y.sum() > len(y) / 2)
        outer_brier = float(np.mean((actual - scores) ** 2))
        fit_diagnostics.append({"fold": (start - spec["validation_start"]) // spec["outer_fold_rows"],
                                "training_rows": len(train), "validation_rows": len(targets),
                                "training_end_index": train[-1], "alpha": alpha, "threshold": threshold,
                                "train_brier": float(model["train_brier"]), "outer_brier": outer_brier,
                                "outer_minus_train_brier": outer_brier - model["train_brier"],
                                "train_logloss": float(model["train_logloss"]),
                                "selected_inner_brier": trace["selected_inner_brier"],
                                "outer_minus_selected_inner_brier": outer_brier - trace["selected_inner_brier"],
                                "coefficient_l2_norm": float(np.linalg.norm(model["coef"])),
                                "iterations": int(model["iterations"]), "converged": True,
                                "constant_class": bool(model["constant_class"]),
                                "interpretation": "Descriptive gap, not proof or absence of overfitting"})
        for j, t in enumerate(targets):
            effects = ((x[j] - model["mean"]) / model["scale"]) * model["coef"]
            rows.append({"date": clean.date.iloc[t], "origin_index": t, "actual_up": int(actual[j]),
                         "score": float(scores[j]), "threshold": threshold,
                         "predicted_up": bool(scores[j] > threshold),
                         "research_label": "UP_RESEARCH" if scores[j] > threshold else "NONPOSITIVE_RESEARCH",
                         "prior_score": prior, "majority_score": majority,
                         "persistence_score": float(clean.ise_try.iloc[t - 2] > 0), "alpha": alpha,
                         "model_fold": (start - spec["validation_start"]) // spec["outer_fold_rows"],
                         "training_end_index": train[-1], "training_end": clean.date.iloc[train[-1]].date().isoformat(),
                         "feature_cutoff_index": t - 2, "feature_cutoff": clean.date.iloc[t - 2].date().isoformat(),
                         "intercept_logit": float(model["intercept"]),
                         "logit_contributions": [{"feature": name, "contribution": float(value)}
                                                 for name, value in zip(spec["features"], effects)]})
    curve = pd.DataFrame(rows)
    _, reference = evaluate_v1(clean, metadata, visible_count=end)
    if (not np.array_equal(curve.origin_index, reference.origin_index) or
            not np.array_equal(curve.date.to_numpy(), reference.date.to_numpy()) or
            not np.array_equal(curve.actual_up, (reference.actual_return.to_numpy() > 0).astype(int))):
        raise ValueError("ISE_V2_REFERENCE_ALIGNMENT")
    curve["v1_predicted_up"] = reference.prediction.to_numpy() > 0
    actual = curve.actual_up.to_numpy()
    metrics = {"logistic": score_metrics(actual, curve.score, curve.predicted_up, score_kind="uncalibrated_logistic_score")}
    for name, column, kind in (("train_prior", "prior_score", "smoothed_training_frequency"),
                               ("majority", "majority_score", "hard_reference_score"),
                               ("persistence", "persistence_score", "hard_reference_score")):
        values = curve[column].to_numpy()
        metrics[name] = score_metrics(actual, values, values > .5, score_kind=kind)
    metrics["v1_ridge_sign"] = {**direction_metrics(actual, curve.v1_predicted_up),
                                "score_kind": "direction_only_not_a_probability", "brier": None,
                                "logloss": None, "calibrated_probability": False}
    improvement = (actual - curve.prior_score.to_numpy()) ** 2 - (actual - curve.score.to_numpy()) ** 2
    summary.update(status="EXPLORATORY_REUSED_VALIDATION", metrics=metrics,
                   selection_trace=traces, fold_fit_diagnostics=fit_diagnostics,
                   mean_brier_improvement_vs_train_prior=float(improvement.mean()),
                   brier_improvement_95_block_interval=_interval(improvement), bootstrap=spec["bootstrap"],
                   evaluation_first_date=curve.date.iloc[0].date().isoformat(),
                   evaluation_last_date=curve.date.iloc[-1].date().isoformat(),
                   label_counts={name: int((curve.research_label == name).sum())
                                 for name in ("UP_RESEARCH", "NONPOSITIVE_RESEARCH")},
                   limitations=["Reused inspected validation; not a fresh independent test",
                                "Nested selection excludes current/future outer labels; past completed labels may be reused",
                                "Raw scores are uncalibrated; empirical ECE is not probability publication approval",
                                "Index directions, not individual-stock quotes, P&L or executable orders",
                                "No final holdout release, frozen v1 modification or V4.1 gate change"])
    try:
        json.dumps(summary, allow_nan=False)
        if not np.isfinite(curve.select_dtypes(include="number").to_numpy()).all():
            raise ValueError("Nonfinite curve")
    except (ValueError, TypeError):
        raise ValueError("ISE_V2_INVALID_CALCULATION") from None
    return summary, curve
