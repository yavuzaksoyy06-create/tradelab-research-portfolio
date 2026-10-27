"""Independent pinned local trust and role-aware chronology, synthetic only."""
import copy,hashlib,unittest
from research_macro.tests.test_events import completed_event,pending_event,predictive_event,DOCUMENT,SOURCE
from research_macro.events import (require_integrity_verified,EventLicenseError,EventTimestampError,
                                  EventSchemaError,canonical_event_mapping,validate_macro_event,event_record_digest,is_in_sample)
from research_macro.documents import registry_digest
from research_macro.availability import response_label_available

def verified_fixture(**event_changes):
    data=b"SYNTHETIC test statement; no actual publisher data"
    doc=dict(DOCUMENT,sha256=hashlib.sha256(data).hexdigest(),bytes_size=len(data),integrity_verified=False)
    event=completed_event(document=doc,**event_changes)
    registry={"schema_version":1,"documents":{doc["url"]:{"source_id":SOURCE["source_id"],
        "sha256":doc["sha256"],"bytes_size":len(data),"reviewer":"synthetic-reviewer",
        "review_reference":"synthetic-offline-trust-anchor","reviewed_at":"2026-10-24T12:00:00Z",
        "terms_url":SOURCE["access_terms_url"],"allowed_uses":["local_descriptive_research"]}}}
    inputs={"document_bytes":data,"trust_registry":registry,"registry_sha256":registry_digest(registry),
            "verified_at":"2026-10-24T13:00:00Z"}
    return event,inputs

class DocumentVerificationTests(unittest.TestCase):
    def test_real_byte_check_does_not_trust_false_or_true_flag(self):
        event,inputs=verified_fixture()
        evidence=require_integrity_verified(event,**inputs)
        self.assertEqual(evidence.document_sha256,hashlib.sha256(inputs["document_bytes"]).hexdigest())
        self.assertEqual(evidence.event_digest,event.record_digest)
    def test_corrupted_bytes_rejected(self):
        event,inputs=verified_fixture();inputs["document_bytes"]+=b"corrupt"
        with self.assertRaises(EventLicenseError):require_integrity_verified(event,**inputs)
    def test_registry_tampering_not_self_authorizing(self):
        event,inputs=verified_fixture()
        inputs["trust_registry"]["documents"][event.document.url]["sha256"]="c"*64
        with self.assertRaisesRegex(EventLicenseError,"pin mismatch"):require_integrity_verified(event,**inputs)
    def test_self_declared_event_hash_does_not_replace_trust_anchor(self):
        event,inputs=verified_fixture();inputs.pop("trust_registry")
        with self.assertRaises(EventLicenseError):require_integrity_verified(event,**inputs)
    def test_wrong_trusted_document_hash(self):
        event,inputs=verified_fixture();inputs["trust_registry"]["documents"][event.document.url]["sha256"]="c"*64
        inputs["registry_sha256"]=registry_digest(inputs["trust_registry"])
        with self.assertRaises(EventLicenseError):require_integrity_verified(event,**inputs)
    def test_review_scope_and_evidence_required(self):
        for field,value in (("allowed_uses",["ml_training"]),("review_reference",""),("terms_url","https://other.example/")):
            event,inputs=verified_fixture();inputs["trust_registry"]["documents"][event.document.url][field]=value
            inputs["registry_sha256"]=registry_digest(inputs["trust_registry"])
            with self.subTest(field=field),self.assertRaises(EventLicenseError):require_integrity_verified(event,**inputs)
    def test_verification_chronology(self):
        event,inputs=verified_fixture();inputs["verified_at"]="2026-01-01T00:00:00Z"
        with self.assertRaises(EventLicenseError):require_integrity_verified(event,**inputs)
    def test_url_credentials_http_and_bad_port_rejected(self):
        for url in ("http://www.federalreserve.gov/x","https://name@www.federalreserve.gov/x",
                    "https://www.federalreserve.gov:bad/x","https://federalreserve.gov.evil.example/x"):
            with self.subTest(url=url),self.assertRaises(EventLicenseError):completed_event(document=dict(DOCUMENT,url=url))
    def test_terms_fragment_not_reviewed(self):
        with self.assertRaises(EventLicenseError):completed_event(source=dict(SOURCE,access_terms_url=SOURCE["access_terms_url"]+"#different"))
    def test_no_blanket_training_rights(self):
        with self.assertRaises(EventLicenseError):completed_event(source=dict(SOURCE,usage_policy="all_uses"))
    def test_older_background_reference_valid(self):
        event=completed_event(document=dict(DOCUMENT,role="background",published_at="2020-01-01T00:00:00Z",fetched_at="2020-01-02T00:00:00Z"))
        self.assertTrue(is_in_sample(event))
    def test_background_fetch_before_publication_invalid(self):
        with self.assertRaises(EventTimestampError):completed_event(document=dict(DOCUMENT,role="background",fetched_at="2020-01-01T00:00:00Z"))
    def test_schedule_document_can_precede_event(self):
        self.assertIsNone(pending_event().actual_release_ts)
    def test_v2_rejected_explicitly(self):
        event=completed_event();mapping=canonical_event_mapping(event);mapping["schema_version"]=2
        mapping["record_digest"]=event.record_digest
        with self.assertRaisesRegex(EventSchemaError,"unsupported schema"):validate_macro_event(mapping)
    def test_new_nested_fields_hashed_and_strict(self):
        event=completed_event();mapping=canonical_event_mapping(event)
        mapping["document"]["role"]="background"
        self.assertNotEqual(event_record_digest(mapping),event.record_digest)
        mapping["document"]["extra"]=True;mapping["record_digest"]=event_record_digest(mapping)
        with self.assertRaises(EventSchemaError):validate_macro_event(mapping)
    def test_eligibility_not_label_availability(self):
        event=completed_event(response_window_end="2026-10-25T00:00:00Z")
        self.assertTrue(is_in_sample(event));self.assertFalse(response_label_available(event))
    def test_delayed_price_availability(self):
        event=completed_event()
        self.assertTrue(response_label_available(event))
        self.assertFalse(response_label_available(event,observations_available_at=["2026-10-25T00:00:00Z"]))
    def test_predictive_target_separate_from_features(self):
        event=predictive_event(prediction_horizon_end="2026-10-25T00:00:00Z")
        self.assertFalse(response_label_available(event))
