"""Causal volume tests: offline synthetic data, no feeds or order endpoints."""
import unittest

import pandas as pd

from research_workspace.equity_data import analyze_prefix, synthetic_fixture
from research_workspace.equity_ui import equity_chart
from research_workspace.equity_volume import volume_frame


class EquityVolumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, _ = synthetic_fixture("SPY")

    def test_first_baseline_needs_20_prior_completed_bars(self):
        values = volume_frame(self.frame)
        self.assertTrue(values["prior_volume_mean_20"].iloc[:20].isna().all())
        self.assertTrue(values["relative_volume_20"].iloc[:20].isna().all())
        expected = float(self.frame.volume.iloc[:20].mean())
        self.assertAlmostEqual(values["prior_volume_mean_20"].iloc[20], expected)
        self.assertAlmostEqual(values["relative_volume_20"].iloc[20],
                               float(self.frame.volume.iloc[20]) / expected)

    def test_outlier_does_not_leak_into_its_own_baseline(self):
        raw = pd.DataFrame({"volume": [10] * 20 + [1000, 10]})
        result = volume_frame(raw)
        self.assertEqual(result["prior_volume_mean_20"].iloc[20], 10)
        self.assertEqual(result["relative_volume_20"].iloc[20], 100)
        self.assertAlmostEqual(result["prior_volume_mean_20"].iloc[21],
                               (19 * 10 + 1000) / 20)

    def test_zero_prior_mean_is_unavailable_not_infinite(self):
        raw = pd.DataFrame({"volume": [0] * 20 + [50, 0]})
        result = volume_frame(raw)
        self.assertTrue(pd.isna(result["relative_volume_20"].iloc[20]))
        self.assertEqual(result["prior_volume_mean_20"].iloc[21], 2.5)
        self.assertEqual(result["relative_volume_20"].iloc[21], 0)

    def test_future_changes_never_alter_existing_volume_metrics(self):
        full = volume_frame(self.frame)
        for count in (1, 19, 20, 21, 85, 131, 201):
            with self.subTest(count=count):
                partial = volume_frame(self.frame.iloc[:count])
                pd.testing.assert_frame_equal(partial, full.iloc[:count].reset_index(drop=True))

    def test_rejects_invalid_inputs(self):
        for volume in (float("nan"), -1, float("inf")):
            with self.subTest(volume=volume), self.assertRaises(ValueError):
                volume_frame(pd.DataFrame({"volume": [volume]}))
        with self.assertRaises(ValueError):
            volume_frame(self.frame.iloc[:0])
        with self.assertRaises(ValueError):
            volume_frame(self.frame, lookback=True)
        with self.assertRaises(ValueError):
            volume_frame(self.frame, lookback=0)

    def test_volume_average_overlay_aligns_to_candle_and_volume_x_axis(self):
        prefix, features = analyze_prefix(self.frame, 100)
        fig = equity_chart(prefix, features, "SPY", show_volume_average=True,
                           ema_periods=(9, 21), show_rsi=True)
        candles, bars = list(fig.data[0].x), list(fig.data[1].x)
        self.assertEqual(candles, bars)
        baseline = next(trace for trace in fig.data if trace.name == "Prior 20-bar mean")
        self.assertEqual(list(baseline.x), candles)
        self.assertEqual(len(baseline.y), len(candles))
        self.assertTrue(pd.isna(list(baseline.y)[:20]).all())
        self.assertEqual(fig.layout.xaxis3.type, "category")
        self.assertEqual(list(fig.layout.xaxis3.categoryarray), candles)

    def test_volume_overlay_off_by_default_in_chart_function(self):
        prefix, features = analyze_prefix(self.frame, 100)
        fig = equity_chart(prefix, features, "SPY")
        self.assertFalse(any(trace.name == "Prior 20-bar mean" for trace in fig.data))

    def test_last_130_visible_bars_still_match_full_prefix_volume_history(self):
        prefix, features = analyze_prefix(self.frame, 201)
        fig = equity_chart(prefix, features, "SPY", show_volume_average=True)
        baseline = next(trace for trace in fig.data if trace.name == "Prior 20-bar mean")
        expected = volume_frame(prefix)["prior_volume_mean_20"].tail(130)
        self.assertEqual(len(baseline.y), 130)
        self.assertEqual(list(baseline.y), list(expected))


if __name__ == "__main__":
    unittest.main()
