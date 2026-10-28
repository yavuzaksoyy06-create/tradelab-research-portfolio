from pathlib import Path
import math
import unittest
from unittest.mock import patch
import pandas as pd
from streamlit.testing.v1 import AppTest
from research_workspace.financial_analytics import treasury,fx,compatibility,export_csv,frame
from research_workspace import real_sources as old

def entry(source,rows,version='synthetic'):
    days=sorted({d for d,s,v in rows})
    return {'version':version,'status':'verified','verified':True,'available':True,'synthetic':True,'pin':'fixture',
            'source':old.SOURCES[source],'manifest':{'source':source,'source_url':old.SOURCES[source]['url'],
            'collected_at':'2026-10-27T00:00:00+00:00','available_at':'2026-10-27T00:00:00+00:00',
            'rows':len(rows),'first_date':days[0],'last_date':days[-1]},
            'rows':[{'date':d,'series':s,'value':v} for d,s,v in rows]}

def ust():
    return entry('treasury_2025',[(d,s,v) for d,a,b,c in [('2025-02-18',4,4.5,4.8),('2025-02-19',4.1,4.4,4.6)] for s,v in [('BC_10YEAR',a),('BC_2YEAR',b),('BC_3MONTH',c)]])
def rates():
    return entry('ecb_fx',[(d,'EUR/USD',v) for d,v in [('2026-08-03',1),('2026-08-04',1.1),('2026-08-05',1.21),('2026-08-06',1.089)]])

class FinancialTests(unittest.TestCase):
    def test_spread_sign_and_bps(self):
        r=treasury(ust());self.assertAlmostEqual(r['spreads'].iloc[0]['10y_minus_2y_bp'],-50)
        self.assertAlmostEqual(r['spreads'].iloc[0]['10y_minus_3m_bp'],-80)
        self.assertTrue(r['spreads'].iloc[0]['10y_minus_2y_bp_inverted'])
    def test_changes_not_returns(self):
        t=treasury(ust())['changes_bp'];self.assertAlmostEqual(t.iloc[1]['BC_10YEAR'],10)
        self.assertTrue(pd.isna(t.iloc[0]['BC_10YEAR']))
    def test_missing_tenor(self):
        e=ust();e['rows']=[r for r in e['rows'] if r['series']!='BC_3MONTH']
        self.assertTrue(treasury(e)['spreads']['10y_minus_3m_bp'].isna().all())
    def test_missing_cell_no_fill(self):
        e=ust();e['rows']=e['rows'][:-1];r=treasury(e)
        self.assertTrue(pd.isna(r['changes_bp'].iloc[1]['BC_3MONTH']))
    def test_sorted_maturities(self):
        r=treasury(ust());self.assertEqual(list(r['curves'].iloc[:3].maturity_months),[3,24,120])
    def test_fx_manual_returns(self):
        t=fx(rates(),window=2)['table'];self.assertAlmostEqual(t.iloc[1].simple_return_pct,10)
        self.assertAlmostEqual(t.iloc[1].log_return,math.log(1.1))
        self.assertAlmostEqual(t.iloc[2].cumulative_change_pct,21)
        self.assertAlmostEqual(t.iloc[3].simple_return_pct,-10)
    def test_volatility_ddof_and_window(self):
        t=fx(rates(),window=2)['table'];self.assertTrue(pd.isna(t.iloc[1].rolling_log_volatility))
        expected=abs(math.log(1.1)-math.log(.9))/math.sqrt(2)
        self.assertAlmostEqual(t.iloc[3].rolling_log_volatility,expected)
    def test_start_rebases_without_prior_data(self):
        t=fx(rates(),window=2,start='2026-08-05')['table']
        self.assertEqual(t.iloc[0].cumulative_change_pct,0);self.assertTrue(pd.isna(t.iloc[0].simple_return_pct))
    def test_missing_date_breaks_return(self):
        e=rates();e['rows'].pop(1);t=fx(e,window=2)['table']
        self.assertTrue(t.iloc[1].known_missing_interval);self.assertTrue(pd.isna(t.iloc[1].log_return))
    def test_weekend_is_not_zero_return(self):
        e=entry('ecb_fx',[('2026-08-07','EUR/USD',1),('2026-08-10','EUR/USD',1.1)])
        t=fx(e,window=2)['table'];self.assertAlmostEqual(t.iloc[1].simple_return_pct,10)
        self.assertEqual(t.iloc[1].interval_calendar_days,3)
    def test_quote_direction(self):
        self.assertIn('EUR appreciation',fx(rates())['metadata']['quotation'])
    def test_invalid_window_or_start(self):
        for w in [0,1,2.5,True]:
            with self.assertRaises(ValueError):fx(rates(),window=w)
        with self.assertRaises(ValueError):fx(rates(),start='2026-08-02')
    def test_unverified_and_future(self):
        e=rates();e['verified']=False
        with self.assertRaises(ValueError):fx(e)
        e=rates();e['manifest']['available_at']='2099-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):fx(e)
    def test_bad_values_and_duplicates(self):
        for value in [0,-1,float('inf')]:
            e=rates();e['rows'][0]['value']=value
            with self.assertRaises(ValueError):fx(e)
        e=rates();e['rows'].append(e['rows'][0])
        with self.assertRaises(ValueError):fx(e)
    def test_disjoint_dates(self):
        r=compatibility(ust(),rates());self.assertEqual(r['status'],'INSUFFICIENT OVERLAPPING VERIFIED DATES')
        self.assertFalse(r['joint_analysis_enabled'])
    def test_overlap_not_sufficient(self):
        r=compatibility(rates(),rates());self.assertEqual(r['status'],'DEFINITION AND AVAILABILITY REVIEW REQUIRED')
        self.assertFalse(r['point_in_time_enabled'])
    def test_prefix_invariance(self):
        a=rates();b=rates();b['rows']=b['rows'][:3]
        pd.testing.assert_frame_equal(fx(a,window=2)['table'].iloc[:3],fx(b,window=2)['table'])
    def test_version_isolation_and_export(self):
        a=rates();a['version']='one';b=rates();b['version']='two'
        self.assertNotEqual(fx(a)['metadata']['version'],fx(b)['metadata']['version'])
        csv=export_csv(fx(a)['table'],fx(a)['metadata']).decode();self.assertIn('meta_manifest_sha256',csv);self.assertIn('one',csv)
    def test_sql_counts(self):
        self.assertEqual(treasury(ust())['coverage'].observations.sum(),6)

class FinancialUITests(unittest.TestCase):
    def app(self):return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=60)
    def test_no_data_no_fake_chart(self):
        with patch('research_workspace.financial_ui.entries',return_value=[]):
            at=self.app().run();at.radio(key='page').set_value('Financial Analytics').run()
            self.assertFalse(at.exception);self.assertTrue(any('UNAVAILABLE DATA' in x.value for x in at.warning))
            self.assertEqual(len(at.get('plotly_chart')),0)
    def test_treasury_ui_backend_agreement(self):
        with patch('research_workspace.financial_ui.entries',return_value=[ust()]):
            at=self.app().run();at.radio(key='page').set_value('Financial Analytics').run()
            self.assertFalse(at.exception);self.assertTrue(any('SYNTHETIC TEST DATA' in x.value for x in at.info))
            pd.testing.assert_frame_equal(at.dataframe[0].value,treasury(ust())['spreads'])
    def test_fx_ui_backend_agreement(self):
        with patch('research_workspace.financial_ui.entries',return_value=[rates()]):
            at=self.app().run();at.radio(key='page').set_value('Financial Analytics').run()
            at.selectbox(key='financial_view').set_value('ECB FX Analytics').run()
            self.assertFalse(at.exception)
            pd.testing.assert_frame_equal(at.dataframe[0].value,fx(rates(),window=20)['table'])
    def test_rejected_input_not_real(self):
        with patch('research_workspace.financial_ui.entries',return_value=[{'status':'rejected','version':'bad','error':'hash'}]):
            at=self.app().run();at.radio(key='page').set_value('Financial Analytics').run()
            self.assertFalse(at.exception);self.assertTrue(at.error);self.assertFalse(any("REAL VERIFIED REFERENCE DATA" in x.value for x in at.info))
