"""Offline, evidence-checked Turkish chart commentary tests."""
import unittest

from research_workspace.equity_commentary import commentary_report, _closest_zone
from research_workspace.equity_data import analyze_prefix, synthetic_fixture


class EquityCommentaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.meta = synthetic_fixture("SPY")

    def test_commentary_has_grounded_source_and_complete_replay_asof(self):
        prefix, features = analyze_prefix(self.frame, 100)
        report = commentary_report(prefix, features, self.meta)
        self.assertEqual(report["symbol"], "SPY")
        self.assertEqual(report["evidence"]["visible_bars"], 100)
        self.assertEqual(report["evidence"]["close"], float(prefix.close.iloc[-1]))
        self.assertEqual(report["as_of_utc"], prefix.bar_end.iloc[-1].isoformat())
        self.assertEqual(report["evidence"]["orders_enabled"], False)
        self.assertEqual(report["evidence"]["point_in_time_archive_verified"], False)
        headings = [section["heading"] for section in report["sections"]]
        self.assertIn("Fiyat ve gözlem zamanı", headings)
        self.assertIn("Mekanik trend çizgileri", headings)
        self.assertIn("Veri güvenilirliği ve kapsam", headings)
        prose = " ".join(section["text"] for section in report["sections"])
        self.assertIn("Sentetik eğitim verisi", prose)
        self.assertIn("kârlılık", prose)
        self.assertNotIn("API_SECRET", prose)

    def test_no_lookahead_when_future_bars_arrive(self):
        prefix, features = analyze_prefix(self.frame, 85)
        full_prefix, full_features = analyze_prefix(self.frame, 145)
        historical = {
            "pivots": [p for p in full_features["pivots"] if p["confirmed_index"] < 85],
            "snapshots": full_features["snapshots"][:85],
        }
        original = commentary_report(prefix, features, self.meta)
        rederived = commentary_report(full_prefix.iloc[:85], historical, self.meta)
        self.assertEqual(original, rederived)
        shorter, fewer = analyze_prefix(self.frame, 31)
        earlier = commentary_report(shorter, fewer, self.meta)
        self.assertNotEqual(earlier["as_of_utc"], original["as_of_utc"])

    def test_warmup_and_missing_zones_produce_explicit_unavailable_text(self):
        prefix, features = analyze_prefix(self.frame, 1)
        report = commentary_report(prefix, features, self.meta)
        text = " ".join(section["text"] for section in report["sections"])
        self.assertIn("henüz", text)
        self.assertIn("RVOL henüz yok", text)
        self.assertIsNone(report["evidence"]["relative_volume_20"])
        self.assertIsNone(report["evidence"]["rsi_14"])
        self.assertEqual(report["structure"], "insufficient")

    def test_nearest_active_zone_uses_only_correct_kind_and_side(self):
        zones = [
            {"id": "Z1", "kind": "support", "lower": 90, "upper": 92},
            {"id": "Z2", "kind": "support", "lower": 97, "upper": 98},
            {"id": "Z3", "kind": "resistance", "lower": 102, "upper": 104},
            {"id": "Z4", "kind": "resistance", "lower": 106, "upper": 108},
        ]
        self.assertEqual(_closest_zone(zones, "support", 100)["id"], "Z2")
        self.assertEqual(_closest_zone(zones, "resistance", 100)["id"], "Z3")
        self.assertIsNone(_closest_zone(zones, "support", 80))
        self.assertIsNone(_closest_zone(zones, "resistance", 120))

    def test_research_guard_rejects_orders_or_false_provenance(self):
        prefix, features = analyze_prefix(self.frame, 25)
        with self.assertRaises(ValueError):
            commentary_report(prefix, features, {**self.meta, "orders_enabled": True})
        with self.assertRaises(ValueError):
            commentary_report(prefix, features, {**self.meta, "feed_verified": True})
        with self.assertRaises(ValueError):
            commentary_report(prefix.iloc[:0], features, self.meta)

    def test_repeated_calls_are_deterministic(self):
        prefix, features = analyze_prefix(self.frame, 110)
        self.assertEqual(commentary_report(prefix, features, self.meta),
                         commentary_report(prefix, features, self.meta))


if __name__ == "__main__":
    unittest.main()
