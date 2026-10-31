"""Small L2 logistic model for the separate, registered ISE direction experiment.

The returned scores are uncalibrated model estimates, not trading probabilities.
This module does not select parameters, read files, fit reserved rows or send orders.
"""
import numpy as np
import pandas as pd

FEATURE_NAMES = ("ise_try_lag2", "ise_try_lag3", "ise_try_prior5_mean",
                 "ise_try_prior20_mean", "ise_try_prior20_std")
MAX_ITERATIONS = 100
GRADIENT_TOLERANCE = 1e-8
MAX_BACKTRACKING = 32
SCORE_EPSILON = 1e-12
ARMIJO_CONSTANT = 1e-4


def compact_features(frame, indices):
    """Five target-history features, each ending no later than row t-2."""
    if (not isinstance(frame, pd.DataFrame) or
            list(frame.columns).count("ise_try") != 1):
        raise ValueError("ISE_V2_FEATURE_SCHEMA")
    try:
        selected = list(indices)
    except TypeError:
        raise ValueError("ISE_V2_FEATURE_INDEX") from None
    if any(type(t) is not int or not 22 <= t < 428 or t >= len(frame) for t in selected):
        raise ValueError("ISE_V2_FEATURE_INDEX")
    if not selected:
        return np.empty((0, len(FEATURE_NAMES)), dtype=float)
    # Even the conversion excludes the reserved suffix and the latest targets.
    raw = frame["ise_try"].iloc[:max(selected) - 1].to_numpy()
    if np.iscomplexobj(raw):
        raise ValueError("ISE_V2_FEATURE_NUMERICS")
    try:
        values = np.asarray(raw, dtype=float)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("ISE_V2_FEATURE_NUMERICS") from None
    rows = []
    with np.errstate(over="ignore", invalid="ignore"):
        for t in selected:
            prior5, prior20 = values[t - 6:t - 1], values[t - 21:t - 1]
            rows.append([values[t - 2], values[t - 3], prior5.mean(), prior20.mean(), prior20.std(ddof=0)])
    result = np.asarray(rows, dtype=float)
    if not np.isfinite(result).all():
        raise ValueError("ISE_V2_FEATURE_NUMERICS")
    return result


def _array(value, *, dimensions):
    raw = np.asarray(value)
    if np.iscomplexobj(raw):
        raise ValueError("ISE_V2_MODEL_INPUT")
    try:
        out = np.asarray(raw, dtype=float)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("ISE_V2_MODEL_INPUT") from None
    if out.ndim != dimensions or not np.isfinite(out).all():
        raise ValueError("ISE_V2_MODEL_INPUT")
    return out


def _sigmoid(values):
    out = np.empty_like(values, dtype=float)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp = np.exp(values[~positive])
    out[~positive] = exp / (1.0 + exp)
    return out


def _objective(design, y, theta, alpha):
    with np.errstate(over="ignore", invalid="ignore"):
        logits = design @ theta
        loss = np.sum(np.logaddexp(0.0, logits) - y * logits)
        loss += .5 * alpha * np.dot(theta[1:], theta[1:])
    if not np.isfinite(logits).all() or not np.isfinite(loss):
        return float("inf")
    return float(loss)


def predict_score(model, x):
    """Apply the training scaler and coefficients; no fitting or calibration."""
    values = _array(x, dimensions=2)
    mean = _array(model["mean"], dimensions=1)
    scale = _array(model["scale"], dimensions=1)
    coef = _array(model["coef"], dimensions=1)
    if (not len(mean) or mean.shape != scale.shape or mean.shape != coef.shape or
            values.shape[1] != len(mean) or (scale <= 0).any()):
        raise ValueError("ISE_V2_MODEL_SHAPE")
    intercept = float(model["intercept"])
    with np.errstate(over="ignore", invalid="ignore"):
        logits = ((values - mean) / scale) @ coef + intercept
    if not np.isfinite(intercept) or not np.isfinite(logits).all():
        raise ValueError("ISE_V2_MODEL_CALCULATION")
    return np.clip(_sigmoid(logits), SCORE_EPSILON, 1.0 - SCORE_EPSILON)


def fit_logistic(x, y, alpha):
    """Minimize SUM binary NLL + alpha/2 ||coef||²; intercept is unpenalized."""
    values, labels = _array(x, dimensions=2), _array(y, dimensions=1)
    if (not len(values) or values.shape[1] == 0 or len(labels) != len(values) or
            not np.isin(labels, (0.0, 1.0)).all() or isinstance(alpha, (bool, np.bool_))):
        raise ValueError("ISE_V2_MODEL_INPUT")
    try:
        penalty = float(alpha)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("ISE_V2_MODEL_INPUT") from None
    if not np.isfinite(penalty) or penalty <= 0:
        raise ValueError("ISE_V2_MODEL_INPUT")
    with np.errstate(over="ignore", invalid="ignore"):
        mean, scale = values.mean(axis=0), values.std(axis=0, ddof=0)
    if not np.isfinite(mean).all() or not np.isfinite(scale).all():
        raise ValueError("ISE_V2_MODEL_CALCULATION")
    scale = np.where(scale > 1e-12, scale, 1.0)
    z = (values - mean) / scale
    if not np.isfinite(z).all():
        raise ValueError("ISE_V2_MODEL_CALCULATION")
    design = np.column_stack((np.ones(len(z)), z))
    prior = float((labels.sum() + 1.0) / (len(labels) + 2.0))
    theta = np.r_[np.log(prior / (1.0 - prior)), np.zeros(values.shape[1])]
    constant = bool(np.all(labels == labels[0]))
    objective = _objective(design, labels, theta, penalty)
    history = [objective]
    iterations, converged = 0, constant
    penalized = np.r_[0.0, np.full(values.shape[1], penalty)]
    if not constant:
        for iteration in range(MAX_ITERATIONS + 1):
            scores = _sigmoid(design @ theta)
            gradient = design.T @ (scores - labels) + penalized * theta
            if not np.isfinite(gradient).all():
                raise ValueError("ISE_V2_MODEL_CALCULATION")
            if np.max(np.abs(gradient)) <= GRADIENT_TOLERANCE:
                iterations, converged = iteration, True
                break
            if iteration == MAX_ITERATIONS:
                break
            curvature = scores * (1.0 - scores)
            hessian = design.T @ (curvature[:, None] * design) + np.diag(penalized)
            try:
                direction = np.linalg.solve(hessian, gradient)
            except np.linalg.LinAlgError:
                raise ValueError("ISE_V2_MODEL_CALCULATION") from None
            descent = float(gradient @ direction)
            if not np.isfinite(direction).all() or not np.isfinite(descent) or descent <= 0:
                raise ValueError("ISE_V2_MODEL_CALCULATION")
            step, accepted = 1.0, False
            for _ in range(MAX_BACKTRACKING):
                candidate = theta - step * direction
                new_objective = _objective(design, labels, candidate, penalty)
                # Near the optimum, a valid Newton improvement can be smaller
                # than one objective ULP. Accept that endpoint only if the
                # registered first-order tolerance is actually satisfied.
                candidate_gradient = design.T @ (_sigmoid(design @ candidate) - labels) + penalized * candidate
                roundoff = 8 * np.finfo(float).eps * max(1.0, abs(objective))
                converged_endpoint = (np.isfinite(candidate_gradient).all() and
                                      np.max(np.abs(candidate_gradient)) <= GRADIENT_TOLERANCE and
                                      new_objective <= objective + roundoff)
                if new_objective <= objective - ARMIJO_CONSTANT * step * descent or converged_endpoint:
                    theta, objective, accepted = candidate, new_objective, True
                    history.append(objective)
                    break
                step *= .5
            if not accepted:
                raise ValueError("ISE_V2_SOLVER_NOT_CONVERGED")
        if not converged:
            raise ValueError("ISE_V2_SOLVER_NOT_CONVERGED")
    model = {"mean": mean.copy(), "scale": scale.copy(), "coef": theta[1:].copy(),
             "intercept": float(theta[0]), "iterations": iterations, "converged": converged,
             "constant_class": constant, "fit_status": "smoothed_constant_class" if constant else "newton_converged",
             "objective_history": history}
    scores = predict_score(model, values)
    model["train_brier"] = float(np.mean((labels - scores) ** 2))
    logits = design @ theta
    model["train_logloss"] = float(np.mean(np.logaddexp(0.0, logits) - labels * logits))
    if not np.isfinite(model["train_brier"]) or not np.isfinite(model["train_logloss"]):
        raise ValueError("ISE_V2_MODEL_CALCULATION")
    return model
