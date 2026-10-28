"""Offline, deterministic confirmed-swing and causal trendline tests."""
import unittest

from research_workspace.equity_data import analyze_prefix, synthetic_fixture
from research_workspace.equity_structure import (
    confirmed_swing_events, confirmed_trendline_segments, structure_state,
)
from research_workspace.equity_ui import equity_chart


def pivot(kind, index, confirmed, price):
    return {
        "kind": kind, "pivot_index": index, "confirmed_index": confirmed,
        "price": price, "confirmed_at": f"confirmed-{confirmed}",
    }


class EquityStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, _ = synthetic_fixture("SPY")

    def sample_features(self):
        return {"pivots": [
            pivot("support", 1, 3, 100),
            pivot("resistance", 2, 4, 110),
            pivot("support", 5, 7, 102),
            pivot("resistance", 6, 8, 112),
            pivot("support", 9, 11, 99),
            pivot("resistance", 10, 12, 108),
        ]}

    def test_swing_labels_compare_only_confirmed_same_kind(self):
        features = self.sample_features()
        events = confirmed_swing_events(features, 13)
        self.assertEqual([e["label"] for e in events],
                         ["L0", "H0", "HL", "HH", "LL", "LH"])
        self.assertEqual(structure_state(events[:4]), "rising")
        self.assertEqual(structure_state(events), "falling")
        self.assertEqual(structure_state(events[:2]), "insufficient")

    def test_trendline_is_drawn_only_after_second_pivot_confirmation(self):
        segments = confirmed_trendline_segments(self.sample_features(), 13)
        support = [s for s in segments if s["kind"] == "support"]
        self.assertEqual([(s["start_index"], s["end_index"]) for s in support],
                         [(7, 10), (11, 12)])
        self.assertEqual(support[0]["known_at_index"], 7)
        self.assertEqual(support[0]["pivot_indices"], (1, 5))
        self.assertAlmostEqual(support[0]["slope_per_bar"], 0.5)
        self.assertAlmostEqual(support[0]["values"][0], 103.0)
        self.assertAlmostEqual(support[1]["slope_per_bar"], -0.75)
        self.assertEqual(confirmed_trendline_segments(self.sample_features(), 7), [])

    def test_prefix_invariance_of_pivots_and_trendline_state(self):
        _, long = analyze_prefix(self.frame, 145)
        _, short = analyze_prefix(self.frame, 85)
        long_events = confirmed_swing_events(
            {"pivots": [p for p in long["pivots"] if p["confirmed_index"] < 85]}, 85)
        self.assertEqual(confirmed_swing_events(short, 85), long_events)
        long_lines = confirmed_trendline_segments(
            {"pivots": [p for p in long["pivots"] if p["confirmed_index"] < 85]}, 85)
        self.assertEqual(confirmed_trendline_segments(short, 85), long_lines)

    def test_chart_trendlines_and_structure_labels_never_start_before_confirmation(self):
        prefix, features = analyze_prefix(self.frame, 100)
        fig = equity_chart(prefix, features, "SPY", show_trendlines=True,
                           show_structure=True, show_rsi=True, ema_periods=(9, 21))
        x = list(fig.data[0].x)
        segments = confirmed_trendline_segments(features, 100)
        traces = [t for t in fig.data if t.name in
                  ("Confirmed low trendline", "Confirmed high trendline")]
        self.assertEqual(len(traces), len(segments))
        for trace, seg in zip(traces, segments):
            self.assertEqual(list(trace.x), x[seg["start_index"]:seg["end_index"] + 1])
            self.assertEqual(list(trace.y), seg["values"])
            self.assertGreaterEqual(seg["start_index"], seg["known_at_index"])
            self.assertIn(seg["known_at_index"], range(100))

    def test_trimmed_chart_has_no_offscreen_or_future_trendline_x(self):
        prefix, features = analyze_prefix(self.frame, 201)
        fig = equity_chart(prefix, features, "SPY", show_trendlines=True,
                           show_structure=True)
        x = set(fig.data[0].x)
        for trace in fig.data:
            if trace.name and (trace.name.startswith("Confirmed ") or
                               trace.name.startswith("Confirmed swing")):
                self.assertTrue(set(trace.x).issubset(x))

    def test_equal_swing_is_not_higher_or_lower(self):
        features = {"pivots": [
            pivot("support", 1, 3, 10.0),
            pivot("support", 5, 7, 10.0),
            pivot("resistance", 6, 8, 20.0),
            pivot("resistance", 10, 12, 20.0),
        ]}
        events = confirmed_swing_events(features, 13)
        self.assertEqual([e["label"] for e in events], ["L0", "EL", "H0", "EH"])
        self.assertEqual(structure_state(events), "mixed")

    def test_invalid_future_confirmation_and_pivot_order_fail_closed(self):
        with self.assertRaises(ValueError):
            confirmed_swing_events({"pivots": [pivot("support", 1, 10, 100)]}, 8)
        with self.assertRaises(ValueError):
            confirmed_trendline_segments({"pivots": [
                pivot("support", 5, 7, 100),
                pivot("support", 4, 10, 101),
            ]}, 11)
        with self.assertRaises(ValueError):
            confirmed_swing_events({"pivots": []}, 0)


if __name__ == "__main__":
    unittest.main()
