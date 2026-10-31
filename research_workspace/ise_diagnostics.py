"""Post-hoc descriptions of already-scored ISE validation rows; never refits."""
import json

import numpy as np
import pandas as pd

from research_workspace.ise_ml import HOLDOUT_START, SIGNAL_THRESHOLD, VALIDATION_START

SIGNALS = ("LONG", "WATCH", "CASH")
REQUIRED = ("date", "origin_index", "actual_return", "prediction", "baseline_mean", "signal", "model_fold")


def _validated(curve):
    if not isinstance(curve, pd.DataFrame) or not set(REQUIRED).issubset(curve.columns):
        raise ValueError("ISE_DIAGNOSTIC_SCHEMA")
    rows = curve[list(REQUIRED)].copy()
    if rows.empty:
        return rows
    for name in ("origin_index", "model_fold"):
        if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, (int, np.integer)) for v in rows[name]):
            raise ValueError("ISE_DIAGNOSTIC_INDEX")
    indices = rows.origin_index.to_numpy()
    if (indices[0] != VALIDATION_START or indices[-1] >= HOLDOUT_START or
            not np.array_equal(indices, np.arange(VALIDATION_START, VALIDATION_START + len(rows)))):
        raise ValueError("ISE_DIAGNOSTIC_RESERVED_OR_NONPREFIX")
    if not np.array_equal(rows.model_fold.to_numpy(), (indices - VALIDATION_START) // 20):
        raise ValueError("ISE_DIAGNOSTIC_FOLD")
    dates = pd.to_datetime(rows.date, errors="raise")
    if (dates.dt.tz is not None or dates.isna().any() or dates.duplicated().any() or
            not dates.is_monotonic_increasing or (dates != dates.dt.normalize()).any() or
            (dates < pd.Timestamp("2009-01-01")).any() or (dates > pd.Timestamp("2011-12-31")).any()):
        raise ValueError("ISE_DIAGNOSTIC_DATES")
    rows["date"] = dates
    for name in ("actual_return", "prediction", "baseline_mean"):
        if not pd.api.types.is_numeric_dtype(rows[name]) or pd.api.types.is_bool_dtype(rows[name]):
            raise ValueError("ISE_DIAGNOSTIC_NUMERICS")
        rows[name] = rows[name].astype(float)
    if not np.isfinite(rows[["actual_return", "prediction", "baseline_mean"]].to_numpy()).all():
        raise ValueError("ISE_DIAGNOSTIC_NONFINITE")
    expected = np.where(rows.prediction > SIGNAL_THRESHOLD, "LONG", np.where(rows.prediction <= 0, "CASH", "WATCH"))
    if not np.array_equal(rows.signal.to_numpy(), expected):
        raise ValueError("ISE_DIAGNOSTIC_SIGNAL")
    return rows


def _confusion(actual, predicted):
    up, called_up = actual > 0, predicted > 0
    tp = int(np.count_nonzero(up & called_up))
    fp = int(np.count_nonzero(~up & called_up))
    fn = int(np.count_nonzero(up & ~called_up))
    tn = int(np.count_nonzero(~up & ~called_up))
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "positive_actual": tp + fn, "nonpositive_actual": tn + fp,
            "directional_accuracy": float((tp + tn) / len(actual)),
            "balanced_accuracy": .5 * (tp / (tp + fn) + tn / (tn + fp)) if tp + fn and tn + fp else None}


def _metrics(rows):
    actual, predicted, baseline = (rows[name].to_numpy() for name in ("actual_return", "prediction", "baseline_mean"))
    with np.errstate(over="ignore", invalid="ignore"):
        mse = float(np.mean((actual - predicted) ** 2))
        baseline_mse = float(np.mean((actual - baseline) ** 2))
    if not np.isfinite(mse) or not np.isfinite(baseline_mse):
        raise ValueError("ISE_DIAGNOSTIC_NONFINITE")
    return {"count": len(rows), "rmse": float(np.sqrt(mse)), "baseline_mean_rmse": float(np.sqrt(baseline_mse)),
            "mse_improvement_vs_train_mean": baseline_mse - mse,
            **_confusion(actual, predicted)}


def diagnostics(curve):
    """Describe visible validation only; empirical rates are not forecasts or P&L."""
    flags = {"post_hoc_descriptive": True, "parameter_search": False, "model_refitted": False,
             "validated_trading_signal": False, "calibrated_probability": False,
             "pnl_computed": False, "holdout_read": False, "orders_enabled": False}
    if isinstance(curve, pd.DataFrame) and curve.empty:
        return {**flags, "status": "INSUFFICIENT_VISIBLE_VALIDATION", "count": 0,
                "folds": [], "signals": [], "confusion": None, "overall": None,
                "commentary": ["Görünür doğrulama sonucu bulunmadığı için başarı veya sinyal güvenilirliği hesaplanmadı."]}
    rows = _validated(curve)
    overall = _metrics(rows)
    folds = []
    for fold, part in rows.groupby("model_fold", sort=True):
        folds.append({"fold": int(fold), "first_date": part.date.iloc[0].date().isoformat(),
                      "last_date": part.date.iloc[-1].date().isoformat(), **_metrics(part)})
    groups = []
    for signal in SIGNALS:
        part = rows.loc[rows.signal == signal]
        n = len(part)
        groups.append({"signal": signal, "count": n,
                       "actual_mean_source_units": float(part.actual_return.mean()) if n else None,
                       "empirical_positive_share": float((part.actual_return > 0).mean()) if n else None,
                       "calibrated_forecast_probability": False,
                       "sample_note": "Gözlem yok; sonuç hesaplanmadı." if not n else
                                      f"Betimsel {n} gözlem; küçük gruplar kararlı çıkarım sağlamaz. "
                                      "Gözlem sayısı bir model kabul eşiği değildir."})
    better = sum(f["mse_improvement_vs_train_mean"] > 0 for f in folds)
    worse = sum(f["mse_improvement_vs_train_mean"] < 0 for f in folds)
    comparison = "daha düşük" if overall["rmse"] < overall["baseline_mean_rmse"] else (
        "daha yüksek" if overall["rmse"] > overall["baseline_mean_rmse"] else "eşit")
    balanced = overall["balanced_accuracy"]
    commentary = [
        f"Görünür {len(rows)} tarihsel doğrulama gözleminde modelin RMSE değeri "
        f"{overall['rmse']:.6f}; eğitim ortalaması referansından {comparison}. "
        f"{len(folds)} pencerenin {better} tanesinde hata azaldı, {worse} tanesinde arttı.",
        f"Yön doğruluğu %{100 * overall['directional_accuracy']:.1f}. " + (
            f"Sınıfları eşit ağırlıklandıran dengeli doğruluk %{100 * balanced:.1f}; "
            "tek başına yüksek yön doğruluğu üstünlük veya güvenilir sinyal kanıtı değildir." if balanced is not None else
            "Bu kesitte iki sonuç sınıfı birlikte bulunmadığı için dengeli doğruluk hesaplanamadı."),
        "Sinyal gruplarındaki pozitif gerçekleşme oranları yalnızca geriye dönük betimlemedir; "
        "kalibre tahmin olasılığı, kâr/zarar hesabı veya emir önerisi değildir. Küçük gruplar güçlü çıkarım desteklemez."]
    result = {**flags, "status": "POST_HOC_VALIDATION_DESCRIPTION", "count": len(rows), "folds": folds,
              "signals": groups, "confusion": {k: overall[k] for k in ("tp", "fp", "fn", "tn")},
              "overall": overall, "commentary": commentary}
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except ValueError:
        raise ValueError("ISE_DIAGNOSTIC_NONFINITE") from None
    return result
