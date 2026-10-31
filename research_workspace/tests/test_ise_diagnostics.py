"""Independent post-hoc reconciliation cases; simulated returns, no market claim."""
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research_workspace.ise_diagnostics import diagnostics


def fixture(actual, predicted, baseline=None):
    n = len(actual)
    predicted = np.asarray(predicted, dtype=float)
    indices = np.arange(321, 321 + n)
    return pd.DataFrame({"date": pd.bdate_range("2010-04-01", periods=n), "origin_index": indices,
                         "actual_return": np.asarray(actual, dtype=float), "prediction": predicted,
                         "baseline_mean": np.zeros(n) if baseline is None else baseline,
                         "signal": np.where(predicted > .005, "LONG", np.where(predicted <= 0, "CASH", "WATCH")),
                         "model_fold": (indices - 321) // 20})


class ISEDiagnosticsTests(unittest.TestCase):
    def test_fold_and_signal_counts_and_squared_errors_reconcile(self):
        actual = np.r_[np.repeat(.01, 15), np.repeat(-.02, 10)]
        predicted = np.r_[np.repeat(.006, 5), np.repeat(.002, 5), np.repeat(-.01, 15)]
        result = diagnostics(fixture(actual, predicted))
        self.assertEqual([f["count"] for f in result["folds"]], [20, 5])
        self.assertEqual(sum(f["count"] for f in result["folds"]), result["count"])
        self.assertEqual(sum(s["count"] for s in result["signals"]), result["count"])
        weighted_mse = sum(f["rmse"] ** 2 * f["count"] for f in result["folds"]) / result["count"]
        self.assertAlmostEqual(weighted_mse, np.mean((actual - predicted) ** 2), places=15)
        self.assertAlmostEqual(result["overall"]["rmse"], np.sqrt(weighted_mse), places=15)
        self.assertEqual(result["confusion"], {"tp": 10, "fp": 0, "fn": 5, "tn": 10})
        self.assertEqual(sum(result["confusion"].values()), 25)

    def test_high_accuracy_from_class_imbalance_is_not_called_signal_validation(self):
        result = diagnostics(fixture([.01] * 9 + [-.01], [.01] * 10))
        self.assertEqual(result["overall"]["directional_accuracy"], .9)
        self.assertEqual(result["overall"]["balanced_accuracy"], .5)
        self.assertFalse(result["validated_trading_signal"])
        self.assertTrue(any("tek başına yüksek yön doğruluğu" in text for text in result["commentary"]))
        self.assertEqual(result["confusion"], {"tp": 9, "fp": 1, "fn": 0, "tn": 0})

    def test_small_and_absent_groups_have_explicit_weak_or_unavailable_evidence(self):
        result = diagnostics(fixture([.01, -.02, .03, -.04], [-.01] * 4))
        groups = {row["signal"]: row for row in result["signals"]}
        self.assertEqual(groups["CASH"]["count"], 4)
        self.assertEqual(groups["CASH"]["empirical_positive_share"], .5)
        self.assertIn("küçük gruplar", groups["CASH"]["sample_note"])
        self.assertIsNone(groups["LONG"]["empirical_positive_share"])
        self.assertIsNone(groups["LONG"]["actual_mean_source_units"])
        self.assertFalse(groups["CASH"]["calibrated_forecast_probability"])

    def test_reserved_nonprefix_or_malformed_rows_are_rejected(self):
        clean = fixture([.01, -.01], [.01, -.01])
        changes = (("origin_index", [320, 321]), ("origin_index", [427, 428]),
                   ("origin_index", [321, 323]), ("model_fold", [1, 1]),
                   ("date", pd.to_datetime(["2026-10-25", "2026-10-26"])),
                   ("actual_return", [np.nan, .01]), ("prediction", [np.inf, .01]),
                   ("signal", ["CASH", "CASH"]))
        for field, value in changes:
            with self.subTest(field=field, value=str(value)), self.assertRaises(ValueError):
                rows = clean.copy()
                rows[field] = value
                diagnostics(rows)

    def test_empty_results_are_unavailable_and_ties_are_nonpositive(self):
        empty = diagnostics(pd.DataFrame())
        self.assertIsNone(empty["overall"])
        self.assertIsNone(empty["confusion"])
        self.assertEqual(empty["status"], "INSUFFICIENT_VISIBLE_VALIDATION")
        result = diagnostics(fixture([0.0] * 5, [0.0] * 5))
        self.assertEqual(result["confusion"], {"tp": 0, "fp": 0, "fn": 0, "tn": 5})
        self.assertIsNone(result["overall"]["balanced_accuracy"])

    def test_diagnostics_are_read_only_and_do_not_refit_models(self):
        rows = fixture([.01, -.01, .02, -.02], [.006, -.002, .003, -.004])
        before = rows.copy(deep=True)
        with patch("research_workspace.ise_ml.fit_ridge", side_effect=AssertionError("No refitting")), \
             patch("research_workspace.ise_ml.evaluate", side_effect=AssertionError("No reevaluation")):
            report = diagnostics(rows)
        pd.testing.assert_frame_equal(rows, before)
        self.assertTrue(report["post_hoc_descriptive"])
        self.assertFalse(report["parameter_search"])
        self.assertFalse(report["holdout_read"])
        json.dumps(report, allow_nan=False)

    def test_finite_inputs_that_overflow_statistics_fail_closed(self):
        rows = fixture([1e300, -1e300], [-1e300, 1e300])
        with self.assertRaisesRegex(ValueError, "NONFINITE"):
            diagnostics(rows)
