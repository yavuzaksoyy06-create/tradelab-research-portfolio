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
        with patch('research_workspace.real_data_ui.reports',return_value={'coverage':[],'reconciliation':[]}) as report:
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
