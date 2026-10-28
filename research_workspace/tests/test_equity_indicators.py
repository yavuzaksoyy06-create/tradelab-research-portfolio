"""Deterministic, no-network tests for descriptive completed-bar indicators."""
import unittest

import pandas as pd

from research_workspace.equity_data import synthetic_fixture, analyze_prefix
from research_workspace.equity_indicators import indicator_frame, wilder_rsi
from research_workspace.equity_ui import equity_chart


class EquityIndicatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, _ = synthetic_fixture("SPY")

    def test_ema_and_rsi_warmup_are_explicitly_unavailable(self):
        stats = indicator_frame(self.frame)
        for period in (9, 21, 50, 200):
            key = f"ema_{period}"
            self.assertTrue(stats[key].iloc[:period - 1].isna().all())
            self.assertTrue(pd.notna(stats[key].iloc[period - 1]))
        self.assertTrue(stats["rsi_14"].iloc[:14].isna().all())
        self.assertTrue(pd.notna(stats["rsi_14"].iloc[14]))

    def test_rsi_constant_and_monotonic_series(self):
        self.assertAlmostEqual(wilder_rsi(pd.Series([100.0] * 30)).iloc[-1], 50.0)
        self.assertAlmostEqual(wilder_rsi(pd.Series(range(100, 130))).iloc[-1], 100.0)
        self.assertAlmostEqual(wilder_rsi(pd.Series(range(130, 100, -1))).iloc[-1], 0.0)

    def test_prefix_indicators_never_change_when_future_bars_arrive(self):
        full = indicator_frame(self.frame)
        for n in (1, 10, 15, 40, 85, 201):
            with self.subTest(visible_count=n):
                partial = indicator_frame(self.frame.iloc[:n])
                pd.testing.assert_frame_equal(
                    partial, full.iloc[:n].reset_index(drop=True)
                )
        self.assertTrue(indicator_frame(self.frame.iloc[:8])["rsi_14"].isna().all())

    def test_invalid_prices_rejected(self):
        frame = self.frame.iloc[:20].copy()
        frame.loc[frame.index[5], "close"] = -2.0
        with self.assertRaises(ValueError):
            indicator_frame(frame)
        with self.assertRaises(ValueError):
            indicator_frame(frame.iloc[:0])

    def test_optional_charts_keep_candle_volume_and_indicator_alignment(self):
        prefix, features = analyze_prefix(self.frame, 100)
        fig = equity_chart(prefix, features, "SPY", ema_periods=(9, 21, 50), show_rsi=True)
        bar_x = list(fig.data[0].x)
        self.assertEqual(bar_x, list(fig.data[1].x))
        self.assertEqual(fig.layout.xaxis3.type, "category")
        self.assertEqual(list(fig.layout.xaxis3.categoryarray), bar_x)
        named = {trace.name: trace for trace in fig.data if trace.name}
        for key in ("EMA 9", "EMA 21", "EMA 50", "RSI 14"):
            self.assertIn(key, named)
            self.assertEqual(list(named[key].x), bar_x)
        self.assertEqual(len(named["RSI 14"].y), 100)

    def test_short_replay_does_not_fabricate_long_ema(self):
        prefix, features = analyze_prefix(self.frame, 20)
        fig = equity_chart(prefix, features, "SPY", ema_periods=(200,), show_rsi=True)
        selected = next(trace for trace in fig.data if trace.name == "EMA 200")
        self.assertTrue(pd.isna(list(selected.y)).all())
        self.assertEqual(len(fig.data[0].x), 20)

    def test_unsupported_ema_is_rejected(self):
        prefix, features = analyze_prefix(self.frame, 40)
        with self.assertRaises(ValueError):
            equity_chart(prefix, features, "SPY", ema_periods=(7,))


if __name__ == "__main__":
    unittest.main()
