"""Independent numeric oracles; these are factual, not predictive tests."""
import unittest
import numpy as np
from research_workspace.equity_data import synthetic_fixture, analyze_prefix
from research_workspace.equity_commentary import commentary_report


def ema(values, period):
    result = float(values[0])
    for value in values[1:]:
        result += 2 / (period + 1) * (value - result)
    return result


def rsi(values):
    changes = np.diff(values)
    up = sum(max(x, 0) for x in changes[:14]) / 14
    down = sum(max(-x, 0) for x in changes[:14]) / 14
    for x in changes[14:]:
        up = (13 * up + max(x, 0)) / 14
        down = (13 * down + max(-x, 0)) / 14
    return 50 if up == down == 0 else 100 if down == 0 else 100 - 100 / (1 + up / down)


class CommentaryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.meta = synthetic_fixture()

    def test_many_checkpoints_against_independent_scalar_oracles(self):
        for n in range(21, len(self.frame) + 1, 7):
            with self.subTest(n=n):
                prefix, features = analyze_prefix(self.frame, n)
                report = commentary_report(prefix, features, self.meta)
                e = report["evidence"]
                values = prefix.close.tolist()
                self.assertAlmostEqual(e["ema_9"], ema(values, 9), places=10)
                self.assertAlmostEqual(e["ema_21"], ema(values, 21), places=10)
                self.assertAlmostEqual(e["rsi_14"], rsi(values), places=10)
                self.assertAlmostEqual(e["relative_volume_20"],
                                       prefix.volume.iloc[-1] / (sum(prefix.volume.iloc[-21:-1]) / 20))
                text = report["sections"][2]["text"]
                self.assertIn("üzerinde" if e["ema_9"] > e["ema_21"] else "altında", text)
                self.assertIn("30 altında" if e["rsi_14"] < 30 else
                              "70 üzerinde" if e["rsi_14"] > 70 else "30–70", text)
                self.assertEqual(report["as_of_utc"], prefix.bar_end.iloc[-1].isoformat())
                self.assertEqual(e["active_zones"], len(features["snapshots"][-1]["zones"]))
                self.assertTrue(all(p["confirmed_index"] < n for p in features["pivots"]))

    def test_monotone_extremes_and_incomplete_provenance(self):
        for direction in (-1, 1):
            frame = self.frame.iloc[:50].copy()
            frame["close"] = 100 + direction * np.arange(50) * .1
            frame["open"] = frame.close
            frame["high"] = frame.close + .01
            frame["low"] = frame.close - .01
            prefix, features = analyze_prefix(frame, 50)
            meta = {"symbol": "SPY", "feed_verified": False, "orders_enabled": False}
            report = commentary_report(prefix, features, meta)
            self.assertAlmostEqual(report["evidence"]["rsi_14"], 100 if direction > 0 else 0)
            self.assertEqual(report["evidence"]["active_zones"], 0)
            self.assertIn("belirtilmemiş", report["sections"][-1]["text"])

    def test_no_unconfirmed_pivot_or_line_in_early_commentary(self):
        prefix, features = analyze_prefix(self.frame, 10)
        report = commentary_report(prefix, features, self.meta)
        self.assertEqual(report["evidence"]["confirmed_swings"], 0)
        self.assertIsNone(report["evidence"]["relative_volume_20"])
        self.assertIn("iki onaylı pivot henüz yok", report["sections"][5]["text"])
