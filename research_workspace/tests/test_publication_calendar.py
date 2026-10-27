import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research_workspace.catalog_sql import _database, reports
from research_workspace.publication_calendar import publication_reports, load_profiles

class PublicationTests(unittest.TestCase):
    def entry(self,source,rows,version='v'):
        return {'version':version,'status':'verified','verified':True,'available':True,
                'source':{'publisher':'Synthetic','unit':'test'},
                'manifest':{'source':source,'rows':len(rows),'collected_at':'2026-10-28T00:00:00+00:00'},
                'rows':[{'date':d,'series':s,'value':1} for d,s in rows]}
    def report(self,source,rows):
        db=_database([self.entry(source,rows)]);self.addCleanup(db.close)
        return publication_reports(db)
    def test_reference_schema_and_new_tenor(self):
        p=load_profiles();self.assertEqual(len(p['ecb_fx']['series']),29)
        self.assertEqual(len(p['treasury_2025']['series']),14)
        self.assertEqual(p['treasury_2025']['series']['BC_1_5MONTH']['from'],'2025-02-18')
        self.assertNotIn('BC_30YEARDISPLAY',p['treasury_2025']['series'])
        self.assertNotIn('EUR/RUB',p['ecb_fx']['series'])
    def test_treasury_before_launch(self):
        r=self.report('treasury_2025',[('2025-02-14','BC_1MONTH')])
        self.assertNotIn('BC_1_5MONTH',r['publication_summary'][0]['entirely_absent_series'])
    def test_treasury_after_launch_absent_series(self):
        r=self.report('treasury_2025',[('2025-02-18','BC_1MONTH')])
        self.assertEqual(r['publication_missing_total'],13)
        self.assertIn('BC_1_5MONTH',r['publication_summary'][0]['entirely_absent_series'])
    def test_ecb_entire_day_detected_weekend_excluded(self):
        p=load_profiles()['ecb_fx'];rows=[(d,s) for d in ['2026-07-30','2026-08-03'] for s in p['series']]
        r=self.report('ecb_fx',rows)
        self.assertEqual(r['publication_missing_total'],29)
        self.assertEqual({x['observation_date'] for x in r['publication_missing']},{'2026-07-31'})
    def test_target_holiday_and_office_holiday_distinguished(self):
        p=load_profiles();q=p['ecb_fx'];q['from']='2026-01-01';q['through']='2026-12-31'
        q['series']={'EUR/USD':{'from':q['from'],'through':q['through']}}
        with patch('research_workspace.publication_calendar.load_profiles',return_value=p):
            r=self.report('ecb_fx',[('2026-04-02','EUR/USD'),('2026-04-07','EUR/USD')])
            self.assertEqual(r['publication_missing_total'],0)
            r=self.report('ecb_fx',[('2026-05-13','EUR/USD'),('2026-05-15','EUR/USD')])
            self.assertEqual(r['publication_missing'][0]['observation_date'],'2026-05-14')
    def test_unknown_source_and_outside_range(self):
        for source in ['unknown','ecb_fx']:
            r=self.report(source,[('2024-01-01','X')])
            self.assertEqual(r['publication_summary'][0]['status'],'unknown')
            self.assertIsNone(r['publication_summary'][0]['missing_expected'])
    def test_partial_scope_flag(self):
        r=self.report('ecb_fx',[('2026-07-29','EUR/USD'),('2026-07-30','EUR/USD')])
        self.assertTrue(r['publication_summary'][0]['outside_reference_range'])
        self.assertEqual(r['publication_summary'][0]['scope_from'],'2026-07-30')
    def test_hash_tampering_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text('{}')
            with patch('research_workspace.publication_calendar.REFERENCE',p):
                with self.assertRaisesRegex(ValueError,'hash mismatch'):load_profiles()
    def test_rejected_ignored_and_versions_separate(self):
        entries=[self.entry('treasury_2025',[('2025-02-18','BC_1MONTH')],v) for v in ['a','b']]
        entries.append({'version':'bad','status':'rejected','error':'hash mismatch'})
        with patch('research_workspace.catalog_sql.catalog',return_value=entries):r=reports()
        self.assertEqual(len(r['publication_summary']),2)
        self.assertEqual(r['publication_missing_total'],26)
        self.assertFalse(r['evaluation_enabled'])
    def test_cap_and_unknown_series(self):
        r=self.report('treasury_2025',[('2025-01-02','UNKNOWN'),('2025-12-31','UNKNOWN')])
        self.assertTrue(r['publication_missing_truncated']);self.assertEqual(len(r['publication_missing']),500)
        self.assertEqual(r['publication_missing_total'],249*13+218)
        self.assertEqual(r['publication_summary'][0]['unexpected_series'],['UNKNOWN'])
