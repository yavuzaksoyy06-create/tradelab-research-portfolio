"""Fixed expanding-window diagnostics; final historical holdout is never scored."""
from __future__ import annotations
import numpy as np
from research_workspace.stage7_events import (
    HORIZONS, VERSION, INSUFFICIENT, validated_history, fingerprint, causal_features, outcome,
    replay_limit, research_partition, HOLDOUT_SESSIONS, MIN_RESEARCH_SESSIONS,
)

TRAIN_SESSIONS = 40
FOLD_SESSIONS = 10
EMBARGO_BARS = 16


def split_plan(frame):
    sessions = list(dict.fromkeys(frame.session))
    if len(sessions) < MIN_RESEARCH_SESSIONS:
        return {"status": INSUFFICIENT, "folds": [], "holdout_start": None}
    starts = {s: int(np.flatnonzero(frame.session.to_numpy() == s)[0]) for s in sessions}
    holdout_session = len(sessions) - HOLDOUT_SESSIONS
    holdout_start = replay_limit(frame)
    folds = []
    for offset in range(TRAIN_SESSIONS, holdout_session, FOLD_SESSIONS):
        start = starts[sessions[offset]]
        stop_session = min(offset + FOLD_SESSIONS, holdout_session)
        stop = starts[sessions[stop_session]]
        folds.append({"train_label_before": start - EMBARGO_BARS, "start": start, "stop": stop,
                      "start_session": str(sessions[offset]),
                      "end_session": str(sessions[stop_session - 1])})
    return {"status": "DIAGNOSTIC PLAN", "folds": folds, "holdout_start": holdout_start,
            "holdout_sessions": HOLDOUT_SESSIONS,
            "holdout_first_session": str(sessions[holdout_session])}


def bucket(record):
    return (record["structure"], record["ema_sign"],
            "missing" if record["rvol"] is None else "high" if record["rvol"] >= 1.5 else "ordinary")


def fit_frequency(rows):
    if not rows or any(r["outcome"]["up"] not in (0, 1) for r in rows):
        raise ValueError("Only matured binary training labels")
    total = sum(r["outcome"]["up"] for r in rows)
    cells = {}
    for row in rows:
        key = bucket(row["features"])
        n, y = cells.get(key, (0, 0))
        cells[key] = (n + 1, y + row["outcome"]["up"])
    return {"base": (total + 1) / (len(rows) + 2), "majority": int(total * 2 >= len(rows)),
            "cells": cells, "n": len(rows)}


def predict_frequency(model, record):
    n, y = model["cells"].get(bucket(record), (0, 0))
    return (y + 1) / (n + 2) if n >= 30 else model["base"]


def scores(labels, probabilities):
    y, p = np.asarray(labels, dtype=float), np.asarray(probabilities, dtype=float)
    if y.ndim != 1 or not len(y) or p.shape != y.shape:
        raise ValueError("Nonempty equal one-dimensional vectors required")
    if not np.isin(y, [0, 1]).all() or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("Invalid binary labels or probabilities")
    pred = p >= .5
    clipped = np.clip(p, 1e-12, 1 - 1e-12)
    recalls = [float(np.mean(pred[y == c] == c)) for c in (0, 1) if (y == c).any()]
    bins, ece = [], 0.0
    for low, high in zip(np.arange(0, 1, .2), np.arange(.2, 1.01, .2)):
        mask = (p >= low) & ((p < high) if high < .999 else (p <= 1))
        n = int(mask.sum())
        predicted, observed = (float(p[mask].mean()), float(y[mask].mean())) if n else (None, None)
        if n:
            ece += n / len(y) * abs(predicted - observed)
        bins.append({"lower": float(low), "upper": float(high), "n": n,
                     "predicted": predicted, "observed": observed})
    return {"n": len(y), "positive_fraction": float(y.mean()),
            "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))),
            "accuracy": float(np.mean(pred == y)),
            "balanced_accuracy": float(np.mean(recalls)) if len(recalls) == 2 else None,
            "ece": float(ece), "calibration": bins}


def block_interval(labels, model_p, baseline_p, sessions):
    """Paired baseline-minus-model Brier, resampling whole observation sessions."""
    y, p, b = map(lambda x: np.asarray(x, dtype=float), (labels, model_p, baseline_p))
    scores(y, p)
    scores(y, b)
    s = np.asarray(sessions)
    if s.shape != y.shape:
        raise ValueError("One session per outcome required")
    unique = list(dict.fromkeys(s))
    if len(unique) < 2:
        return None
    difference = (b - y) ** 2 - (p - y) ** 2
    sums = np.array([difference[s == key].sum() for key in unique])
    counts = np.array([(s == key).sum() for key in unique])
    rng = np.random.default_rng(7)
    picks = rng.integers(0, len(unique), size=(500, len(unique)))
    means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    return {"lower": float(np.quantile(means, .025)), "upper": float(np.quantile(means, .975)),
            "method": "paired session bootstrap", "replicates": 500, "seed": 7,
            "sessions": len(unique), "estimate": float(difference.mean())}


def evaluate_history(frame, metadata, *, visible_count=None):
    clean = validated_history(frame, metadata)
    n = len(clean) if visible_count is None else visible_count
    if type(n) is not int or not 1 <= n <= len(clean):
        raise ValueError("Invalid evaluation replay cursor")
    registered = metadata.get("research_partition")
    if registered is not None and registered != research_partition(clean):
        raise ValueError("Registered snapshot changed; research partition cannot move")
    plan = split_plan(clean)
    visible = clean.iloc[:n]
    complete_count = int((visible.session_close <= visible.bar_end.iloc[-1]).sum())
    plan["folds"] = [fold for fold in plan["folds"] if fold["stop"] <= complete_count]
    result = {"schema": VERSION, "dataset_sha256": fingerprint(clean),
              "symbol": metadata["symbol"], "feed": metadata.get("feed", "unspecified"),
              "synthetic": metadata["synthetic"], "plan": plan, "horizons": {},
              "status": INSUFFICIENT, "probabilities_publishable": False,
              "final_holdout_evaluated": False, "hypothesis_horizon_comparisons": 10,
              "model_families": 1, "parameter_searches": 0}
    if not metadata["synthetic"] and (metadata.get("feed") not in ("iex", "sip") or
                                      metadata.get("adjustment") != "split"):
        result["reason"] = "Actual history requires explicit single feed and split-adjustment metadata"
        return result
    if not plan["folds"]:
        return result
    if not metadata["synthetic"] and registered is None:
        result["reason"] = "Immutable snapshot research partition registration required"
        return result
    # Never even build holdout feature vectors or outcomes.
    development = clean.iloc[:min(plan["holdout_start"], complete_count)]
    features = causal_features(development, metadata)
    for horizon in HORIZONS:
        rows = [{"features": r, "outcome": outcome(development, r, horizon)}
                for r in features if r["index"] + horizon < len(development)]
        predictions, fold_reports = [], []
        for fold in plan["folds"]:
            train = [r for r in rows if r["features"]["index"] + horizon < fold["train_label_before"]]
            valid = [r for r in rows if fold["start"] <= r["features"]["index"]
                     and r["features"]["index"] + horizon < fold["stop"]]
            if not train or not valid:
                continue
            model = fit_frequency(train)
            current = []
            for row in valid:
                f = row["features"]
                current.append({"index": f["index"], "session": f["session"], "y": row["outcome"]["up"],
                                "model": predict_frequency(model, f), "unconditional": model["base"],
                                "majority": model["majority"], "persistence": float(f["previous_up"]),
                                "ema_rule": float(f["ema_sign"] > 0), "features": f})
            predictions.extend(current)
            fold_reports.append({**fold, "train_n": len(train), "validation_n": len(valid),
                                 "train_last_outcome_index": max(r["features"]["index"] + horizon for r in train),
                                 "model": scores([r["y"] for r in current], [r["model"] for r in current])})
        if not predictions:
            continue
        y = [r["y"] for r in predictions]
        p = [r["model"] for r in predictions]
        base = [r["unconditional"] for r in predictions]
        sessions = [r["session"] for r in predictions]
        metrics = {key: scores(y, [r[key] for r in predictions])
                   for key in ("model", "unconditional", "majority", "persistence", "ema_rule")}
        interval = block_interval(y, p, base, sessions)
        thresholds = (len(set(sessions)) >= 60 and len(y) >= 1000 and min(sum(y), len(y) - sum(y)) >= 100
                      and interval is not None and interval["lower"] > 0 and metrics["model"]["ece"] <= .05)
        # Hypothesis diagnostics share these SAME OOS predictions; no refitting/tuning.
        predicates = {
            "falling_structure": lambda f: f["structure"] == "falling",
            "ema_down_cross": lambda f: f["ema_down_cross"],
            "sr_break": lambda f: f["event"]["type"] in ("breakout", "breakdown"),
            "high_rvol_sr": lambda f: f["event"]["type"] in ("breakout", "breakdown") and
                                      f["rvol"] is not None and f["rvol"] >= 1.5,
            "combined": lambda f: True,
        }
        groups = {}
        for name, predicate in predicates.items():
            selected = [r for r in predictions if predicate(r["features"])]
            sr_labels = [outcome(development, r["features"], horizon)["sr_outcome"] for r in selected]
            groups[name] = {"n": len(selected), "positive_fraction":
                            sum(r["y"] for r in selected) / len(selected) if selected else None,
                            "unconditional_forecast_mean":
                            sum(r["unconditional"] for r in selected) / len(selected) if selected else None,
                            "sr_outcomes": {label: sr_labels.count(label) for label in
                                            ("continuation", "reversal", "unresolved", "ambiguous", "no_event")}}
        result["horizons"][str(horizon)] = {
            "metrics": metrics, "paired_brier_improvement": interval, "folds": fold_reports,
            "oos_sessions": len(set(sessions)), "diagnostic_thresholds_met": bool(thresholds),
            "hypotheses": groups, "eligible_pre_holdout_records": len(rows),
            "oos_fraction_of_eligible": len(predictions) / len(rows),
        }
    result["status"] = "SYNTHETIC SOFTWARE DIAGNOSTIC" if metadata["synthetic"] else "HISTORICAL DIAGNOSTIC — NOT RELEASED"
    return result
