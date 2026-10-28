import copy
import unittest
import pandas as pd
from test_financial_analytics import entry, rates, ust
from research_workspace.financial_analytics import treasury,fx,frame,export_csv

class AuditTests(unittest.TestCase):
    def test_treasury_missing_publication_breaks_change(self):
        e=entry('treasury_2025',[('2025-01-02','BC_10YEAR',4),('2025-01-06','BC_10YEAR',4.2)])
        result=treasury(e)
        self.assertTrue(pd.isna(result['changes_bp'].iloc[1]['BC_10YEAR']))
        self.assertTrue(result['spreads'].iloc[1]['known_missing_interval'])
    def test_treasury_weekend_without_missing_day(self):
        e=entry('treasury_2025',[('2025-01-03','BC_10YEAR',4),('2025-01-06','BC_10YEAR',4.2)])
        self.assertAlmostEqual(treasury(e)['changes_bp'].iloc[1]['BC_10YEAR'],20)
    def test_unknown_fx_calendar_not_certified_for_volatility(self):
        e=entry('ecb_fx',[('2024-01-01','EUR/USD',1),('2024-01-03','EUR/USD',1.1),('2024-01-05','EUR/USD',1.2)])
        t=fx(e,window=2)['table']
        self.assertTrue(pd.isna(t.iloc[2].rolling_log_volatility))
        self.assertEqual(t.iloc[2].interval_assessment,'unreviewed_calendar')
    def test_collection_cannot_follow_availability(self):
        e=rates();e['manifest']['collected_at']='2026-10-28T00:00:00+00:00'
        with self.assertRaises(ValueError):fx(e)
    def test_export_records_analytical_revision(self):
        m=fx(rates())['metadata']
        self.assertIn('analytics_sha256',m);self.assertIn('publication_reference_sha256',m)
    def test_export_preserves_synthetic_classification(self):
        self.assertTrue(fx(rates())['metadata']['synthetic'])
    def test_export_string_dtype_formula(self):
        df=pd.DataFrame({'label':pd.Series(['=1+1','\t=1+1'],dtype='string')})
        csv=export_csv(df,{}).decode()
        self.assertIn("'=1+1",csv);self.assertIn("'\t=1+1",csv)
    def test_calendar_reference_coverage_in_changes_export(self):
        t=treasury(ust())['changes_bp']
        self.assertIn('previous_observed_date',t.columns)
        self.assertIn('interval_assessment',t.columns)
