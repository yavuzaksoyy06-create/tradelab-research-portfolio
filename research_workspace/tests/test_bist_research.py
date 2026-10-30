"""Simulated BIST daily fixtures; no real-price result or provider download."""
import hashlib
import json
import unittest

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from research_workspace.bist_research import CONSTANTS, analyze, load_csv


class BISTResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        days = xcals.get_calendar("XIST", start="2020-01-01", end="2024-12-31").sessions
        price = 100 + np.arange(len(days)) * .05 + np.sin(np.arange(len(days)) / 15) * 8
        cls.raw = pd.DataFrame({"date": days, "open": price, "high": price + 1,
                                "low": price - 1, "close": price, "volume": 1000,
                                "adjusted_close": price * .9})

    def pack(self, raw=None, **changes):
        payload = (self.raw if raw is None else raw).to_csv(index=False).encode()
        meta = {**CONSTANTS, "symbol": "THYAO", "provider": "Simulated test provider",
                "source_url": "https://example.test/history", "license_reference": "Simulated fixture only",
                "csv_sha256": hashlib.sha256(payload).hexdigest(), **changes}
        return payload, meta

    def test_complete_registered_fixture_is_sanitized(self):
        payload, meta = self.pack(api_key="TEST_SECRET", arbitrary_path="PRIVATE_PATH")
        frame, safe = load_csv(payload, meta)
        self.assertEqual(len(frame), len(self.raw))
        self.assertFalse(safe["source_independently_verified"])
        self.assertFalse(safe["orders_enabled"])
        self.assertNotIn("TEST_SECRET", json.dumps(safe))
        self.assertNotIn("PRIVATE_PATH", json.dumps(safe))

    def test_hash_and_usage_rights_are_required(self):
        payload, meta = self.pack()
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            load_csv(payload + b"\n", meta)
        for key, value in (("usage_rights", "unknown"), ("source_independently_verified", 0),
                           ("currency", "USD"), ("symbol", "SPY")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_csv(payload, {**meta, key: value})

    def test_source_rejects_credential_query_and_fragment_urls(self):
        for url in ("http://example.test/", "https://user:pass@example.test/",
                    "https://example.test/?token=SECRET", "https://example.test/#SECRET"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "INVALID_SOURCE"):
                load_csv(*self.pack(source_url=url))

    def test_reserved_dates_rejected_before_invalid_numerics(self):
        for day, code in (("2025-01-01", "HOLDOUT_RESERVED"), ("2026-10-26", "SEALED_PERIOD")):
            raw = self.raw.copy()
            raw["date"] = raw.date.astype(str)
            raw.loc[len(raw) - 1, "date"] = day
            raw["adjusted_close"] = raw.adjusted_close.astype(str)
            raw.loc[len(raw) - 1, "adjusted_close"] = "not a numerical value"
            with self.subTest(day=day), self.assertRaisesRegex(ValueError, code):
                load_csv(*self.pack(raw))

    def test_missing_duplicate_and_invalid_prices_rejected(self):
        missing = self.raw.drop(index=20)
        duplicate = self.raw.copy()
        duplicate.loc[21, "date"] = duplicate.loc[20, "date"]
        for raw in (missing, duplicate):
            with self.assertRaises(ValueError):
                load_csv(*self.pack(raw))
        for field, value in (("volume", -1), ("low", 999999), ("close", 0), ("adjusted_close", np.nan)):
            raw = self.raw.copy()
            raw.loc[30, field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_csv(*self.pack(raw))

    def test_direct_analyze_cannot_replace_registered_input(self):
        frame, meta = load_csv(*self.pack())
        frame.loc[300, "adjusted_close"] *= 1.01
        with self.assertRaisesRegex(ValueError, "REGISTERED_INPUT_CHANGED"):
            analyze(frame, meta)

    def test_registered_metadata_cannot_be_relabelled(self):
        frame, meta = load_csv(*self.pack())
        for field, value in (("symbol", "GARAN"), ("provider", "different"),
                             ("csv_sha256", "0" * 64), ("source_url", "https://other.test/history")):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "REGISTERED_INPUT_CHANGED"):
                analyze(frame, {**meta, field: value})

    def test_finite_extreme_prices_cannot_create_infinite_statistics(self):
        raw = self.raw.copy()
        raw.loc[800, "adjusted_close"] = 1e-300
        raw.loc[801, "adjusted_close"] = 1e300
        frame, meta = load_csv(*self.pack(raw))
        with self.assertRaisesRegex(ValueError, "INVALID_CALCULATION"):
            analyze(frame, meta)

    def test_delayed_position_matches_independent_recursive_oracle(self):
        frame, meta = load_csv(*self.pack())
        _, curve = analyze(frame, meta)
        ema20 = ema60 = float(frame.adjusted_close.iloc[0])
        signals = []
        for i, value in enumerate(frame.adjusted_close):
            if i:
                ema20 += 2 / 21 * (value - ema20)
                ema60 += 2 / 61 * (value - ema60)
            signals.append(float(i >= 59 and ema20 > ema60))
        for row in curve.itertuples():
            source = frame.index[frame.date == row.date][0]
            self.assertEqual(row.position, signals[source - 2])

    def test_future_suffix_does_not_change_earlier_features_or_returns(self):
        frame, meta = load_csv(*self.pack())
        _, original = analyze(frame, meta)
        changed = self.raw.copy()
        cutoff = changed.date.iloc[-80]
        changed.loc[changed.date >= cutoff, "adjusted_close"] *= 1.3
        altered, newmeta = load_csv(*self.pack(changed))
        _, newcurve = analyze(altered, newmeta)
        pd.testing.assert_frame_equal(original.loc[original.date < cutoff].reset_index(drop=True),
                                      newcurve.loc[newcurve.date < cutoff].reset_index(drop=True))

    def test_always_long_matches_buyhold_with_both_transaction_sides(self):
        raw = self.raw.copy()
        raw["adjusted_close"] = np.arange(len(raw)) + 100.0
        frame, meta = load_csv(*self.pack(raw))
        summary, curve = analyze(frame, meta)
        self.assertTrue((curve.position == 1).all())
        strategy = summary["sensitivity_bps_per_side"]["25"]["strategy"]
        benchmark = summary["sensitivity_bps_per_side"]["25"]["buy_hold"]
        self.assertEqual(strategy, benchmark)
        start = frame.index[frame.date == curve.date.iloc[0]][0]
        expected = (frame.adjusted_close.iloc[-1] / frame.adjusted_close.iloc[start - 1]) * (1 - .0025) ** 2 - 1
        self.assertAlmostEqual(strategy["net_total_return"], expected, places=12)
        self.assertEqual(summary["turnover_including_terminal_exit"], 2)
        self.assertEqual(summary["daily_mean_excess_95_block_interval"], [0, 0])

    def test_report_is_finite_deterministic_and_excludes_holdout(self):
        frame, meta = load_csv(*self.pack())
        summary, curve = analyze(frame, meta)
        again, _ = analyze(frame, meta)
        self.assertEqual(summary, again)
        json.dumps(summary, allow_nan=False)
        self.assertGreaterEqual(curve.date.min(), pd.Timestamp("2023-01-01"))
        self.assertLess(curve.date.max(), pd.Timestamp("2025-01-01"))
        self.assertFalse(summary["holdout_scored"])
        self.assertFalse(summary["orders_enabled"])
        results = [summary["sensitivity_bps_per_side"][str(b)]["strategy"]["net_total_return"] for b in (10, 25, 50)]
        self.assertGreaterEqual(results[0], results[1])
        self.assertGreaterEqual(results[1], results[2])
        annual = summary["annual_net_returns"]
        self.assertAlmostEqual((1 + annual["2023"]) * (1 + annual["2024"]) - 1, results[1])
