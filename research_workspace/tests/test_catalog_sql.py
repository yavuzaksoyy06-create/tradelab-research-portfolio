import copy
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from research_workspace.catalog_sql import _database, reports, COVERAGE_SQL, RECONCILIATION_SQL

def fixture():
    return {'version':'fixture_1','status':'verified','verified':True,'available':True,
            'manifest':{'source':'fixture','collected_at':'2026-01-03T00:00:00+00:00','rows':2},
            'source':{'publisher':'Synthetic fixture','unit':'reference units'},
            'rows':[{'date':'2026-01-01','series':'A','value':1.0},
                    {'date':'2026-01-02','series':'A','value':2.0}]}

class CatalogSQLTests(unittest.TestCase):
    def database(self,entries):
        db=_database(entries);self.addCleanup(db.close);return db
    def test_join_and_grouped_coverage(self):
        db=self.database([fixture()]);r=dict(db.execute(COVERAGE_SQL).fetchone())
        self.assertEqual((r['observations'],r['first_date'],r['last_date']),(2,'2026-01-01','2026-01-02'))
        self.assertEqual(r['publisher'],'Synthetic fixture')
    def test_rejected_rows_never_loaded(self):
        bad={'version':'bad','status':'rejected','error':'hash mismatch','rows':fixture()['rows']}
        db=self.database([bad]);r=dict(db.execute(RECONCILIATION_SQL).fetchone())
        self.assertEqual(r['loaded_rows'],0);self.assertIsNone(r['row_count_matches'])
        self.assertEqual(db.execute(COVERAGE_SQL).fetchall(),[])
    def test_duplicate_key_rejected(self):
        e=fixture();e['rows'][1]=copy.deepcopy(e['rows'][0])
        with self.assertRaises(sqlite3.IntegrityError):_database([e])
    def test_count_mismatch_rejected(self):
        e=fixture();e['manifest']['rows']=3
        with self.assertRaises(ValueError):_database([e])
    def test_unavailable_or_unverified_rejected(self):
        for field in ('available','verified'):
            e=fixture();e[field]=False
            with self.assertRaises(ValueError):_database([e])
    def test_sql_injection_is_literal_data(self):
        e=fixture();e['rows'][0]['series']="x'); DROP TABLE observations;--"
        db=self.database([e])
        self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
    def test_database_is_readonly_after_loading(self):
        db=self.database([fixture()])
        with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM observations')
        self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)
    def test_conflicting_source_rejected(self):
        e=fixture();e['version']='fixture_2';e['source']['unit']='different'
        with self.assertRaises(ValueError):_database([fixture(),e])
    def test_reverification_on_every_request(self):
        with patch('research_workspace.catalog_sql.catalog',side_effect=[[],[fixture()]]) as reader:
            self.assertEqual(reports()['coverage'],[])
            r=reports();self.assertEqual(len(r['coverage']),1)
            self.assertFalse(r['persistent_database']);self.assertFalse(r['evaluation_enabled'])
            self.assertEqual(reader.call_count,2)
    def test_versions_kept_separate(self):
        e=fixture();e['version']='fixture_2'
        db=self.database([fixture(),e]);rows=db.execute(COVERAGE_SQL).fetchall()
        self.assertEqual(len(rows),2);self.assertEqual([r['observations'] for r in rows],[2,2])
    def test_ui_requests_report_only_on_click(self):
        app=Path(__file__).resolve().parents[1]/'app.py'
        with patch('research_workspace.real_data_ui.reports',return_value={**reports(), 'coverage':[], 'reconciliation':[]}) as report:
            at=AppTest.from_file(str(app),default_timeout=60).run()
            at.radio(key='page').set_value('Gerçek Veri').run();report.assert_not_called()
            at.button(key='sql_catalog_report').click().run()
            self.assertFalse(at.exception);report.assert_called_once()
    def test_ui_error_does_not_claim_success(self):
        app=Path(__file__).resolve().parents[1]/'app.py'
        with patch('research_workspace.real_data_ui.reports',side_effect=ValueError('Manifest row count mismatch')):
            at=AppTest.from_file(str(app),default_timeout=60).run()
            at.radio(key='page').set_value('Gerçek Veri').run()
            at.button(key='sql_catalog_report').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(any('SQL raporu doğrulanamadı' in e.value for e in at.error))

class QualityTests(unittest.TestCase):
    def report(self, rows, version='one', extras=()):
        entry=fixture();entry['version']=version;entry['rows']=rows;entry['manifest']['rows']=len(rows)
        with patch('research_workspace.catalog_sql.catalog',return_value=[entry,*extras]):
            return reports()
    def row(self, day, series='A', value=1):
        return {'date':day,'series':series,'value':value}
    def test_missing_observed_grid_includes_boundary(self):
        r=self.report([self.row('2026-01-01'),self.row('2026-01-02'),self.row('2026-01-02','B')])
        self.assertEqual(r['missing_observations'],[{'version_id':'one','series':'B','observation_date':'2026-01-01'}])
        self.assertEqual(r['quality'][1]['absent_on_observed_dates'],1)
        self.assertEqual(r['calendar_completeness'],'unknown')
    def test_weekend_gap_not_missing_observation(self):
        r=self.report([self.row('2026-01-02'),self.row('2026-01-05')])
        self.assertEqual(r['missing_observations_total'],0)
        self.assertEqual(r['calendar_gaps'][0]['intervening_calendar_days'],2)
    def test_all_series_absent_day_not_inferred(self):
        r=self.report([self.row('2026-01-01'),self.row('2026-01-03')])
        self.assertEqual(r['missing_observations'],[])
        self.assertEqual(r['calendar_gaps_total'],1)
    def test_value_summary_not_error_classification(self):
        r=self.report([self.row('2026-01-01',value=0),self.row('2026-01-02',value=3)])
        q=r['quality'][0];self.assertEqual((q['minimum_value'],q['maximum_value'],q['zero_values']),(0,3,1))
    def test_versions_and_rejections_isolated(self):
        e=fixture();e['version']='other'
        r=self.report([self.row('2026-02-01','B')],extras=[e,{'version':'bad','status':'rejected','error':'hash mismatch'}])
        self.assertEqual(r['missing_observations_total'],0)
        self.assertEqual(len(r['quality']),2)
    def test_empty_unknown_not_complete(self):
        with patch('research_workspace.catalog_sql.catalog',return_value=[]):r=reports()
        self.assertEqual(r['quality'],[]);self.assertEqual(r['calendar_gaps_total'],0)
        self.assertEqual(r['calendar_completeness'],'unknown')
    def test_detail_cap_preserves_exact_total(self):
        from datetime import date,timedelta
        rows=[self.row((date(2025,1,1)+timedelta(days=i)).isoformat()) for i in range(503)]
        rows.append(self.row('2025-01-01','B'))
        r=self.report(rows)
        self.assertEqual(r['missing_observations_total'],502)
        self.assertEqual(len(r['missing_observations']),500)
        self.assertTrue(r['missing_observations_truncated'])
    def test_single_observation_has_no_gap(self):
        r=self.report([self.row('2026-01-01')])
        self.assertEqual(r['calendar_gaps'],[])
        self.assertEqual(r['missing_observations'],[])
