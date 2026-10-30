"""Causal model mechanics use explicitly simulated returns, not market results."""
import hashlib
import json
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research_workspace.ise_ml import (COLUMNS, FEATURE_NAMES, HOLDOUT_START, VALIDATION_START, SOURCE_URL,
                                     evaluate, features, fit_ridge, load_csv)


class ISEMLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(11)
        vals = rng.normal(0, .01, size=(536, 9))
        vals[2:, 0] += vals[:-2, 2] * .3
        cls.raw = pd.DataFrame(vals, columns=COLUMNS[1:])
        cls.raw.insert(0, "date", pd.bdate_range("2009-01-05", periods=536))

    def pack(self, raw=None):
        payload = (self.raw if raw is None else raw).to_csv(index=False).encode()
        return load_csv(payload, {"source_id": "uci247", "license": "CC-BY-4.0",
                                  "source_url": SOURCE_URL,
                                  "csv_sha256": hashlib.sha256(payload).hexdigest()})

    def test_source_bytes_and_manifest_fields_are_bound(self):
        frame, meta = self.pack()
        for key, value in (("source_id", "other"), ("csv_sha256", "0" * 64),
                           ("canonical_sha256", "0" * 64), ("holdout_start", 429)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                evaluate(frame, {**meta, key: value})
        payload = self.raw.to_csv(index=False).encode()
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            load_csv(payload + b"\n", {"source_id": "uci247", "license": "CC-BY-4.0",
                                       "source_url": SOURCE_URL,
                                       "csv_sha256": hashlib.sha256(payload).hexdigest()})

    def test_features_have_independent_lag_and_window_oracle(self):
        frame, _ = self.pack()
        t = 100
        got = features(frame, [t])[0]
        expected = [*frame.loc[t - 2, list(COLUMNS[1:])], *frame.loc[t - 3, list(COLUMNS[1:])]]
        for window in (5, 20):
            values = frame.ise_try.iloc[t - window - 1:t - 1].to_numpy()
            expected.extend((sum(values) / window, np.sqrt(sum((values - values.mean()) ** 2) / window)))
        np.testing.assert_allclose(got, expected, rtol=1e-12, atol=1e-14)
        self.assertEqual(len(got), len(FEATURE_NAMES))
        changed = frame.copy()
        changed.loc[t - 1:, COLUMNS[1:]] = 100.0
        np.testing.assert_array_equal(features(frame, [t]), features(changed, [t]))

    def test_ridge_matches_centered_independent_normal_equations(self):
        rng = np.random.default_rng(9)
        x = rng.normal(size=(100, 22))
        x[:, -1] = 1.0
        y = rng.normal(size=100)
        mean, scale, weights, intercept = fit_ridge(x, y)
        z = (x - x.mean(axis=0)) / np.where(x.std(axis=0) > 1e-12, x.std(axis=0), 1)
        # Augmented least squares is independent of the production linear solve.
        design = np.vstack((z, np.sqrt(10.0) * np.eye(22)))
        target = np.r_[y - y.mean(), np.zeros(22)]
        oracle = np.linalg.lstsq(design, target, rcond=None)[0]
        np.testing.assert_allclose(weights, oracle, rtol=1e-10, atol=1e-12)
        self.assertEqual(intercept, y.mean())
        self.assertEqual(scale[-1], 1.0)

    def test_holdout_suffix_changes_cannot_affect_validation(self):
        frame, meta = self.pack()
        summary, curve = evaluate(frame, meta)
        changed = self.raw.copy()
        changed.loc[HOLDOUT_START:, COLUMNS[1:]] = 50.0
        other, other_meta = self.pack(changed)
        report2, curve2 = evaluate(other, other_meta)
        pd.testing.assert_frame_equal(curve, curve2)
        self.assertEqual(summary["metrics"], report2["metrics"])
        self.assertEqual(curve.origin_index.max(), HOLDOUT_START - 1)
        self.assertFalse(summary["holdout_scored"])

    def test_future_validation_changes_preserve_earlier_predictions(self):
        frame, meta = self.pack()
        _, first = evaluate(frame, meta)
        changed = self.raw.copy()
        changed.loc[370:, COLUMNS[1:]] *= 15
        other, other_meta = self.pack(changed)
        _, second = evaluate(other, other_meta)
        pd.testing.assert_frame_equal(first.loc[first.origin_index < 370].reset_index(drop=True),
                                      second.loc[second.origin_index < 370].reset_index(drop=True))
        # Changing the target and contemporaneous foreign returns cannot change
        # that observation's prediction either; only its realized error changes.
        a = first.loc[first.origin_index == 370].iloc[0]
        b = second.loc[second.origin_index == 370].iloc[0]
        self.assertEqual(a.prediction, b.prediction)
        self.assertNotEqual(a.actual_return, b.actual_return)

    def test_training_and_standardization_never_include_target_or_feature_cutoff(self):
        frame, meta = self.pack()
        calls = []
        original = fit_ridge

        def record(x, y):
            calls.append((x.copy(), y.copy()))
            return original(x, y)

        with patch("research_workspace.ise_ml.fit_ridge", side_effect=record):
            _, curve = evaluate(frame, meta)
        self.assertEqual(len(calls), 6)
        for fold, (x, y) in enumerate(calls):
            start = VALIDATION_START + fold * 20
            self.assertEqual(len(x), start - 2 - 22)
            np.testing.assert_array_equal(y, frame.ise_try.iloc[22:start - 2])
        self.assertTrue((curve.training_end_index < curve.feature_cutoff_index).all())

    def test_replay_only_emits_visible_validation_and_is_deterministic(self):
        frame, meta = self.pack()
        empty, rows = evaluate(frame, meta, visible_count=VALIDATION_START)
        self.assertEqual(empty["evaluated_rows"], 0)
        self.assertTrue(rows.empty)
        report, visible = evaluate(frame, meta, visible_count=350)
        self.assertEqual(len(visible), 29)
        self.assertLess(visible.origin_index.max(), 350)
        again, repeated = evaluate(frame, meta, visible_count=350)
        self.assertEqual(report, again)
        pd.testing.assert_frame_equal(visible, repeated)
        self.assertEqual(len(evaluate(frame, meta, visible_count=536)[1]), 107)
        json.dumps(report, allow_nan=False)

    def test_reserved_or_sealed_dates_rejected_before_invalid_numbers(self):
        for value, message in (("2025-01-02", "RESERVED_PERIOD"), ("2026-10-26", "SEALED_PERIOD")):
            raw = self.raw.copy().astype({"date": str, "ise_try": str})
            raw.loc[535, "date"] = value
            raw.loc[535, "ise_try"] = "not numeric"
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, message):
                self.pack(raw)

    def test_nonfinite_inputs_and_visible_indices_rejected(self):
        raw = self.raw.copy()
        raw.loc[100, "sp"] = np.inf
        with self.assertRaisesRegex(ValueError, "INVALID_NUMERICS"):
            self.pack(raw)
        frame, meta = self.pack()
        for count in (-1, True, 537, 3.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                evaluate(frame, meta, visible_count=count)
        for index in (-1, True, 428):
            with self.subTest(index=index), self.assertRaises(ValueError):
                features(frame, [index])
