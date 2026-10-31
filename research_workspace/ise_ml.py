"""Registered chronological ridge diagnostics on UCI 247 index returns, not prices."""
from io import BytesIO
import hashlib
import json
import re

import numpy as np
import pandas as pd

PROTOCOL = "tradelab.ise-ml.v1"
COLUMNS = ("date", "ise_try", "ise_usd", "sp", "dax", "ftse", "nikkei", "bovespa", "eu", "em")
SOURCE_URL = "https://archive.ics.uci.edu/dataset/247/istanbul+stock+exchange"
ROWS, VALIDATION_START, HOLDOUT_START = 536, 321, 428
MAX_BYTES = 500_000
RIDGE_LAMBDA, SIGNAL_THRESHOLD = 10.0, 0.005
FEATURE_NAMES = tuple(f"{col}_lag{lag}" for lag in (2, 3) for col in COLUMNS[1:]) + (
    "ise_try_prior5_mean", "ise_try_prior5_std", "ise_try_prior20_mean", "ise_try_prior20_std")


def model_specification():
    """Reject parameter drift under the fixed v1 name; this is not an authenticity signature."""
    columns = "date ise_try ise_usd sp dax ftse nikkei bovespa eu em".split()
    names = [f"{name}_lag{lag}" for lag in (2, 3) for name in columns[1:]] + [
        "ise_try_prior5_mean", "ise_try_prior5_std", "ise_try_prior20_mean", "ise_try_prior20_std"]
    expected = {"protocol": "tradelab.ise-ml.v1", "columns": columns, "rows": 536,
                "validation_start": 321, "holdout_start": 428, "feature_names": names,
                "ridge_lambda": 10.0, "signal_threshold_source_units": 0.005,
                "fold_rows": 20, "training_purge_rows": 2, "minimum_feature_lag_rows": 2,
                "bootstrap_block_rows": 20, "bootstrap_replications": 500, "bootstrap_seed": 7}
    current = {**expected, "protocol": PROTOCOL, "columns": list(COLUMNS), "rows": ROWS,
               "validation_start": VALIDATION_START, "holdout_start": HOLDOUT_START,
               "feature_names": list(FEATURE_NAMES), "ridge_lambda": RIDGE_LAMBDA,
               "signal_threshold_source_units": SIGNAL_THRESHOLD}
    try:
        actual = json.dumps(current, sort_keys=True, separators=(",", ":"), allow_nan=False)
        pinned = json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        raise ValueError("ISE_REGISTERED_MODEL_SPEC_CHANGED") from None
    if actual != pinned:
        raise ValueError("ISE_REGISTERED_MODEL_SPEC_CHANGED")
    return expected


def model_spec_sha256():
    return hashlib.sha256(json.dumps(model_specification(), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _manifest(meta):
    if (not isinstance(meta, dict) or meta.get("source_id") != "uci247" or
            meta.get("license") != "CC-BY-4.0"):
        raise ValueError("ISE_INVALID_MANIFEST")
    for key in ("csv_sha256", "raw_source_sha256"):
        if key in meta or key == "csv_sha256":
            if not isinstance(meta.get(key), str) or not re.fullmatch("[0-9a-f]{64}", meta[key]):
                raise ValueError("ISE_INVALID_MANIFEST")
    if meta.get("source_url") != SOURCE_URL:
        raise ValueError("ISE_INVALID_SOURCE")
    safe = {key: meta[key] for key in ("source_id", "license", "csv_sha256", "raw_source_sha256") if key in meta}
    safe["source_url"] = SOURCE_URL
    return safe


def _validated(frame):
    if tuple(frame.columns) != COLUMNS or len(frame) != ROWS:
        raise ValueError("ISE_INVALID_SCHEMA")
    clean = frame.copy()
    dates = pd.to_datetime(clean.date, format="%Y-%m-%d", errors="raise")
    if dates.isna().any() or dates.dt.tz is not None or (dates != dates.dt.normalize()).any():
        raise ValueError("ISE_INVALID_DATES")
    # Reject prospective/sealed dates before numeric interpretation.
    if (dates >= pd.Timestamp("2026-10-26")).any():
        raise ValueError("ISE_SEALED_PERIOD")
    if (dates >= pd.Timestamp("2025-01-01")).any():
        raise ValueError("ISE_RESERVED_PERIOD")
    if ((dates < pd.Timestamp("2009-01-01")).any() or (dates > pd.Timestamp("2011-12-31")).any() or dates.duplicated().any() or
            not dates.is_monotonic_increasing):
        raise ValueError("ISE_INVALID_DATES")
    clean["date"] = dates
    for name in COLUMNS[1:]:
        clean[name] = pd.to_numeric(clean[name], errors="raise").astype(float)
    if not np.isfinite(clean[list(COLUMNS[1:])].to_numpy()).all():
        raise ValueError("ISE_INVALID_NUMERICS")
    return clean.reset_index(drop=True)


def _fingerprint(frame):
    return hashlib.sha256(frame.to_csv(index=False, float_format="%.17g", date_format="%Y-%m-%d",
                                      lineterminator="\n").encode("utf-8")).hexdigest()


def _registration(meta):
    value = {**_manifest(meta), "protocol": meta.get("protocol"),
             "canonical_sha256": meta.get("canonical_sha256"),
             "validation_start": VALIDATION_START, "holdout_start": HOLDOUT_START}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _validation_binding(meta):
    value = {key: meta.get(key) for key in ("registration_sha256", "rows", "bytes", "orders_enabled",
                                           "validation_start", "holdout_start")}
    value["model_spec_sha256"] = model_spec_sha256()
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def experiment_sha256(metadata):
    value = {"registration_sha256": metadata.get("registration_sha256"),
             "validation_binding_sha256": metadata.get("validation_binding_sha256"),
             "model_spec_sha256": model_spec_sha256()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_csv(payload, manifest):
    """Validate source bytes and bind the full fixed partition; no outcomes computed."""
    meta = _manifest(manifest)
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError("ISE_INPUT_SIZE")
    if hashlib.sha256(payload).hexdigest() != meta["csv_sha256"]:
        raise ValueError("ISE_HASH_MISMATCH")
    frame = _validated(pd.read_csv(BytesIO(payload), dtype=str))
    meta.update(protocol=PROTOCOL, canonical_sha256=_fingerprint(frame), rows=ROWS,
                validation_start=VALIDATION_START, holdout_start=HOLDOUT_START,
                bytes=len(payload), orders_enabled=False)
    meta["registration_sha256"] = _registration(meta)
    # Derived from the exact bytes just consumed. It need not rewrite an older
    # immutable on-disk manifest: read_snapshot rebuilds it from pinned bytes.
    meta["validation_binding_sha256"] = _validation_binding(meta)
    return frame, meta


def validate_registration(frame, metadata):
    """Validate a memory snapshot and fixed specification without fitting a model."""
    model_specification()
    clean = _validated(frame)
    _manifest(metadata)
    fixed = {"rows": ROWS, "validation_start": VALIDATION_START, "holdout_start": HOLDOUT_START}
    if (any(type(metadata.get(key)) is not int or metadata[key] != value for key, value in fixed.items()) or
            type(metadata.get("bytes")) is not int or not 0 < metadata["bytes"] <= MAX_BYTES or
            metadata.get("orders_enabled") is not False):
        raise ValueError("ISE_REGISTERED_INPUT_CHANGED")
    if (metadata.get("protocol") != PROTOCOL or metadata.get("canonical_sha256") != _fingerprint(clean) or
            metadata.get("registration_sha256") != _registration(metadata) or
            metadata.get("validation_binding_sha256") != _validation_binding(metadata)):
        raise ValueError("ISE_REGISTERED_INPUT_CHANGED")
    return clean


def features(frame, indices):
    """Every feature ends at observation t-2, never on the target date."""
    values = frame[list(COLUMNS[1:])].to_numpy(dtype=float)
    result = []
    for t in indices:
        if type(t) is not int or not 22 <= t < HOLDOUT_START:
            raise ValueError("ISE_INVALID_FEATURE_INDEX")
        row = [*values[t - 2], *values[t - 3]]
        for window in (5, 20):
            prior = values[t - window - 1:t - 1, 0]
            row.extend((prior.mean(), prior.std(ddof=0)))
        result.append(row)
    out = np.asarray(result, dtype=float).reshape((-1, len(FEATURE_NAMES)))
    if not np.isfinite(out).all():
        raise ValueError("ISE_INVALID_CALCULATION")
    return out


def fit_ridge(x, y):
    """Train-only standardization; unpenalized intercept and fixed L2 strength."""
    mean, scale = x.mean(axis=0), x.std(axis=0, ddof=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = (x - mean) / scale
    intercept = float(y.mean())
    weights = np.linalg.solve(z.T @ z + RIDGE_LAMBDA * np.eye(z.shape[1]), z.T @ (y - intercept))
    if not all(np.isfinite(v).all() for v in (mean, scale, weights)) or not np.isfinite(intercept):
        raise ValueError("ISE_INVALID_CALCULATION")
    return mean, scale, weights, intercept


def _metrics(actual, predicted):
    errors = actual - predicted
    true_up, predicted_up = actual > 0, predicted > 0
    recalls = [float((predicted_up[true_up == cls] == cls).mean()) for cls in (False, True)
               if np.any(true_up == cls)]
    return {"mae": float(np.abs(errors).mean()), "rmse": float(np.sqrt(np.mean(errors ** 2))),
            "directional_accuracy": float((true_up == predicted_up).mean()),
            "balanced_accuracy": float(np.mean(recalls)) if len(recalls) == 2 else None}


def _interval(values):
    if len(values) < 20:
        return None
    rng, n = np.random.default_rng(7), len(values)
    means = []
    for _ in range(500):
        starts = rng.integers(0, n - 20 + 1, size=int(np.ceil(n / 20)))
        means.append(np.concatenate([values[i:i + 20] for i in starts])[:n].mean())
    return [float(v) for v in np.quantile(means, [.025, .975])]


def evaluate(frame, metadata, *, visible_count=None):
    """Expanding fixed folds; only visible validation labels, never the 108-row holdout."""
    clean = validate_registration(frame, metadata)
    if visible_count is None:
        visible_count = HOLDOUT_START
    if type(visible_count) is not int or not 0 <= visible_count <= ROWS:
        raise ValueError("ISE_INVALID_VISIBLE_COUNT")
    end = min(visible_count, HOLDOUT_START)
    summary = {"protocol": PROTOCOL, "source_id": "uci247", "registration_sha256": metadata["registration_sha256"],
               "model_spec_sha256": model_spec_sha256(), "experiment_sha256": experiment_sha256(metadata),
               "input_rows": ROWS, "validation_start": VALIDATION_START, "holdout_start": HOLDOUT_START,
               "reserved_rows": ROWS - HOLDOUT_START, "evaluated_rows": max(0, end - VALIDATION_START),
               "model": "standardized ridge regression", "ridge_lambda": RIDGE_LAMBDA,
               "feature_count": len(FEATURE_NAMES), "minimum_feature_lag_rows": 2,
               "fold_rows": 20, "training_purge_rows": 2, "parameter_search_performed": False,
               "holdout_scored": False, "orders_enabled": False, "probabilities_publishable": False,
               "source_return_definition": "unverified", "economic_backtest_available": False,
               "prediction_units": "source return units; not independently verified percentages",
               "status": "INSUFFICIENT_VISIBLE_VALIDATION"}
    if end <= VALIDATION_START:
        return summary, pd.DataFrame()
    rows = []
    fold_diagnostics = []
    for fold_start in range(VALIDATION_START, end, 20):
        train = list(range(22, fold_start - 2))
        x = features(clean, train)
        y = clean.ise_try.iloc[train].to_numpy()
        mean, scale, weights, intercept = fit_ridge(x, y)
        targets = list(range(fold_start, min(fold_start + 20, end)))
        standardized = (features(clean, targets) - mean) / scale
        predictions = standardized @ weights + intercept
        fitted = ((x - mean) / scale) @ weights + intercept
        target_values = clean.ise_try.iloc[targets].to_numpy()
        train_rmse = float(np.sqrt(np.mean((y - fitted) ** 2)))
        validation_rmse = float(np.sqrt(np.mean((target_values - predictions) ** 2)))
        z = (x - mean) / scale
        singular = np.linalg.svd(z, compute_uv=False)
        effective_dof = 1.0 + float(np.sum(singular ** 2 / (singular ** 2 + RIDGE_LAMBDA)))
        fold_diagnostics.append({"fold": (fold_start - VALIDATION_START) // 20,
                                 "training_rows": len(train), "feature_count": len(FEATURE_NAMES),
                                 "validation_rows": len(targets),
                                 "training_first_index": train[0], "training_end_index": train[-1],
                                 "training_first_date": clean.date.iloc[train[0]].date().isoformat(),
                                 "training_end_date": clean.date.iloc[train[-1]].date().isoformat(),
                                 "validation_first_index": targets[0], "validation_last_index": targets[-1],
                                 "train_rmse": train_rmse, "validation_rmse": validation_rmse,
                                 "train_mean_rmse": float(np.sqrt(np.mean((y - intercept) ** 2))),
                                 "validation_train_mean_rmse": float(np.sqrt(np.mean((target_values - intercept) ** 2))),
                                 "validation_minus_train_rmse": validation_rmse - train_rmse,
                                 "validation_train_rmse_ratio": validation_rmse / train_rmse if train_rmse > 0 else None,
                                 "effective_degrees_of_freedom": effective_dof,
                                 "coefficient_l2_norm": float(np.linalg.norm(weights)),
                                 "interpretation": "Descriptive fit-gap audit; not proof or absence of overfitting"})
        for j, t in enumerate(targets):
            contributions = standardized[j] * weights
            top = np.argsort(-np.abs(contributions), kind="stable")[:3]
            pred = float(predictions[j])
            rows.append({"date": clean.date.iloc[t], "origin_index": t,
                         "actual_return": float(clean.ise_try.iloc[t]), "prediction": pred,
                         "baseline_mean": intercept, "baseline_zero": 0.0,
                         "baseline_persistence": float(clean.ise_try.iloc[t - 2]),
                         "signal": "LONG" if pred > SIGNAL_THRESHOLD else "CASH" if pred <= 0 else "WATCH",
                         "model_fold": (fold_start - VALIDATION_START) // 20,
                         "training_end": clean.date.iloc[train[-1]].date().isoformat(),
                         "training_end_index": train[-1], "feature_cutoff_index": t - 2,
                         "feature_cutoff": clean.date.iloc[t - 2].date().isoformat(),
                         "intercept": intercept,
                         "top_contributions": [{"feature": FEATURE_NAMES[k], "contribution": float(contributions[k])}
                                               for k in top]})
    curve = pd.DataFrame(rows)
    actual, predicted = curve.actual_return.to_numpy(), curve.prediction.to_numpy()
    numeric = curve.select_dtypes(include="number").to_numpy()
    if not np.isfinite(numeric).all():
        raise ValueError("ISE_INVALID_CALCULATION")
    improvement = (actual - curve.baseline_mean.to_numpy()) ** 2 - (actual - predicted) ** 2
    summary.update(status="RETROSPECTIVE_VALIDATION_ONLY", metrics={"ridge": _metrics(actual, predicted),
                   **{name: _metrics(actual, curve[col].to_numpy()) for name, col in (
                       ("train_mean", "baseline_mean"), ("zero", "baseline_zero"), ("persistence", "baseline_persistence"))}},
                   signal_counts={name: int((curve.signal == name).sum()) for name in ("LONG", "WATCH", "CASH")},
                   fold_fit_diagnostics=fold_diagnostics,
                   signal_threshold_source_units=SIGNAL_THRESHOLD,
                   mean_squared_error_improvement_vs_train_mean=float(improvement.mean()),
                   mse_improvement_95_block_interval=_interval(improvement),
                   bootstrap={"method": "moving_block", "block_rows": 20, "replications": 500, "seed": 7},
                   evaluation_first_date=curve.date.iloc[0].date().isoformat(),
                   evaluation_last_date=curve.date.iloc[-1].date().isoformat(),
                   pnl_computed=False,
                   limitations=["Index returns, not individual-stock OHLCV or executable prices",
                                "Source units and vintage require independent interpretation; no PIT proof",
                                "Two-observation lag limits international close-timing leakage; publication times unverified",
                                "Signals are uncalibrated research classifications, not executable orders",
                                "Small retrospective sample; validation is not a fresh prospective test",
                                "No parameter search, holdout release or frozen V4.1 modification"])
    try:
        json.dumps(summary, allow_nan=False)
    except ValueError:
        raise ValueError("ISE_INVALID_CALCULATION") from None
    return summary, curve
