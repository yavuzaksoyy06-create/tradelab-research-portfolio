from pathlib import Path
import unittest,tempfile,json,hashlib
from research_workspace.evidence import stored_tests,protected_artifacts,prospective_restrictions,historical_status

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.directory=self.root/'evidence';self.directory.mkdir()
        p=self.root/'research_macro/events.py';p.parent.mkdir();p.write_text('fixture')
        self.record={'label':'test','recorded_at':'2026-01-01T00:00:00Z','source_sha256':{'research_macro/events.py':hashlib.sha256(p.read_bytes()).hexdigest()},
            'suites':{'example':{'tests':1,'failures':0,'errors':0,'skipped':0,'exit_code':0}}}
    def tearDown(self):self.temp.cleanup()
    def save(self):
        p=self.directory/'result.json';p.write_text(json.dumps(self.record))
        (self.directory/'index.json').write_text(json.dumps({'records':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}))
    def test_missing_results_not_green(self):self.assertEqual(stored_tests(self.directory,self.root)['status'],'not_run')
    def test_valid_record(self):
        self.save();self.assertEqual(stored_tests(self.directory,self.root)['status'],'passed')
    def test_changed_source_stales_evidence(self):
        self.save();(self.root/'research_macro/events.py').write_text('changed')
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'stale')
    def test_failed_test_remains_failed(self):
        self.record['suites']['example'].update(failures=1,exit_code=1);self.save()
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'failed')
    def test_tampered_report_unavailable(self):
        self.save();(self.directory/'result.json').write_text('{}')
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'unavailable')
    def test_null_count_not_success(self):
        self.record['suites']['example']['tests']=None;self.save()
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'unavailable')
    def test_missing_execution_metadata_not_green(self):
        self.record.pop('recorded_at');self.save()
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'unavailable')
    def test_naive_execution_time_not_green(self):
        self.record['recorded_at']='2026-01-01';self.save()
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'unavailable')
    def test_source_path_escape_rejected(self):
        self.record['source_sha256']={'../private.py':'0'*64};self.save()
        self.assertEqual(stored_tests(self.directory,self.root)['status'],'unavailable')
    def test_missing_historical_data(self):self.assertEqual(historical_status(self.root)['status'],'unavailable')
    def test_missing_protection_not_green(self):self.assertEqual(protected_artifacts(self.root)['status'],'unavailable')
    def test_missing_gate_does_not_authorize(self):
        result=prospective_restrictions(self.root)
        self.assertFalse(result['evaluation_enabled']);self.assertFalse(result['time_gate_passed'])
