"""Simulated-array oracles for v2 logistic mechanics; no market-result claims."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from research_workspace.ise_direction_model import compact_features, fit_logistic, predict_score


class ISEDirectionModelTests(unittest.TestCase):
    def test_features_match_manual_past_windows_and_ignore_future(self):
        series = np.arange(536, dtype=float) / 1000
        frame = pd.DataFrame({"ise_try": series})
        actual = compact_features(frame, [100])[0]
        a, b = series[94:99], series[79:99]
        expected = [series[98], series[97], sum(a)/5, sum(b)/20,
                    np.sqrt(sum((b-b.mean())**2)/20)]
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-15)
        changed = frame.copy()
        changed.loc[99:, "ise_try"] = np.nan
        np.testing.assert_array_equal(compact_features(frame, [100]), compact_features(changed, [100]))
        self.assertEqual(compact_features(frame, []).shape, (0, 5))

    def test_invalid_or_reserved_feature_indices_fail(self):
        frame = pd.DataFrame({"ise_try": np.zeros(536)})
        for indices in ([-1], [True], [21], [428], [100.0]):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                compact_features(frame, indices)
        bad = frame.copy()
        bad.loc[98, "ise_try"] = np.inf
        with self.assertRaises(ValueError):
            compact_features(bad, [100])

    def test_intercept_only_fit_matches_binary_frequency(self):
        x = np.zeros((100, 5))
        y = np.r_[np.ones(30), np.zeros(70)]
        model = fit_logistic(x, y, 10)
        self.assertTrue(model["converged"])
        self.assertFalse(model["constant_class"])
        np.testing.assert_allclose(model["coef"], 0, atol=1e-12)
        np.testing.assert_allclose(predict_score(model, x), .3, atol=1e-10)
        self.assertAlmostEqual(model["intercept"], np.log(.3/.7), places=8)

    def test_constant_class_fallback_is_explicit_and_smoothed(self):
        x = np.arange(80).reshape(20, 4)
        for label in (0, 1):
            y = np.full(20, label)
            model = fit_logistic(x, y, 1)
            self.assertTrue(model["constant_class"])
            self.assertEqual(model["iterations"], 0)
            self.assertEqual(model["fit_status"], "smoothed_constant_class")
            expected = (y.sum()+1)/(len(y)+2)
            np.testing.assert_allclose(predict_score(model, x), expected, atol=1e-15)

    def test_fitted_parameters_satisfy_independent_finite_difference_gradient(self):
        rng = np.random.default_rng(27)
        x = rng.normal(size=(140, 5))
        y = (x[:, 0] + rng.normal(size=len(x))*.6 > .2).astype(float)
        model = fit_logistic(x, y, 10)
        design = np.column_stack((np.ones(len(x)), (x-model["mean"])/model["scale"]))
        theta = np.r_[model["intercept"], model["coef"]]
        def loss(value):
            score = design @ value
            # Stable scalar oracle with a separately written regularizer.
            return sum(max(v, 0)+np.log1p(np.exp(-abs(v)))-t*v for v,t in zip(score,y)) + 5*sum(value[1:]**2)
        derivative = []
        for i in range(len(theta)):
            shift = np.zeros(len(theta)); shift[i] = 1e-5
            derivative.append((loss(theta+shift)-loss(theta-shift))/(2e-5))
        np.testing.assert_allclose(derivative, 0, atol=1e-7)
        self.assertTrue(np.all(np.diff(model["objective_history"]) <= 1e-12))

    def test_prediction_uses_training_scaler_without_modifying_it(self):
        rng = np.random.default_rng(3)
        x = rng.normal(size=(100, 5)); y = np.arange(100) % 2
        model = fit_logistic(x, y, 100)
        mean, scale = model["mean"].copy(), model["scale"].copy()
        probe = np.array([[1000, -1000, 0, 1, 3]], dtype=float)
        p = predict_score(model, probe)
        np.testing.assert_array_equal(model["mean"], mean)
        np.testing.assert_array_equal(model["scale"], scale)
        self.assertTrue(np.all((p > 0) & (p < 1)))
        np.testing.assert_allclose(mean, x.mean(axis=0))
        np.testing.assert_allclose(scale, x.std(axis=0, ddof=0))

    def test_invalid_inputs_and_nonconvergence_fail_closed(self):
        x = np.zeros((5, 2)); y = np.array([0,1,0,1,1])
        for a, b, penalty in ((x[:0], y[:0], 1), (x, y[:-1], 1), (x, np.ones(5)*.2, 1),
                               (x, y, 0), (x, y, True), (x, y, np.inf),
                               (np.full((5,2), np.nan), y, 1), (x.astype(complex)+1j, y, 1)):
            with self.subTest(alpha=penalty), self.assertRaises(ValueError):
                fit_logistic(a,b,penalty)
        rng = np.random.default_rng(5)
        with patch("research_workspace.ise_direction_model.MAX_ITERATIONS", 0), self.assertRaisesRegex(ValueError, "NOT_CONVERGED"):
            fit_logistic(rng.normal(size=(10, 2)), np.arange(10)%2, 1)

    def test_fit_is_deterministic_and_prediction_shape_is_checked(self):
        rng = np.random.default_rng(21)
        x = rng.normal(size=(80, 5)); y = (x[:, 1] > 0).astype(float)
        first, second = fit_logistic(x,y,1), fit_logistic(x,y,1)
        np.testing.assert_array_equal(first["coef"], second["coef"])
        np.testing.assert_array_equal(predict_score(first,x), predict_score(second,x))
        self.assertEqual(first["objective_history"], second["objective_history"])
        with self.assertRaises(ValueError):
            predict_score(first,np.zeros((1,4)))
