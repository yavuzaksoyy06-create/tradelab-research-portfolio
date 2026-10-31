"""Nested-selection oracles and leakage tests use simulated returns only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from research_workspace.tests import test_ise_ml as fixtures
from research_workspace import ise_direction_v2 as v2
from research_workspace.ise_direction_model import fit_logistic


class DirectionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ISEMLTests.setUpClass()
        cls.fixture = fixtures.ISEMLTests()

    def pack(self, raw=None):
        return self.fixture.pack(raw)

    def test_selection_ties_and_exact_decision_boundary(self):
        self.assertEqual(v2.choose_alpha([{"alpha": a, "pooled_inner_brier": .25} for a in (1., 10., 100.)]), 100.)
        alpha = v2.choose_alpha([{"alpha": 1., "pooled_inner_brier": .1}, {"alpha": 100., "pooled_inner_brier": .2}])
        self.assertEqual(alpha, 1.)
        threshold, rows = v2.choose_threshold(np.array([0, 1]), np.array([.5, .5]), [.4, .5, .6])
        self.assertEqual(threshold, .5)
        self.assertEqual(rows[1]["balanced_accuracy"], .5)
        threshold, _ = v2.choose_threshold(np.ones(4), np.array([.4, .5, .6, .7]), [.4, .5, .6])
        self.assertEqual(threshold, .5)

    def test_metrics_have_independent_brier_logloss_and_class_oracle(self):
        y, p = np.array([0, 1, 0, 1]), np.array([.1, .9, .6, .6])
        got = v2.score_metrics(y, p, p > .5, score_kind="test_only")
        self.assertAlmostEqual(got["brier"], (.01 + .01 + .36 + .16) / 4)
        self.assertAlmostEqual(got["logloss"], -(np.log(.9) + np.log(.9) + np.log(.4) + np.log(.6)) / 4)
        self.assertEqual(got["balanced_accuracy"], .75)
        self.assertEqual(sum(b["count"] for b in got["calibration_bins"]), 4)
        self.assertFalse(got["calibrated_probability"])
        with self.assertRaises(ValueError):
            v2.direction_metrics([0, np.nan], [0, 1])

    def test_inner_scalers_and_labels_use_only_each_training_subset(self):
        frame, _ = self.pack()
        calls = []
        def record(x, y, alpha):
            result = fit_logistic(x, y, alpha)
            np.testing.assert_allclose(result["mean"], x.mean(axis=0), atol=0)
            calls.append((x.copy(), y.copy(), alpha))
            return result
        with patch.object(v2, "fit_logistic", side_effect=record):
            _, _, trace = v2.select_inner(frame, 321, v2.experiment_specification())
        self.assertEqual(len(calls), 9)
        for i, (x, y, _) in enumerate(calls):
            start = (169, 219, 269)[i % 3]
            self.assertEqual(len(x), start - 2 - 22)
            np.testing.assert_array_equal(y, (frame.ise_try.iloc[22:start - 2] > 0).astype(float))
        self.assertEqual(trace["eligible_training_end_exclusive"], 319)
        self.assertEqual(trace["alpha_candidates"][0]["pooled_inner_rows"], 150)

    def test_current_and_future_outer_labels_cannot_select_current_settings(self):
        frame, _ = self.pack()
        first = v2.select_inner(frame, 321, v2.experiment_specification())
        changed = frame.copy()
        changed.loc[319:, "ise_try"] = 100.
        second = v2.select_inner(changed, 321, v2.experiment_specification())
        self.assertEqual(first, second)

    def test_reserved_suffix_and_future_target_do_not_change_prior_predictions(self):
        frame, meta = self.pack()
        summary, curve = v2.evaluate_v2(frame, meta)
        changed = self.fixture.raw.copy()
        changed.loc[428:, "ise_try"] = 100.
        other, other_meta = self.pack(changed)
        again, again_curve = v2.evaluate_v2(other, other_meta)
        pd.testing.assert_frame_equal(curve, again_curve)
        self.assertEqual(summary["metrics"], again["metrics"])
        changed = self.fixture.raw.copy()
        changed.loc[350:, "ise_try"] *= -15
        other, other_meta = self.pack(changed)
        _, later = v2.evaluate_v2(other, other_meta)
        columns = [c for c in curve.columns if c != "actual_up"]
        pd.testing.assert_frame_equal(curve.loc[curve.origin_index <= 350, columns].reset_index(drop=True),
                                      later.loc[later.origin_index <= 350, columns].reset_index(drop=True))

    def test_replay_is_deterministic_and_old_ridge_is_direction_only(self):
        frame, meta = self.pack()
        before = frame.copy(deep=True)
        empty, rows = v2.evaluate_v2(frame, meta, visible_count=321)
        self.assertTrue(rows.empty)
        self.assertEqual(empty["evaluated_rows"], 0)
        report, curve = v2.evaluate_v2(frame, meta, visible_count=350)
        second, repeated = v2.evaluate_v2(frame, meta, visible_count=350)
        self.assertEqual(report, second)
        pd.testing.assert_frame_equal(curve, repeated)
        pd.testing.assert_frame_equal(frame, before)
        self.assertEqual(len(curve), 29)
        self.assertLess(curve.origin_index.max(), 350)
        self.assertIsNone(report["metrics"]["v1_ridge_sign"]["brier"])
        self.assertFalse(report["fresh_independent_test"])
        self.assertFalse(report["holdout_scored"])
        json.dumps(report, allow_nan=False)

    def test_specification_mutation_and_invalid_indices_fail_closed(self):
        spec = v2.experiment_specification()
        spec["alpha_grid"] = [0.01]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "changed.json"
            path.write_text(json.dumps(spec), encoding="utf-8")
            with patch.object(v2, "_SPEC_PATH", path), self.assertRaisesRegex(ValueError, "SPEC_CHANGED"):
                v2.experiment_specification()
        frame, meta = self.pack()
        for count in (-1, True, 537, 3.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                v2.evaluate_v2(frame, meta, visible_count=count)
        for start in (True, 320, 428):
            with self.subTest(start=start), self.assertRaises(ValueError):
                v2.select_inner(frame, start, v2.experiment_specification())
        with patch.object(v2.model_core, "MAX_ITERATIONS", 99), self.assertRaisesRegex(ValueError, "SPEC_CHANGED"):
            v2.evaluate_v2(frame, meta)

    def test_one_class_and_nonconvergence_are_explicit(self):
        raw = self.fixture.raw.copy()
        raw.ise_try = .01
        frame, meta = self.pack(raw)
        report, curve = v2.evaluate_v2(frame, meta, visible_count=325)
        self.assertTrue(report["fold_fit_diagnostics"][0]["constant_class"])
        self.assertEqual(report["selection_trace"][0]["selected_alpha"], 100.)
        self.assertEqual(report["selection_trace"][0]["selected_threshold"], .5)
        self.assertTrue(np.isfinite(curve.score).all())
        with patch.object(v2, "fit_logistic", return_value={"converged": False}), self.assertRaisesRegex(ValueError, "NOT_CONVERGED"):
            v2.evaluate_v2(frame, meta)
