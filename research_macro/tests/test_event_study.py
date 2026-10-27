import unittest
from dataclasses import replace, asdict
from datetime import timedelta
from research_macro.tests.test_document_verification import verified_fixture
from research_macro.event_study import (Instrument, SessionGrid, Observation, StudyError,
                                        fx_session_grid, study_event)
from research_macro.events import EventLicenseError
from research_fx.calendar import HoursProfile, utc

PROFILE = HoursProfile('synthetic', '1', 'Synthetic calendar fixture only')

class EventStudyTests(unittest.TestCase):
    def setUp(self):
        self.event, self.verification = verified_fixture(response_window_start='2026-01-28T18:30:00Z',
                                                        response_window_end='2026-01-28T19:30:00Z')
        self.grid = fx_session_grid(self.event.response_window_start, self.event.response_window_end,
                                    symbol='EUR/USD', profile=PROFILE)
        self.bars = [Observation(t, 100+i, 101+i, t+timedelta(minutes=15)) for i,t in enumerate(self.grid.opens)]
        self.options = dict(instrument=Instrument('EUR/USD', 'fx', 'USD', 'synthetic midpoint'),
                            grid=self.grid, as_of='2026-10-24T00:00:00Z', source_reference='synthetic-fixture-v1',
                            synthetic=True, verification_inputs=self.verification)
    def evaluate(self, bars=None, **options):
        return study_event(self.event, self.bars if bars is None else bars, **(self.options | options))
    def test_raw_straddling_and_pre_post_returns(self):
        result = self.evaluate()
        self.assertEqual(result.status, 'available')
        self.assertAlmostEqual(result.raw_return, .04)
        self.assertAlmostEqual(result.pre_release_return, .02)
        self.assertAlmostEqual(result.post_release_return, 104/102-1)
    def test_preannouncement_window_is_valid_retrospectively(self):
        self.event, self.verification = verified_fixture(response_window_start='2026-01-28T18:00:00Z', response_window_end='2026-01-28T18:30:00Z')
        grid = fx_session_grid(self.event.response_window_start,self.event.response_window_end,symbol='EUR/USD',profile=PROFILE)
        bars=[Observation(t,100,101,t+timedelta(minutes=15)) for t in grid.opens]
        result=self.evaluate(bars,grid=grid,verification_inputs=self.verification)
        self.assertEqual(result.status,'available');self.assertIsNone(result.post_release_return)
    def test_incomplete_window_gate(self):
        result=self.evaluate(as_of='2026-01-28T19:15:00Z')
        self.assertEqual(result.status,'not_yet_available');self.assertIsNone(result.raw_return)
    def test_exact_window_end_allowed(self):
        self.assertEqual(self.evaluate(as_of='2026-01-28T19:30:00Z').status,'available')
    def test_event_not_known_yet(self):
        self.assertEqual(self.evaluate(as_of='2026-01-28T18:59:59Z').status,'not_yet_available')
    def test_delayed_observation_blocks_label(self):
        bars=self.bars[:-1]+[replace(self.bars[-1],available_at='2026-10-25T00:00:00Z')]
        self.assertEqual(self.evaluate(bars).status,'not_yet_available')
    def test_missing_observations_never_filled(self):
        result=self.evaluate(self.bars[1:])
        self.assertEqual(result.status,'missing_observations');self.assertEqual(len(result.missing),1)
        self.assertIsNone(result.raw_return)
    def test_full_session_closure(self):
        result=self.evaluate([],grid=replace(self.grid,opens=()))
        self.assertEqual(result.status,'session_closure');self.assertEqual(result.closed_bar_count,4)
        self.assertIsNone(result.raw_return)
    def test_partial_closure_not_bridged(self):
        result=self.evaluate(self.bars[:1]+self.bars[2:],grid=replace(self.grid,opens=self.grid.opens[:1]+self.grid.opens[2:]))
        self.assertEqual(result.status,'session_closure');self.assertEqual(result.closed_bar_count,1)
    def test_fx_rollover_join(self):
        self.event, self.verification=verified_fixture(response_window_start='2026-01-28T21:45:00Z',response_window_end='2026-01-28T22:30:00Z')
        grid=fx_session_grid(self.event.response_window_start,self.event.response_window_end,symbol='EUR/USD',profile=PROFILE)
        bars=[Observation(t,100,101,t+timedelta(minutes=15)) for t in grid.opens]
        self.assertEqual(self.evaluate(bars,grid=grid,verification_inputs=self.verification).status,'session_closure')
    def test_duplicate_rejected(self):
        with self.assertRaises(StudyError):self.evaluate(self.bars+[self.bars[-1]])
    def test_unsorted_rejected(self):
        with self.assertRaises(StudyError):self.evaluate(list(reversed(self.bars)))
    def test_unexpected_bar_rejected(self):
        with self.assertRaises(StudyError):self.evaluate(self.bars,grid=replace(self.grid,opens=self.grid.opens[1:]))
    def test_invalid_prices_rejected(self):
        for price in (0,-1,float('nan'),float('inf'),True):
            with self.subTest(price=price),self.assertRaises(StudyError):self.evaluate([replace(self.bars[0],open=price)]+self.bars[1:])
    def test_unfinished_bar_rejected(self):
        with self.assertRaises(StudyError):self.evaluate([replace(self.bars[0],available_at=self.bars[0].timestamp)]+self.bars[1:])
    def test_window_cannot_be_shortened_to_hide_missing(self):
        with self.assertRaises(StudyError):self.evaluate(self.bars[1:],grid=replace(self.grid,start=self.grid.opens[1],opens=self.grid.opens[1:]))
    def test_symbol_mismatch_rejected(self):
        with self.assertRaises(StudyError):self.evaluate(instrument=Instrument('USD/JPY','fx','JPY','mid'))
    def test_cross_market_metadata_is_retained(self):
        for symbol,asset,currency,basis in [('USD/JPY','fx','JPY','mid'),('SPY','equity','USD','unadjusted'),('QQQ','equity','USD','adjusted'),('BTC/USD','crypto','USD','spot'),('ETH/USD','crypto','USD','spot')]:
            instrument=Instrument(symbol,asset,currency,basis)
            result=self.evaluate(instrument=instrument,grid=replace(self.grid,symbol=symbol,calendar_reference='explicit-synthetic-session'))
            self.assertEqual(result.provenance['instrument'],asdict(instrument))
    def test_no_real_data_mode(self):
        with self.assertRaises(StudyError):self.evaluate(synthetic=False)
    def test_document_bytes_still_required(self):
        with self.assertRaises(EventLicenseError):self.evaluate(verification_inputs={})
    def test_source_reference_required(self):
        with self.assertRaises(StudyError):self.evaluate(source_reference='')
    def test_deterministic_and_price_sensitive_provenance(self):
        a=self.evaluate();self.assertEqual(asdict(a),asdict(self.evaluate()))
        b=self.evaluate(self.bars[:-1]+[replace(self.bars[-1],close=105)])
        self.assertNotEqual(a.provenance['observations_sha256'],b.provenance['observations_sha256'])
        self.assertEqual(a.provenance['verification']['event_digest'],self.event.record_digest)
    def test_bad_session_grids_rejected(self):
        for kwargs in ({'opens':tuple(reversed(self.grid.opens))},{'opens':self.grid.opens+self.grid.opens[:1]},
                       {'minutes':True},{'start':self.grid.end},{'calendar_sha256':'no-digest'},
                       {'opens':(utc('2026-01-28T18:31:00Z'),)}):
            with self.subTest(kwargs=kwargs),self.assertRaises(StudyError):replace(self.grid,**kwargs)
    def test_instrument_metadata_required(self):
        for args in [('SPY','unknown','USD','raw'),('SPY','equity','','raw'),('OTHER','fx','USD','mid')]:
            with self.assertRaises(StudyError):Instrument(*args)

if __name__=='__main__':unittest.main()
