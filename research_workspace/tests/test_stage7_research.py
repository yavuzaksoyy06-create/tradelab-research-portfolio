"""Offline contracts: synthetic software tests are never market-performance evidence."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd

from research_sr_v4.data import expected_grid
from research_workspace.equity_data import synthetic_fixture, REQUIRED
from research_workspace.equity_provider import read_alpaca_history
from research_workspace.stage7_events import (
    event_dataset, safe_summary, outcome, classify_event, validated_history, causal_features,
)
from research_workspace.stage7_validation import (
    split_plan, evaluate_history, fit_frequency, predict_frequency, scores, block_interval,
)
from research_workspace.stage7_scenarios import scenarios
from research_workspace.stage7_history import collect_history, save_private, load_private


def long_fixture():
    grid = expected_grid("2025-01-02", "2025-06-25").iloc[:120 * 26].copy()
    x = np.arange(len(grid))
    close = 100 + x * .001 + np.sin(x / 9)
    grid["open"] = close
    grid["close"] = close
    grid["high"] = close + .1
    grid["low"] = close - .1
    grid["volume"] = 1000 + x % 100
    return grid


class Stage7ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.meta = synthetic_fixture()
        cls.dataset = event_dataset(cls.frame, cls.meta)

    def test_features_and_predictions_are_prefix_invariant(self):
        shorter = event_dataset(self.frame, self.meta, visible_count=85)
        original = {r["features"]["index"]: r["features"] for r in shorter["records"]}
        future = {r["features"]["index"]: r["features"] for r in self.dataset["records"]}
        for i, record in original.items():
            self.assertEqual(record, future[i])
            self.assertEqual(scenarios(record), scenarios(future[i]))
        # Truncation changes full snapshot hash, never a causal predictor hash.
        small = event_dataset(self.frame.iloc[:78], self.meta)
        self.assertNotEqual(small["dataset_sha256"], self.dataset["dataset_sha256"])
        self.assertEqual(small["records"][0]["features"], self.dataset["records"][0]["features"])

    def test_outcomes_invisible_until_exact_completed_horizon(self):
        for horizon in (4, 16):
            record = next(r["features"] for r in self.dataset["records"] if r["features"]["index"] == 40)
            pending = outcome(self.frame.iloc[:40 + horizon], record, horizon)
            self.assertIsNone(pending["available_at"])
            self.assertIsNone(pending["up"])
            ready = outcome(self.frame.iloc[:41 + horizon], record, horizon)
            self.assertEqual(ready["available_at"], self.frame.bar_end.iloc[40 + horizon].isoformat())
            self.assertAlmostEqual(ready["return"], self.frame.close.iloc[40 + horizon] / record["close"] - 1)
        with self.assertRaises(ValueError):
            outcome(self.frame, record, 8)

    def test_replay_table_contains_no_future_outcomes(self):
        replay = event_dataset(self.frame, self.meta, visible_count=55)
        cutoff = self.frame.bar_end.iloc[54]
        for row in replay["records"]:
            end = row["outcome"]["available_at"]
            self.assertTrue(end is None or pd.Timestamp(end) <= cutoff)
            if row["features"]["index"] + row["horizon"] >= 55:
                self.assertIsNone(row["outcome"]["return"])

    def test_confirmed_pivots_and_lines_not_backdated(self):
        for row in self.dataset["records"]:
            f = row["features"]
            self.assertTrue(all(line["known_at_index"] <= f["index"] for line in f["lines"].values()))
        early = event_dataset(self.frame, self.meta, visible_count=21)["records"][0]["features"]
        self.assertEqual(early["lines"], {})

    def test_event_definitions_and_intrabar_ambiguity(self):
        zone = {"id": "x", "kind": "resistance", "lower": 99, "upper": 100}
        bars = pd.DataFrame({"close": [99.5, 101, 102, 101], "low": [99.4, 100.5, 101.5, 99.5],
                             "high": [99.6, 101.1, 102.1, 101.2]})
        snaps = [{"zones": [zone]} for _ in range(4)]
        event = classify_event(bars, snaps, 2, None)
        self.assertEqual(event["type"], "breakout")
        self.assertEqual(classify_event(bars, snaps, 3, event)["type"], "retest")
        bars.loc[2, "low"] = 98
        self.assertEqual(classify_event(bars, snaps, 2, None)["type"], "ambiguous")
        bars.loc[2, "low"] = 101.5
        snaps[0]["zones"] = [zone, {**zone, "id": "y"}]
        self.assertEqual(classify_event(bars, snaps, 2, None)["type"], "ambiguous")
        self.assertEqual(classify_event(bars, [{"zones": []}] * 4, 2, None)["type"], "none")

    def test_sr_endpoint_labels_and_ties(self):
        frame = self.frame.iloc[:5].copy()
        record = {"index": 0, "close": 100, "event": {
            "type": "breakout", "direction": 1, "zone": {"lower": 99, "upper": 100}}}
        frame["low"], frame["high"] = 100.2, 101.2
        frame["close"] = 101
        self.assertEqual(outcome(frame, record, 4)["sr_outcome"], "continuation")
        frame.loc[frame.index[-1], "close"] = 98
        self.assertEqual(outcome(frame, record, 4)["sr_outcome"], "reversal")
        frame.loc[frame.index[-1], "close"] = 100
        self.assertEqual(outcome(frame, record, 4)["up"], 0)
        frame.loc[frame.index[2], ["low", "high"]] = [98, 101]
        self.assertEqual(outcome(frame, record, 4)["sr_outcome"], "ambiguous")

    def test_missing_data_and_sealed_boundary_fail_closed(self):
        with self.assertRaises(ValueError):
            event_dataset(self.frame.drop(index=10), self.meta)
        sealed = self.frame.copy()
        sealed["timestamp"] = sealed.timestamp + pd.Timedelta(days=30)
        with self.assertRaisesRegex(ValueError, "sealed"):
            event_dataset(sealed, self.meta)
        with self.assertRaises(ValueError):
            event_dataset(self.frame, {**self.meta, "orders_enabled": True})
        self.assertEqual(event_dataset(self.frame, self.meta, visible_count=10)["records"], [])

    def test_no_probabilities_even_with_forged_metadata(self):
        dataset = event_dataset(self.frame, {**self.meta, "calibrated": True, "probability": .99})
        report = scenarios(dataset["records"][-1]["features"])
        self.assertIsNone(report["probability"])
        self.assertIn("INSUFFICIENT", report["status"])
        self.assertTrue(all("horizons" in s for s in report["scenarios"]))

    def test_export_allowlist_contains_no_price_or_credentials(self):
        summary = safe_summary(self.dataset)
        self.assertTrue(summary["synthetic"])
        self.assertFalse(summary["orders_enabled"])
        self.assertTrue({"close", "return", "volume", "api_key", "origin"}.isdisjoint(summary))
        json.dumps(summary, allow_nan=False)

    def test_scores_and_calibration_against_hand_computed_values(self):
        result = scores([0, 1], [.25, .75])
        self.assertAlmostEqual(result["brier"], .0625)
        self.assertAlmostEqual(result["log_loss"], -np.log(.75))
        self.assertEqual(result["balanced_accuracy"], 1)
        self.assertAlmostEqual(result["ece"], .25)
        self.assertEqual(sum(b["n"] for b in result["calibration"]), 2)
        self.assertIsNone(scores([1, 1], [.5, .5])["balanced_accuracy"])
        self.assertEqual(sum(b["n"] for b in scores([0, 1], [0, 1])["calibration"]), 2)
        for p in ([float("nan"), .1], [-.1, .5], [1.1, .2]):
            with self.assertRaises(ValueError):
                scores([0, 1], p)

    def test_session_bootstrap_is_paired_and_deterministic(self):
        result = block_interval([0, 1, 0, 1], [0, 1, 0, 1], [.5] * 4, ["a", "a", "b", "b"])
        self.assertEqual(result["lower"], .25)
        self.assertEqual(result["upper"], .25)
        self.assertEqual(result, block_interval([0, 1, 0, 1], [0, 1, 0, 1], [.5] * 4, ["a", "a", "b", "b"]))
        self.assertIsNone(block_interval([0, 1], [.5, .5], [.5, .5], ["a", "a"]))

    def test_frequency_smoothing_and_fallback(self):
        f = self.dataset["records"][0]["features"]
        rows = [{"features": f, "outcome": {"up": 1}} for _ in range(30)]
        model = fit_frequency(rows)
        self.assertAlmostEqual(predict_frequency(model, f), 31 / 32)
        other = {**f, "structure": "unknown"}
        self.assertEqual(predict_frequency(model, other), model["base"])
        with self.assertRaises(ValueError):
            fit_frequency([{"features": f, "outcome": {"up": None}}])

    def test_sparse_history_not_evaluated(self):
        report = evaluate_history(self.frame, self.meta)
        self.assertIn("INSUFFICIENT", report["status"])
        self.assertEqual(report["horizons"], {})
        self.assertFalse(report["final_holdout_evaluated"])

    def test_walk_forward_purge_and_holdout_isolation(self):
        frame = long_fixture()
        plan = split_plan(frame)
        self.assertEqual(plan["holdout_sessions"], 20)
        with patch("research_workspace.stage7_validation.causal_features", wraps=causal_features) as spy:
            report = evaluate_history(frame, self.meta)
            self.assertEqual(len(spy.call_args.args[0]), plan["holdout_start"])
        self.assertFalse(report["probabilities_publishable"])
        for h, result in report["horizons"].items():
            for fold in result["folds"]:
                self.assertLess(fold["train_last_outcome_index"], fold["start"] - 16)
                self.assertLessEqual(fold["stop"], plan["holdout_start"])
            self.assertEqual(set(result["metrics"]), {"model", "unconditional", "majority", "persistence", "ema_rule"})
        changed = frame.copy()
        changed.loc[changed.index[plan["holdout_start"]:], ["open", "high", "low", "close"]] *= 2
        altered = evaluate_history(changed, self.meta)
        self.assertEqual(report["horizons"], altered["horizons"])
        self.assertNotEqual(report["dataset_sha256"], altered["dataset_sha256"])
        json.dumps(report, allow_nan=False)

    def test_download_requires_explicit_action_and_rejects_sealed_dates(self):
        def forbidden(*args):
            self.fail("No network call permitted")
        for consent, end in ((False, "2026-10-16"), (True, "2026-10-27")):
            with self.assertRaises(ValueError):
                collect_history("SPY", "2026-10-05", end, feed="iex", api_key="key", api_secret="secret",
                                explicit_download=consent, request_page=forbidden)

    def test_collection_batches_and_metadata_no_secrets(self):
        source = long_fixture()
        calls = []
        def fake(params, *_):
            calls.append(params)
            selected = source.loc[(source.timestamp >= pd.Timestamp(params["start"])) &
                                  (source.timestamp < pd.Timestamp(params["end"]))]
            return {"bars": {"SPY": [{"t": r.timestamp.isoformat(), "o": r.open, "h": r.high,
                                     "l": r.low, "c": r.close, "v": r.volume} for r in selected.itertuples()]}}
        frame, meta = collect_history("SPY", str(source.session.iloc[0]), str(source.session.iloc[-1]),
                                     feed="sip", api_key="SENSITIVE", api_secret="SENSITIVE2",
                                     explicit_download=True, request_page=fake)
        self.assertEqual(len(frame), len(source))
        self.assertGreater(len(calls), 1)
        self.assertEqual(meta["missing_bars"], 0)
        self.assertNotIn("SENSITIVE", json.dumps(meta))
        self.assertTrue(all(c["feed"] == "sip" for c in calls))

    def test_transport_error_sanitized_no_retry(self):
        calls = []
        def fail(*_):
            calls.append(1)
            raise RuntimeError("SENSITIVE")
        with self.assertRaisesRegex(ValueError, "batch failed") as exc:
            collect_history("SPY", "2026-10-05", "2026-10-16", feed="iex", api_key="x", api_secret="y",
                            explicit_download=True, request_page=fail)
        self.assertNotIn("SENSITIVE", str(exc.exception))
        self.assertEqual(len(calls), 1)

    def test_provider_rejects_entire_missing_edge_session(self):
        rows = [{"t": r.timestamp.isoformat(), "o": r.open, "h": r.high,
                 "l": r.low, "c": r.close, "v": r.volume} for r in self.frame.itertuples()]
        for bad in (rows[26:], rows[:-26]):
            with self.subTest(first=bad[0]["t"]), self.assertRaises(ValueError):
                read_alpaca_history("SPY", "2026-10-05", "2026-10-16", feed="iex",
                                    api_key="x", api_secret="y",
                                    request_page=lambda *_: {"bars": {"SPY": bad}})

    def test_private_snapshot_cannot_be_written_inside_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            with self.assertRaises(ValueError):
                save_private(self.frame, self.meta, root / "private")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot"
            manifest = save_private(self.frame, self.meta, target)
            import hashlib
            self.assertEqual(manifest["csv_sha256"], hashlib.sha256((target / "bars.csv").read_bytes()).hexdigest())
            with self.assertRaises(ValueError):
                save_private(self.frame, self.meta, target)

    def test_snapshot_hash_and_coverage_mismatch_rejected(self):
        meta = {**self.meta, "schema": "tradelab.stage7.v1", "synthetic": False,
                "feed": "sip", "adjustment": "split", "received_bars": len(self.frame),
                "expected_bars": len(self.frame)}
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot"
            manifest = save_private(self.frame, meta, target)
            clean, _ = load_private(target)
            self.assertEqual(len(clean), len(self.frame))
            manifest["expected_bars"] += 26
            (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coverage"):
                load_private(target)
            (target / "bars.csv").write_bytes((target / "bars.csv").read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                load_private(target)

    def test_actual_unspecified_feed_cannot_be_evaluated(self):
        report = evaluate_history(long_fixture(), {**self.meta, "synthetic": False})
        self.assertEqual(report["horizons"], {})
        self.assertIn("feed", report["reason"])

    def test_downward_break_and_reversal_are_symmetric(self):
        z = {"id": "s", "kind": "support", "lower": 100, "upper": 101}
        bars = pd.DataFrame({"close": [100.5, 99, 98], "low": [100.4, 98.9, 97.9],
                             "high": [100.6, 99.1, 98.1]})
        self.assertEqual(classify_event(bars, [{"zones": [z]}] * 3, 2, None)["type"], "breakdown")

    def test_synthetic_flag_must_be_boolean(self):
        with self.assertRaises(ValueError):
            event_dataset(self.frame, {**self.meta, "synthetic": 0})


if __name__ == "__main__":
    unittest.main()
