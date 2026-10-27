import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from research_workspace.adapters import DEMO

APP=Path(__file__).resolve().parents[1]/'app.py'
class WorkspaceUITests(unittest.TestCase):
    def app(self,page='Genel Bakış'):
        at=AppTest.from_file(str(APP),default_timeout=60).run()
        if page!='Genel Bakış':at.radio(key='page').set_value(page).run()
        self.assertFalse(at.exception,[x.message for x in at.exception]);return at
    def test_overview_separates_history_and_demo(self):
        at=self.app();self.assertTrue(any('donmuş' in x.value.lower() for x in at.subheader))
        self.assertTrue(any('Planlanan' in x.value for x in at.caption))
    def test_forex_has_demo_label_and_backend_count(self):
        at=self.app('Forex Takvimi');self.assertTrue(any(DEMO in x.value for x in at.warning))
        self.assertEqual(at.metric[0].value,'95')
    def test_missing_control_changes_count(self):
        at=self.app('Forex Takvimi');at.selectbox(key='fx_scenario').set_value('Eksik mum').run()
        self.assertEqual(at.metric[1].value,'1');self.assertFalse(at.exception)
    def test_weekend_empty_state(self):
        at=self.app('Forex Takvimi');at.selectbox(key='fx_preset').set_value('Hafta sonu').run()
        self.assertEqual(at.metric[0].value,'0');self.assertFalse(at.exception)
    def test_macro_all_cases_work(self):
        at=self.app('Makro Laboratuvarı')
        for case in ('FOMC','CPI','NFP'):
            at.selectbox(key='macro_case').set_value(case).run();self.assertFalse(at.exception)
            self.assertTrue(any(m.label=='Tam pencere' for m in at.metric))
    def test_macro_future_clock_hides_return(self):
        at=self.app('Makro Laboratuvarı');at.selectbox(key='macro_clock').set_value('Duyurudan hemen önce').run()
        self.assertFalse(any(m.label=='Tam pencere' for m in at.metric));self.assertFalse(at.exception)
    def test_broken_document_has_no_result(self):
        at=self.app('Makro Laboratuvarı');at.selectbox(key='macro_scenario').set_value('Bozuk belge').run()
        self.assertTrue(at.error);self.assertFalse(at.exception);self.assertEqual(len(at.metric),0)
    def test_missing_macro_has_no_fake_zero(self):
        at=self.app('Makro Laboratuvarı');at.selectbox(key='macro_scenario').set_value('Eksik gözlem').run()
        self.assertFalse(any(m.label=='Tam pencere' for m in at.metric));self.assertFalse(at.exception)
    def test_audit_gate_and_integrity(self):
        at=self.app('Araştırma Denetimi');self.assertFalse(at.exception)
        self.assertTrue(any('zaman kapısı' in x.value for x in at.warning))
    def test_learning_is_optional_and_separate(self):
        at=self.app();self.assertFalse(any('Öğrenme modu' in x.value for x in at.subheader))
        at.toggle(key='learning').set_value(True).run()
        self.assertTrue(any('HİPOTETİK' in x.value for x in at.info))
        at.selectbox(key='learning_topic').set_value('Beklenen değer').run();self.assertFalse(at.exception)
    def test_no_real_dataset_dependency(self):
        with patch('research_workspace.evidence.historical_status',return_value={'status':'unavailable','missing':['not-present']}):
            at=self.app();self.assertTrue(any('Tarihsel kayıt bulunamıyor' in x.value for x in at.warning))
            at.radio(key='page').set_value('Makro Laboratuvarı').run();self.assertFalse(at.exception)
