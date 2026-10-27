"""Stage 1 tests: 24/7 UTC research calendar (research_crypto.calendar).

Synthetic timestamps only; no network, no market data, standard library only.
Every test is deterministic — DST is handled by construction (internal time is
UTC), and no test depends on the local machine's timezone or clock.
"""
import unittest
from datetime import datetime, timedelta, timezone

from research_crypto import SYMBOLS, resolve_symbol
from research_crypto.calendar import (
    BarAlignmentError,
    CalendarError,
    EmptyIntervalError,
    MaintenanceWindowError,
    NaiveTimestampError,
    as_utc,
    expected_grid,
    merge_maintenance_windows,
    validate_bars,
)

from research_crypto.calendar import HOUR

DT = datetime
UTC = timezone.utc


def jan(day, hour, minute=0):
    """Utility: a UTC bar-open instant on the first days of January 2026."""
    return DT(2026, 1, day, hour, minute, tzinfo=UTC)


def grid_of(count, start=DT(2026, 1, 1, tzinfo=UTC)):
    return [start + i * HOUR for i in range(count)]


def opens(day, hours):
    return [DT(2026, 1, day, hour, tzinfo=UTC) for hour in hours]


class GridTests(unittest.TestCase):
    def test_half_open_semantics(self):
        # [00:00, 05:00) contains opens 00..04 but not the 05:00 end boundary.
        grid = expected_grid(jan(1, 0), jan(1, 5))
        self.assertEqual(grid[0], jan(1, 0))
        self.assertEqual(grid[-1], jan(1, 4))
        self.assertEqual(len(grid), 5)
        self.assertNotIn(jan(1, 5), grid)

    def test_single_hour_interval_yields_one_open(self):
        grid = expected_grid(jan(1, 7), jan(1, 8))
        self.assertEqual(grid, (jan(1, 7),))

    def test_full_day_has_exactly_24_opens(self):
        grid = expected_grid(jan(1, 0), jan(2, 0))
        self.assertEqual(len(grid), 24)
        self.assertEqual(grid[0], jan(1, 0))
        self.assertEqual(grid[-1], jan(1, 23))

    def test_grid_entries_are_hourly_and_utc(self):
        grid = expected_grid(jan(1, 0), jan(1, 6))
        for earlier, later in zip(grid, grid[1:]):
            self.assertEqual(later - earlier, HOUR)
        for stamp in grid:
            self.assertEqual(stamp.tzname(), "UTC")

    def test_naive_start_rejected(self):
        with self.assertRaises(NaiveTimestampError):
            expected_grid(DT(2026, 1, 1), DT(2026, 1, 2, tzinfo=UTC))

    def test_naive_end_rejected(self):
        with self.assertRaises(NaiveTimestampError):
            expected_grid(DT(2026, 1, 1, tzinfo=UTC), DT(2026, 1, 2))

    def test_non_hour_aligned_start_rejected(self):
        with self.assertRaises(BarAlignmentError):
            expected_grid(jan(1, 0, minute=30), jan(1, 5))

    def test_second_precision_rejected(self):
        with self.assertRaises(BarAlignmentError):
            expected_grid(jan(1, 0), DT(2026, 1, 1, 5, 0, 30, tzinfo=UTC))

    def test_empty_interval_rejected(self):
        with self.assertRaises(EmptyIntervalError):
            expected_grid(jan(1, 4), jan(1, 4))

    def test_reversed_interval_rejected(self):
        with self.assertRaises(EmptyIntervalError):
            expected_grid(jan(1, 6), jan(1, 5))

    def test_aware_non_utc_input_is_normalized(self):
        # +05:30 offset instant 05:30 == 00:00 UTC; grid must equal UTC grid.
        zone = timezone(timedelta(hours=5, minutes=30))
        del zone  # documented offset form is exercised through ISO strings below
        grid = expected_grid("2026-01-01T05:30:00+05:30", "2026-01-01T11:30:00+05:30")
        self.assertEqual(grid, expected_grid(jan(1, 0), jan(1, 6)))
        self.assertEqual(grid[0].utcoffset(), timedelta(0))

    def test_iso_strings_and_z_suffix_accepted(self):
        grid = expected_grid("2026-01-01T00:00:00Z", "2026-01-01T03:00:00+00:00")
        self.assertEqual(grid, (jan(1, 0), jan(1, 1), jan(1, 2)))


class MaintenanceTests(unittest.TestCase):
    def test_window_excludes_interior_opens(self):
        grid = expected_grid(
            jan(1, 0), jan(1, 8), maintenance=((jan(1, 4), jan(1, 7)),)
        )
        self.assertEqual(len(grid), 5)
        self.assertNotIn(jan(1, 4), grid)
        self.assertNotIn(jan(1, 6), grid)
        self.assertIn(jan(1, 3), grid)
        self.assertIn(jan(1, 7), grid)  # half-open window: end open survives

    def test_overlapping_windows_merge(self):
        direct = expected_grid(
            jan(1, 0), jan(1, 12), maintenance=((jan(1, 4), jan(1, 6)), (jan(1, 5), jan(1, 8)))
        )
        merged = expected_grid(jan(1, 0), jan(1, 12), maintenance=((jan(1, 4), jan(1, 8)),))
        self.assertEqual(direct, merged)
        for stamp in opens(1, range(4, 8)):
            self.assertNotIn(stamp, direct)

    def test_adjacent_windows_merge(self):
        windows = merge_maintenance_windows(((jan(1, 2), jan(1, 4)), (jan(1, 4), jan(1, 6))))
        self.assertEqual(windows, ((jan(1, 2), jan(1, 6)),))

    def test_window_outside_grid_has_no_effect(self):
        baseline = expected_grid(jan(1, 0), jan(1, 3))
        affected = expected_grid(jan(1, 0), jan(1, 3), maintenance=((jan(2, 0), jan(2, 4)),))
        self.assertEqual(baseline, affected)

    def test_unordered_window_list_is_deterministic(self):
        compare = expected_grid(jan(1, 0), jan(1, 10), maintenance=((jan(1, 7), jan(1, 9)), (jan(1, 2), jan(1, 3))))
        single = expected_grid(jan(1, 0), jan(1, 10), maintenance=((jan(1, 2), jan(1, 3)), (jan(1, 7), jan(1, 9))))
        self.assertEqual(compare, single)

    def test_reversed_window_rejected(self):
        with self.assertRaises(MaintenanceWindowError):
            expected_grid(jan(1, 0), jan(1, 5), maintenance=((jan(1, 4), jan(1, 3)),))

    def test_empty_window_rejected(self):
        with self.assertRaises(MaintenanceWindowError):
            merge_maintenance_windows(((jan(1, 4), jan(1, 4)),))

    def test_partial_overlap_window_excludes_affected_bars(self):
        # 04:30–05:15 interrupts [04:00,05:00) and [05:00,06:00) → both excluded;
        # 03:00 and 06:00 bars remain expected (no truncation, no synthesis).
        grid = expected_grid(jan(1, 0), jan(1, 8), maintenance=((jan(1, 4, minute=30), jan(1, 5, minute=15)),))
        self.assertNotIn(jan(1, 4), grid)
        self.assertNotIn(jan(1, 5), grid)
        self.assertIn(jan(1, 3), grid)
        self.assertIn(jan(1, 6), grid)
        self.assertEqual(len(grid), 6)

    def test_subhour_window_inside_a_single_bar(self):
        # 04:10–04:50 falls entirely inside [04:00,05:00) → only that bar excluded.
        grid = expected_grid(jan(1, 0), jan(1, 6), maintenance=((jan(1, 4, minute=10), jan(1, 4, minute=50)),))
        self.assertEqual(len(grid), 5)
        self.assertNotIn(jan(1, 4), grid)
        self.assertIn(jan(1, 3), grid)
        self.assertIn(jan(1, 5), grid)

    def test_adjacent_bar_boundary_not_affected_by_partial_window(self):
        # Window ending exactly at 05:00 does not touch [05:00,06:00).
        grid = expected_grid(jan(1, 0), jan(1, 6), maintenance=((jan(1, 3, minute=30), jan(1, 5)),))
        self.assertNotIn(jan(1, 4), grid)   # [04:00,05:00) overlaps [03:30,05:00)
        self.assertNotIn(jan(1, 3), grid)   # [03:00,04:00) overlaps [03:30,05:00)
        self.assertIn(jan(1, 5), grid)      # [05:00,06:00) starts at window end

    def test_partial_window_validation_accepts_affected_gaps(self):
        observed = [stamp for stamp in grid_of(8) if stamp not in (jan(1, 4), jan(1, 5))]
        report = validate_bars(
            observed, jan(1, 0), jan(1, 8),
            maintenance=((jan(1, 4, minute=30), jan(1, 5, minute=15)),),
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.missing, ())

    def test_naive_window_rejected(self):
        with self.assertRaises(NaiveTimestampError):
            merge_maintenance_windows(((DT(2026, 1, 4), DT(2026, 1, 5, tzinfo=UTC)),))

    def test_shapeless_window_rejected(self):
        with self.assertRaises(MaintenanceWindowError):
            merge_maintenance_windows((("2026-01-04T00:00:00Z",),))
        with self.assertRaises(MaintenanceWindowError):
            merge_maintenance_windows(("not-a-pair",))


class ValidationTests(unittest.TestCase):
    def test_clean_sequence_passes(self):
        report = validate_bars(grid_of(24), jan(1, 0), jan(2, 0))
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.expected_count, 24)
        self.assertEqual(report.observed_count, 24)

    def test_missing_open_detected_and_not_filled(self):
        observed = [stamp for stamp in grid_of(24) if stamp != jan(1, 9)]
        report = validate_bars(observed, jan(1, 0), jan(2, 0))
        self.assertFalse(report.ok)
        self.assertEqual(report.missing, (jan(1, 9),))
        self.assertEqual(report.observed_count, 23)  # no silent fill-up to 24
        self.assertIn("missing bar open(s)", str(report.errors))

    def test_missing_examples_capped_for_actionability(self):
        observed = grid_of(24)[:6]
        report = validate_bars(observed, jan(1, 0), jan(2, 0))
        self.assertEqual(len(report.missing), 18)
        self.assertIn("more", " ".join(report.errors))

    def test_duplicate_open_detected(self):
        observed = grid_of(6) + [jan(1, 3)]
        report = validate_bars(observed, jan(1, 0), jan(1, 6))
        self.assertFalse(report.ok)
        self.assertEqual(report.duplicates, ((jan(1, 3), 2),))
        self.assertEqual(report.observed_count, 7)
        self.assertIn("duplicated bar opens", " ".join(report.errors))

    def test_off_grid_open_detected(self):
        report = validate_bars(grid_of(5) + [jan(1, 0, minute=30)], jan(1, 0), jan(1, 5))
        self.assertFalse(report.ok)
        self.assertEqual(report.off_grid, (jan(1, 0, minute=30),))

    def test_unsorted_sequence_detected(self):
        observed = list(reversed(grid_of(6)))
        report = validate_bars(observed, jan(1, 0), jan(1, 6))
        self.assertFalse(report.order_ok)
        self.assertFalse(report.ok)
        self.assertEqual(report.duplicates, ())
        self.assertEqual(report.missing, ())
        self.assertIn("not strictly increasing", " ".join(report.errors))

    def test_maintenance_aware_validation_allows_gap(self):
        observed = [
            stamp for stamp in grid_of(8)
            if not (jan(1, 4) <= stamp < jan(1, 7))
        ]
        report = validate_bars(
            observed, jan(1, 0), jan(1, 8), maintenance=((jan(1, 4), jan(1, 7)),)
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.missing, ())

    def test_naive_observation_records_index(self):
        with self.assertRaises(NaiveTimestampError) as caught:
            validate_bars([jan(1, 0), DT(2026, 1, 1, 1)], jan(1, 0), jan(1, 3))
        self.assertIn("observed[1]", str(caught.exception))

    def test_non_timestamp_observation_rejected(self):
        with self.assertRaises(CalendarError):
            validate_bars([42], jan(1, 0), jan(1, 2))

    def test_error_examples_show_iso_text(self):
        report = validate_bars(grid_of(5) + [jan(1, 0, minute=30)], jan(1, 0), jan(1, 5))
        message = " ".join(report.errors)
        self.assertIn("2026-01-01T00:30:00+00:00", message)


class DesignGuaranteeTests(unittest.TestCase):
    def test_dst_change_sunday_still_has_24_opens(self):
        # US DST began 2026-03-08 (America/New_York); UTC stays continuous.
        sunday = expected_grid(DT(2026, 3, 8, tzinfo=UTC), DT(2026, 3, 9, tzinfo=UTC))
        plain = expected_grid(DT(2026, 3, 15, tzinfo=UTC), DT(2026, 3, 16, tzinfo=UTC))
        self.assertEqual(len(sunday), 24)
        self.assertEqual([s.isoformat()[-9:] for s in sunday], [s.isoformat()[-9:] for s in plain])

    def test_repeated_grid_build_is_identical(self):
        first = expected_grid(jan(1, 0), jan(1, 6), maintenance=((jan(1, 2), jan(1, 3)),))
        second = expected_grid(jan(1, 0), jan(1, 6), maintenance=((jan(1, 2), jan(1, 3)),))
        self.assertEqual(first, second)

    def test_as_utc_keeps_instant_identity(self):
        stamp = as_utc("2026-01-01T05:00:00-05:00")
        self.assertEqual(stamp, DT(2026, 1, 1, 10, tzinfo=UTC))

    def test_symbols_are_limited_to_stage_one(self):
        self.assertEqual(SYMBOLS, ("BTC/USDT", "ETH/USDT"))
        self.assertEqual(resolve_symbol("BTC/USDT"), "BTC/USDT")
        with self.assertRaises(ValueError):
            resolve_symbol("SOL/USDT")


if __name__ == "__main__":
    unittest.main()
