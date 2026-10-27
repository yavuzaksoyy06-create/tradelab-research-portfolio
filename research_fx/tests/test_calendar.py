import unittest
from dataclasses import replace
from datetime import timedelta
from research_fx.calendar import HoursProfile, CalendarError, expected_grid, utc, Bar, validate_bars

PROFILE = HoursProfile('synthetic-provider', '1', 'Synthetic hours, not reviewed live provider hours')

def grid(a, b, **kwargs):
    return expected_grid(a, b, symbol=kwargs.pop('symbol', 'EUR/USD'), profile=kwargs.pop('profile', PROFILE), **kwargs)

class CalendarTests(unittest.TestCase):
    def test_spring_sunday_open_is_21_utc(self):
        self.assertEqual(grid('2026-03-08T20:00Z', '2026-03-08T22:00Z')[0], utc('2026-03-08T21:00Z'))
    def test_winter_sunday_open_is_22_utc(self):
        self.assertEqual(grid('2026-03-01T21:00Z', '2026-03-01T23:00Z')[0], utc('2026-03-01T22:00Z'))
    def test_fall_sunday_open_is_22_utc(self):
        self.assertEqual(grid('2026-11-01T21:00Z', '2026-11-01T23:00Z')[0], utc('2026-11-01T22:00Z'))
    def test_pre_fall_open_is_21_utc(self):
        self.assertEqual(grid('2026-10-25T20:00Z', '2026-10-25T22:00Z')[0], utc('2026-10-25T21:00Z'))
    def test_friday_close_excludes_partial_bar(self):
        p = replace(PROFILE, friday_close_minute=17*60+5)
        self.assertEqual(grid('2026-10-23T20:45Z', '2026-10-23T21:30Z', profile=p), (utc('2026-10-23T20:45Z'),))
    def test_weekend_closed(self):
        self.assertEqual(grid('2026-10-24T00:00Z', '2026-10-25T20:00Z'), ())
    def test_sunday_partial_open_excluded(self):
        p = replace(PROFILE, sunday_open_minute=17*60+5)
        self.assertEqual(grid('2026-10-25T21:00Z', '2026-10-25T22:00Z', profile=p)[0], utc('2026-10-25T21:15Z'))
    def test_daily_rollover_partial_bar(self):
        self.assertEqual(grid('2026-10-19T20:45Z', '2026-10-19T21:30Z'),
                         (utc('2026-10-19T20:45Z'), utc('2026-10-19T21:15Z')))
    def test_winter_rollover(self):
        self.assertNotIn(utc('2026-01-19T22:00Z'), grid('2026-01-19T21:45Z', '2026-01-19T22:30Z'))
    def test_no_maintenance_profile(self):
        self.assertEqual(len(grid('2026-10-19T21:00Z', '2026-10-19T21:30Z', profile=replace(PROFILE, maintenance_minutes=0))), 2)
    def test_explicit_holiday(self):
        p = replace(PROFILE, closures=(('2026-10-20T00:00Z', '2026-10-21T00:00Z'),))
        self.assertEqual(grid('2026-10-20T00:00Z', '2026-10-21T00:00Z', profile=p), ())
    def test_tiny_closure_invalidates_whole_bar(self):
        p = replace(PROFILE, closures=(('2026-10-20T12:07Z', '2026-10-20T12:08Z'),))
        self.assertEqual(grid('2026-10-20T12:00Z', '2026-10-20T12:30Z', profile=p), (utc('2026-10-20T12:15Z'),))
    def test_exact_boundary_does_not_remove_neighbour(self):
        p = replace(PROFILE, closures=(('2026-10-20T12:15Z', '2026-10-20T12:30Z'),))
        self.assertEqual(grid('2026-10-20T12:00Z', '2026-10-20T12:45Z', profile=p), (utc('2026-10-20T12:00Z'), utc('2026-10-20T12:30Z')))
    def test_three_symbols_same_profile(self):
        for symbol in ('EUR/USD', 'USD/JPY', 'GBP/USD'):
            self.assertEqual(len(grid('2026-10-20T12:00Z', '2026-10-20T13:00Z', symbol=symbol)), 4)
    def test_timezone_normalized(self):
        self.assertEqual(grid('2026-10-20T08:00-04:00', '2026-10-20T09:00-04:00'), grid('2026-10-20T12:00Z', '2026-10-20T13:00Z'))
    def test_naive_rejected(self):
        with self.assertRaises(CalendarError): grid('2026-10-20T12:00', '2026-10-20T13:00Z')
    def test_unaligned_rejected(self):
        with self.assertRaises(CalendarError): grid('2026-10-20T12:01Z', '2026-10-20T13:00Z')
    def test_bounded_range(self):
        for a, b in [('2026-10-21T12:00Z', '2026-10-20T13:00Z'), ('2025-01-01T00:00Z', '2027-01-01T00:00Z')]:
            with self.assertRaises(CalendarError): grid(a, b)
    def test_bad_symbol_interval_profile(self):
        for kwargs in ({'symbol':'SPY'}, {'minutes':True}, {'minutes':7}, {'profile':None}):
            with self.assertRaises(CalendarError): grid('2026-10-20T12:00Z', '2026-10-20T13:00Z', **kwargs)
    def test_invalid_profiles(self):
        for kwargs in ({'provider':''}, {'version':''}, {'assumptions':''}, {'rollover_minute':90}, {'maintenance_minutes':-1}, {'closures':(('2026-01-02T00:00Z','2026-01-01T00:00Z'),)}):
            with self.assertRaises(CalendarError): replace(PROFILE, **kwargs)
    def test_profile_digest_deterministic_and_sensitive(self):
        self.assertEqual(PROFILE.digest, replace(PROFILE).digest)
        self.assertNotEqual(PROFILE.digest, replace(PROFILE, version='2').digest)
        self.assertEqual(grid('2026-03-01T00:00Z', '2026-03-10T00:00Z'), grid('2026-03-01T00:00Z', '2026-03-10T00:00Z'))

class BarValidationTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = '2026-10-20T12:00Z', '2026-10-20T13:00Z'
        self.bars = [Bar(t, 100, 102, 99, 101, 10, t+timedelta(minutes=15)) for t in grid(self.a, self.b)]
    def check(self, bars, **kwargs):
        return validate_bars(bars, self.a, self.b, symbol='EUR/USD', profile=PROFILE, as_of=kwargs.get('as_of', self.b))
    def test_valid_complete(self): self.assertTrue(self.check(self.bars).valid)
    def test_missing_not_filled(self): self.assertEqual(len(self.check(self.bars[1:]).missing), 1)
    def test_duplicate_detected(self): self.assertEqual(len(self.check(self.bars+[self.bars[-1]]).duplicates), 1)
    def test_order_not_repaired(self): self.assertFalse(self.check(list(reversed(self.bars))).ordered)
    def test_off_grid_detected(self):
        self.assertTrue(self.check([replace(self.bars[0], timestamp=utc('2026-10-20T11:00Z'))]).unexpected)
    def test_invalid_ohlcv(self):
        for kwargs in ({'open':float('nan')}, {'high':99}, {'low':102}, {'close':0}, {'volume':-1}, {'open':True}):
            with self.subTest(kwargs=kwargs): self.assertTrue(self.check([replace(self.bars[0], **kwargs)]).invalid)
    def test_late_observation(self): self.assertTrue(self.check(self.bars, as_of='2026-10-20T12:59Z').invalid)
    def test_available_before_close_invalid(self):
        self.assertTrue(self.check([replace(self.bars[0], available_at=self.bars[0].timestamp)]).invalid)
    def test_malformed_bar_detected(self): self.assertTrue(self.check([None]).invalid)
    def test_naive_bar_timestamp_detected(self):
        self.assertTrue(self.check([replace(self.bars[0], timestamp=self.bars[0].timestamp.replace(tzinfo=None))]).invalid)

if __name__ == '__main__': unittest.main()
