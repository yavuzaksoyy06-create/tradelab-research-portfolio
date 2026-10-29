"""Offline regression checks for the actual historical Plotly AAPL daily example."""
import unittest
import pandas as pd

from demo_daily import (
    load_daily_sample, daily_indicators, confirmed_pivots,
    market_chart, english_report, SOURCE_URL,
)


class DailyDemoMarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_daily_sample()

    def test_real_historical_observations_bundled_and_not_synthetic(self):
        d = self.data
        self.assertEqual(len(d), 506)
        self.assertEqual(d.date.iloc[0].strftime("%Y-%m-%d"), "2015-02-17")
        self.assertEqual(d.date.iloc[-1].strftime("%Y-%m-%d"), "2017-02-16")
        self.assertAlmostEqual(float(d.close.iloc[0]), 127.830002)
        self.assertEqual(int(d.volume.iloc[0]), 63152400)
        self.assertIn("plotly/datasets", SOURCE_URL)

    def test_prefix_causality_indicators_and_english_commentary(self):
        a, b = self.data.iloc[:300], self.data.iloc[:370]
        pd.testing.assert_frame_equal(daily_indicators(a), daily_indicators(b).iloc[:len(a)])
        self.assertEqual(english_report(a), english_report(b.iloc[:len(a)]))
        self.assertTrue(all(x["confirmed_index"] < len(a) for x in confirmed_pivots(a)))
        old = confirmed_pivots(a)
        current = [p for p in confirmed_pivots(b) if p["confirmed_index"] < len(a)]
        self.assertEqual(old, current)

    def test_confirmed_pivots_never_backdated(self):
        for p in confirmed_pivots(self.data.iloc[:280]):
            self.assertEqual(p["confirmed_index"] - p["pivot_index"], 2)
            self.assertGreater(p["known_at"], p["pivot_date"])

    def test_observed_chart_uses_actual_daily_prices(self):
        prefix = self.data.iloc[:300]
        fig = market_chart(prefix, periods=(20, 50), show_rsi=True)
        self.assertEqual(float(fig.data[0].close[-1]), float(prefix.close.iloc[-1]))
        self.assertEqual(len(fig.data[0].x), 110)
        self.assertTrue(any("EMA 20" in str(t.name) for t in fig.data))
        self.assertNotIn("synthetic", str(fig.layout.title.text).lower())


if __name__ == "__main__":
    unittest.main()
