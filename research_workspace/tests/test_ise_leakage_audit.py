"""Adversarial registration and chronological controls; simulated returns only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from research_workspace.ise_ml import (COLUMNS, SOURCE_URL, evaluate, features, load_csv,
                                     model_specification, validate_registration)
from research_workspace.ise_source import read_snapshot, register_source
from research_workspace.tests.test_ise_source import archive_fixture


class ISELeakageAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(71)
        values = rng.normal(0, .01, (536, 9))
        # An intentionally predictable fixture, not evidence of market skill.
        values[2:, 0] += values[:-2, 2] * .7
        cls.raw = pd.DataFrame(values, columns=COLUMNS[1:])
        cls.raw.insert(0, "date", pd.bdate_range("2009-01-05", periods=536))

    def pack(self, raw=None):
        payload = (self.raw if raw is None else raw).to_csv(index=False).encode()
        return load_csv(payload, {"source_id": "uci247", "license": "CC-BY-4.0",
                                  "source_url": SOURCE_URL,
                                  "csv_sha256": hashlib.sha256(payload).hexdigest()})

    def test_registered_input_cannot_silently_change_regularization(self):
        frame, meta = self.pack()
        with patch("research_workspace.ise_ml.RIDGE_LAMBDA", .01):
            with self.assertRaisesRegex(ValueError, "SPEC|PROTOCOL|REGISTERED"):
                evaluate(frame, meta)

    def test_registered_input_cannot_silently_change_signal_threshold(self):
        frame, meta = self.pack()
        with patch("research_workspace.ise_ml.SIGNAL_THRESHOLD", 0.0):
            with self.assertRaisesRegex(ValueError, "SPEC|PROTOCOL|REGISTERED"):
                evaluate(frame, meta)

    def test_registered_partition_indices_require_exact_integer_types(self):
        frame, meta = self.pack()
        for key, value in (("validation_start", 321.0), ("holdout_start", 428.0)):
            with self.subTest(field=key), self.assertRaises(ValueError):
                evaluate(frame, {**meta, key: value})

    def test_registered_counts_and_execution_flag_cannot_contradict_input(self):
        frame, meta = self.pack()
        for key, value in (("rows", 535), ("rows", 536.0), ("bytes", 0),
                           ("bytes", True), ("bytes", meta["bytes"] + 1),
                           ("orders_enabled", True), ("orders_enabled", 0)):
            with self.subTest(field=key, value=value), self.assertRaises(ValueError):
                evaluate(frame, {**meta, key: value})

    def test_last_purged_observation_does_not_change_first_validation_prediction(self):
        frame, meta = self.pack()
        _, original = evaluate(frame, meta, visible_count=322)
        changed = self.raw.copy()
        # Row 320 is after the train window and after the latest permitted
        # feature observation (319) for validation target 321.
        changed.loc[320:, list(COLUMNS[1:])] *= 50
        other, other_meta = self.pack(changed)
        _, replay = evaluate(other, other_meta, visible_count=322)
        self.assertEqual(original.prediction.iloc[0], replay.prediction.iloc[0])
        self.assertEqual(original.training_end_index.iloc[0], 318)
        self.assertEqual(original.feature_cutoff_index.iloc[0], 319)
        self.assertNotEqual(original.actual_return.iloc[0], replay.actual_return.iloc[0])

    def test_memory_validation_is_read_only_and_requires_current_binding(self):
        frame, meta = self.pack()
        before = frame.copy(deep=True)
        with patch("research_workspace.ise_ml.fit_ridge", side_effect=AssertionError("Validation must not fit")):
            validated = validate_registration(frame, meta)
            pd.testing.assert_frame_equal(validated, before)
            stale = dict(meta)
            del stale["validation_binding_sha256"]
            with self.assertRaises(ValueError):
                validate_registration(frame, stale)
        pd.testing.assert_frame_equal(frame, before)
        report, _ = evaluate(frame, meta, visible_count=321)
        spec = json.dumps(model_specification(), sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(report["model_spec_sha256"], hashlib.sha256(spec).hexdigest())
        self.assertEqual(len(report["experiment_sha256"]), 64)

    def test_training_fit_audit_matches_independent_augmented_least_squares(self):
        frame, meta = self.pack()
        report, _ = evaluate(frame, meta, visible_count=343)
        self.assertEqual([d["validation_rows"] for d in report["fold_fit_diagnostics"]], [20, 2])
        for item in report["fold_fit_diagnostics"]:
            start = 321 + item["fold"] * 20
            train = list(range(22, start - 2))
            targets = list(range(start, min(start + 20, 343)))
            x = features(frame, train)
            mean, scale = x.mean(axis=0), x.std(axis=0)
            scale = np.where(scale > 1e-12, scale, 1.0)
            z = (x - mean) / scale
            y = frame.ise_try.iloc[train].to_numpy()
            w = np.linalg.lstsq(np.vstack((z, np.sqrt(10.) * np.eye(22))),
                                np.r_[y - y.mean(), np.zeros(22)], rcond=None)[0]
            train_pred = z @ w + y.mean()
            val_pred = ((features(frame, targets) - mean) / scale) @ w + y.mean()
            train_rmse = np.sqrt(np.mean((y - train_pred) ** 2))
            val_rmse = np.sqrt(np.mean((frame.ise_try.iloc[targets].to_numpy() - val_pred) ** 2))
            dof = 1 + np.trace(np.linalg.solve(z.T @ z + 10 * np.eye(22), z.T @ z))
            self.assertEqual(item["training_rows"], len(train))
            self.assertEqual(item["training_end_index"], start - 3)
            self.assertEqual(item["feature_count"], 22)
            self.assertAlmostEqual(item["train_rmse"], train_rmse, places=14)
            self.assertAlmostEqual(item["validation_rmse"], val_rmse, places=14)
            self.assertAlmostEqual(item["effective_degrees_of_freedom"], dof, places=11)
            self.assertAlmostEqual(item["coefficient_l2_norm"], np.linalg.norm(w), places=13)
            self.assertAlmostEqual(item["validation_minus_train_rmse"], val_rmse - train_rmse, places=14)
            self.assertAlmostEqual(item["validation_train_rmse_ratio"], val_rmse / train_rmse, places=12)
            self.assertIn("not proof", item["interpretation"])

    def test_fit_gap_audit_excludes_all_later_visible_and_reserved_outcomes(self):
        frame, meta = self.pack()
        original, _ = evaluate(frame, meta, visible_count=350)
        changed = self.raw.copy()
        changed.loc[350:, list(COLUMNS[1:])] *= 40
        other, other_meta = self.pack(changed)
        repeated, _ = evaluate(other, other_meta, visible_count=350)
        self.assertEqual(original["fold_fit_diagnostics"], repeated["fold_fit_diagnostics"])

    def test_source_readback_checks_present_binding_and_preserves_legacy_snapshot(self):
        source = archive_fixture()
        pin = hashlib.sha256(source).hexdigest()
        with tempfile.TemporaryDirectory() as tmp, \
             patch("research_workspace.ise_source.PINNED_RAW_SHA256", pin):
            folder = Path(tmp) / "snapshot"
            original = register_source(source, folder)
            path = folder / "manifest.json"
            for value in ("0" * 64, 0):
                with self.subTest(binding=value), self.assertRaisesRegex(ValueError, "REGISTERED_INPUT_CHANGED"):
                    changed = {**original, "validation_binding_sha256": value}
                    path.write_text(json.dumps(changed), encoding="utf-8")
                    read_snapshot(folder)
            legacy = dict(original)
            del legacy["validation_binding_sha256"]
            path.write_text(json.dumps(legacy), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            frame, enriched = read_snapshot(folder)
            self.assertEqual(enriched["validation_binding_sha256"], original["validation_binding_sha256"])
            validate_registration(frame, enriched)
            self.assertEqual(before, {p.name: p.read_bytes() for p in folder.iterdir()})
