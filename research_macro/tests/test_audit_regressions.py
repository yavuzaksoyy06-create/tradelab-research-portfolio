"""Five independently reproduced V2 defects; all fixtures are synthetic."""
import importlib.util
import unittest
from research_macro.events import EventLicenseError,EventSchemaError,EventTimestampError,require_integrity_verified
from research_macro.tests.test_events import completed_event,SOURCE,DOCUMENT

class AuditRegressions(unittest.TestCase):
    def test_boolean_is_not_byte_verification(self):
        with self.assertRaises(EventLicenseError):require_integrity_verified(completed_event())
    def test_fomc_cannot_use_cpi_source(self):
        source=dict(SOURCE,source_id="BLS_CPI",publisher="Bureau of Labor Statistics",
                    access_terms_url="https://www.bls.gov/bls/linksite.htm")
        document=dict(DOCUMENT,source_id="BLS_CPI",url="https://www.bls.gov/example/synthetic.htm")
        with self.assertRaises((EventSchemaError,EventLicenseError)):
            completed_event(source=source,document=document)
    def test_unreviewed_terms_url_rejected(self):
        with self.assertRaises(EventLicenseError):
            completed_event(source=dict(SOURCE,access_terms_url="https://unreviewed.example/terms"))
    def test_response_label_gate_is_separate(self):
        self.assertIsNotNone(importlib.util.find_spec("research_macro.availability"),
                             "Missing response-label availability gate")
        from research_macro.availability import response_label_available
        event=completed_event(response_window_end="2026-10-25T00:00:00Z")
        self.assertFalse(response_label_available(event,"2026-10-24T00:00:00Z"))
    def test_announcement_fetched_before_release_rejected(self):
        with self.assertRaises(EventTimestampError):
            completed_event(document=dict(DOCUMENT,fetched_at="2026-01-27T00:00:00Z"))
