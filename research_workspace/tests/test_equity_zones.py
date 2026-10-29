"""Causal S/R chart display tests, isolated from the frozen V4/V4.1 engine."""
import unittest

from research_workspace.equity_data import analyze_prefix, synthetic_fixture
from research_workspace.equity_ui import equity_chart
from research_workspace.equity_zones import historical_zone_bands


def _snapshot(index, *zones):
    return {"index": index, "zones": list(zones)}


def _zone(zone_id, kind, lo, hi):
    return {"id": zone_id, "kind": kind, "lower": lo, "upper": hi}


class EquityZoneHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, _ = synthetic_fixture("SPY")

    def test_zone_bands_start_only_when_known_and_split_on_change_or_disappearance(self):
        s = _zone("Z1", "support", 95.0, 96.0)
        updated = _zone("Z1", "support", 94.0, 96.0)
        r = _zone("Z2", "resistance", 101.0, 102.0)
        snapshots = [
            _snapshot(0), _snapshot(1, s), _snapshot(2, s),
            _snapshot(3, updated), _snapshot(4), _snapshot(5, r),
        ]
        actual = historical_zone_bands(snapshots)
        self.assertEqual(
            [(b["zone_id"], b["start_index"], b["end_index"], b["lower"], b["upper"]) for b in actual],
            [("Z1", 1, 2, 95.0, 96.0),
             ("Z1", 3, 3, 94.0, 96.0),
             ("Z2", 5, 5, 101.0, 102.0)],
        )
        self.assertEqual(
            [(b["zone_id"], b["start_index"], b["end_index"])
             for b in historical_zone_bands(snapshots, visible_start=2)],
            [("Z1", 2, 2), ("Z1", 3, 3), ("Z2", 5, 5)],
        )

    def test_rendered_historical_bands_match_completed_snapshots_exactly(self):
        prefix, features = analyze_prefix(self.frame, 100)
        fig = equity_chart(prefix, features, "SPY")
        bands = historical_zone_bands(features["snapshots"])
        shapes = [shape for shape in fig.layout.shapes if shape.type == "rect"]
        self.assertEqual(len(shapes), len(bands))
        x = list(fig.data[0].x)
        for shape, band in zip(shapes, bands):
            self.assertEqual(shape.x0, x[band["start_index"]])
            self.assertEqual(shape.x1, x[band["end_index"]])
            self.assertEqual((shape.x0shift, shape.x1shift), (-0.5, 0.5))
            self.assertEqual((shape.y0, shape.y1), (band["lower"], band["upper"]))
            self.assertEqual((shape.xref, shape.yref), ("x", "y"))
            for i in range(band["start_index"], band["end_index"] + 1):
                zone = next(z for z in features["snapshots"][i]["zones"]
                            if z["id"] == band["zone_id"])
                self.assertEqual(
                    (zone["kind"], zone["lower"], zone["upper"]),
                    (band["kind"], band["lower"], band["upper"]),
                )

    def test_confirmed_pivot_marker_never_points_to_earlier_unconfirmed_candle(self):
        prefix, features = analyze_prefix(self.frame, 100)
        fig = equity_chart(prefix, features, "SPY")
        traces = {trace.name: trace for trace in fig.data[2:]}
        for kind in ("support", "resistance"):
            matching = [p for p in features["pivots"] if p["kind"] == kind
                        and p["confirmed_index"] < 100]
            if not matching:
                self.assertNotIn(kind, traces)
                continue
            self.assertIn(kind, traces)
            expected = [
                prefix.iloc[p["confirmed_index"]].timestamp.tz_convert(
                    "America/New_York").strftime("%Y-%m-%d %H:%M")
                for p in matching
            ]
            self.assertEqual(list(traces[kind].x), expected)
            self.assertEqual([v[1] for v in traces[kind].customdata],
                             [p["confirmed_at"] for p in matching])

    def test_replay_prefix_does_not_change_existing_bar_close_zone_history(self):
        _, full = analyze_prefix(self.frame, 110)
        _, short = analyze_prefix(self.frame, 85)
        self.assertEqual(historical_zone_bands(full["snapshots"][:85]),
                         historical_zone_bands(short["snapshots"]))

    def test_last_130_bar_view_does_not_project_back_or_include_future(self):
        prefix, features = analyze_prefix(self.frame, 201)
        fig = equity_chart(prefix, features, "SPY")
        bands = historical_zone_bands(features["snapshots"], visible_start=71)
        shapes = [shape for shape in fig.layout.shapes if shape.type == "rect"]
        self.assertEqual(len(shapes), len(bands))
        self.assertEqual(len(fig.data[0].x), 130)
        self.assertTrue(all(b["start_index"] >= 71 and b["end_index"] <= 200
                            for b in bands))
        for shape in shapes:
            self.assertIn(shape.x0, fig.data[0].x)
            self.assertIn(shape.x1, fig.data[0].x)

    def test_rejects_invalid_snapshot_order_or_duplicate_ids(self):
        with self.assertRaises(ValueError):
            historical_zone_bands([_snapshot(1)])
        with self.assertRaises(ValueError):
            historical_zone_bands([_snapshot(0, _zone("Z1", "support", 1, 2),
                                               _zone("Z1", "support", 1, 2))])
        with self.assertRaises(ValueError):
            historical_zone_bands([], visible_start=-1)


if __name__ == "__main__":
    unittest.main()
