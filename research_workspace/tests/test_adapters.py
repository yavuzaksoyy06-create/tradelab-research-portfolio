import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch
from research_workspace import adapters as a
from research_workspace.charts import forex_chart,event_chart
from research_macro.event_study import study_event
from research_macro.events import EventLicenseError
from research_fx.calendar import expected_grid

class IntegrationTests(unittest.TestCase):
    def test_all_cases_validate_source_compatibility(self):
        for case in a.CASES:
            with self.subTest(case=case):
                f=a.macro_case(case);v=a.macro_view(f,f['grid'].end)
                self.assertEqual(v['result'].status,'available');self.assertTrue(v['event_eligible'])
                self.assertEqual(f['event'].schema_version,3)
    def test_result_matches_existing_engine(self):
        f=a.macro_case();v=a.macro_view(f,f['grid'].end)
        expected=study_event(f['event'],f['bars'],instrument=f['instrument'],grid=f['grid'],as_of=f['grid'].end,
            source_reference='SYNTHETIC teaching fixture v1',synthetic=True,verification_inputs=f['verification'])
        self.assertEqual(v['result'],expected)
    def test_case_window_selection(self):
        f=a.macro_case(before=60,after=15)
        self.assertEqual(len(f['grid'].opens),5)
        self.assertEqual(f['grid'].end-f['grid'].start,timedelta(minutes=75))
    def test_future_window_has_no_return(self):
        f=a.macro_case();v=a.macro_view(f,a.utc(f['event'].actual_release_ts))
        self.assertIsNone(v['result'].raw_return);self.assertFalse(v['event_eligible'])
        self.assertFalse(v['label_temporally_available'])
    def test_unavailable_prices_absent_from_chart_and_table(self):
        f=a.macro_case();cut=a.utc(f['event'].actual_release_ts)-timedelta(seconds=1)
        v=a.macro_view(f,cut)
        self.assertTrue(all(t<=cut for t in v['frame'].available_at))
        for trace in event_chart(v,a.utc(f['event'].actual_release_ts)).data:
            self.assertTrue(all(a.utc(t)<=cut for t in trace.x))
        self.assertNotIn('observations_sha256',v['result'].provenance)
    def test_future_price_mutation_cannot_change_visible_observations(self):
        f=a.macro_case();cut=a.utc(f['event'].actual_release_ts)
        g={**f,'bars':tuple(replace(b,open=9000,close=9001) if a.utc(b.available_at)>cut else b for b in f['bars'])}
        v,w=a.macro_view(f,cut),a.macro_view(g,cut)
        self.assertEqual(v['frame'].to_json(date_format='iso'),w['frame'].to_json(date_format='iso'))
        self.assertEqual(v['result'],w['result'])
    def test_empty_asof_view(self):
        f=a.macro_case();v=a.macro_view(f,f['grid'].start)
        self.assertTrue(v['frame'].empty);self.assertIsNone(v['result'].raw_return)
        self.assertEqual(sum(len(t.x) for t in event_chart(v,a.utc(f['event'].actual_release_ts)).data),0)
    def test_missing_observations_not_filled(self):
        f=a.macro_case(scenario='Eksik gözlem');v=a.macro_view(f,f['grid'].end)
        self.assertEqual(v['result'].status,'missing_observations');self.assertIsNone(v['result'].raw_return)
    def test_closure_is_distinct_from_missing(self):
        f=a.macro_case(scenario='Seans kesintisi');v=a.macro_view(f,f['grid'].end)
        self.assertEqual(v['result'].status,'session_closure');self.assertFalse(v['result'].missing)
    def test_delayed_observation_then_available(self):
        f=a.macro_case(scenario='Gecikmiş fiyat')
        self.assertEqual(a.macro_view(f,f['grid'].end)['result'].status,'not_yet_available')
        self.assertEqual(a.macro_view(f,f['grid'].end+timedelta(hours=1))['result'].status,'available')
    def test_bad_document_prevents_output(self):
        f=a.macro_case(scenario='Bozuk belge')
        with self.assertRaises(EventLicenseError):a.macro_view(f,f['grid'].end)
    def test_three_parities_retain_currency_and_synthetic_price_basis(self):
        for symbol in a.SYMBOLS:
            f=a.macro_case(symbol=symbol)
            self.assertIn('synthetic',f['instrument'].price_basis)
            self.assertEqual(f['instrument'].quote_currency,'JPY' if symbol=='USD/JPY' else 'USD')
    def test_invalid_controls_fail_closed(self):
        for kwargs in ({'case':'OTHER'},{'before':0},{'scenario':'unknown'}):
            with self.assertRaises(ValueError):a.macro_case(**kwargs)
    def test_existing_document_and_availability_functions_called(self):
        f=a.macro_case()
        with patch.object(a,'verify_document_bytes',wraps=a.verify_document_bytes) as verify,patch.object(a,'response_label_available',wraps=a.response_label_available) as gate:
            a.macro_view(f,f['grid'].end);verify.assert_called_once();gate.assert_called_once()

class ForexPresentationTests(unittest.TestCase):
    def view(self,**kwargs):return a.forex_view('2026-01-28T00:00Z','2026-01-29T00:00Z',**kwargs)
    def test_grid_is_exact_backend_output(self):
        v=self.view();g=expected_grid('2026-01-28T00:00Z','2026-01-29T00:00Z',symbol='EUR/USD',profile=a.PROFILE)
        self.assertEqual(v['expected'],g)
        self.assertEqual(tuple(v['frame'].loc[v['frame'].expected,'timestamp']),g)
    def test_maintenance_partial_bar_is_explained(self):
        v=self.view();row=v['frame'].query("status == 'Kısmi rollover bakımı'")
        self.assertEqual(len(row),1);self.assertFalse(row.expected.iloc[0])
    def test_dst_utc_offsets(self):
        for start,end,first in [('2026-03-08T20:00Z','2026-03-08T23:00Z','2026-03-08T21:00Z'),
                                ('2026-11-01T20:00Z','2026-11-01T23:00Z','2026-11-01T22:00Z')]:
            v=a.forex_view(start,end);self.assertEqual(v['expected'][0],a.utc(first))
    def test_partial_sunday_uses_engine(self):
        p=replace(a.PROFILE,sunday_open_minute=1025)
        v=a.forex_view('2026-03-08T21:00Z','2026-03-08T22:00Z',profile=p)
        self.assertEqual(v['frame'].iloc[0].status,'Kısmi seans');self.assertEqual(len(v['expected']),3)
    def test_weekend_not_missing_data(self):
        v=a.forex_view('2026-01-31T00:00Z','2026-02-01T00:00Z')
        self.assertEqual(v['report'].expected_count,0);self.assertFalse(v['report'].missing)
    def test_defect_controls_use_validator(self):
        for scenario,field in [('Eksik mum','missing'),('Tekrarlı mum','duplicates'),('Geçersiz OHLC','invalid'),('Gecikmiş erişim','invalid')]:
            with self.subTest(scenario=scenario):self.assertTrue(getattr(self.view(scenario=scenario)['report'],field))
    def test_time_labels(self):
        labels=a.time_labels('2026-03-08T21:00Z')
        self.assertIn('17:00 EDT',labels['New York']);self.assertIn('00:00',labels['İstanbul'])
    def test_chart_contains_every_slot_once(self):
        v=self.view();fig=forex_chart(v)
        self.assertEqual(sum(len(t.x) for t in fig.data),len(v['frame']))
        self.assertTrue(any(a.DEMO in item.text for item in fig.layout.annotations))
    def test_macro_chart_synthetic_label_no_bridging(self):
        f=a.macro_case(scenario='Eksik gözlem');v=a.macro_view(f,f['grid'].end);fig=event_chart(v,a.utc(f['event'].actual_release_ts))
        self.assertTrue(any(a.DEMO in item.text for item in fig.layout.annotations))
        self.assertTrue(all(t.mode=='markers' for t in fig.data))
    def test_invalid_range(self):
        for end in ('2026-01-28T00:00Z','2026-02-28T00:00Z'):
            with self.assertRaises(ValueError):a.forex_view('2026-01-28T00:00Z',end)
