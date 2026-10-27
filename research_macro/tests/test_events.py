"""Event Registry v2 tests — all fixtures synthetic; no network, no data.

Audit remediation coverage (Parts A–F): each reproduces a confirmed defect,
regression-style, and fixes are validated. Fixture vocabulary is synthetic;
the 2026-10-24 cutoff governs sample-membership tests.
"""
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import asdict

from research_macro.events import (
    ARCHIVABLE_LICENSE_CLASSES,
    EVENT_TYPES,
    EventLeakageError,
    EventLicenseError,
    EventSchemaError,
    EventTimestampError,
    MacroEvent,
    SAMPLE_CUTOFF_UTC,
    SCHEMA_VERSION,
    build_macro_event,
    canonical_event_mapping,
    event_record_digest,
    is_in_sample,
    is_predictive_eligible,
    require_integrity_verified,
    validate_macro_event,
)
from research_crypto.manifest import canonical_utc_text

UTC = timezone.utc


def ts(year, month, day, hour, minute=0):
    return canonical_utc_text(datetime(year, month, day, hour, minute, tzinfo=UTC), "t")


SCHEDULED = "2026-01-28T19:00:00Z"   # FOMC statement, 14:00 ET in January (EST)
RELEASE = "2026-01-28T19:00:00Z"
AVAIL = "2026-01-28T19:00:01Z"
FEATURE = "2026-01-28T20:00:00Z"     # upstream/research marker (no constraint)
WIN_START = "2026-01-28T20:00:00Z"
WIN_END = "2026-01-28T20:45:00Z"
STUDY_WIN_START = "2026-01-28T18:30:00Z"   # audit Part A window (straddles release)
STUDY_WIN_END = "2026-01-28T19:30:00Z"
DECISION = "2026-01-28T18:00:00Z"     # one hour before the announcement
PFEATURE = "2026-01-28T17:30:00Z"     # pre-announcement feature snapshot
HOR_START = "2026-01-28T19:00:00Z"
HOR_END = "2026-01-28T19:45:00Z"

SOURCE = {
    "source_id": "FRB_FOMC",
    "publisher": "Federal Reserve Board",
    "license_class": "US-GOV-PD",
    "verification": "catalog_verified",
    "access_terms_url": "https://www.federalreserve.gov/aboutthefed/contact-us-topics.htm",
    "verified_at": "2026-10-24T12:00:00Z",
    "usage_policy": "local_descriptive_research",
}
DOCUMENT = {
    "source_id": "FRB_FOMC",
    "url": "https://www.federalreserve.gov/example/synthetic-statement.htm",
    "fetched_at": ts(2026, 1, 28, 19, 2),
    "fetch_authorized": True,
    "sha256": "b" * 64,
    "bytes_size": 4096,
    "integrity_verified": True,
    "content_type": "text/html",
    "role": "announcement",
    "published_at": RELEASE,
}


def ts(year, month, day, hour, minute=0):
    return canonical_utc_text(datetime(year, month, day, hour, minute, tzinfo=UTC), "t")


def completed_event(**overrides):
    kwargs = dict(
        event_id="FOMC-2026-01-28-STMT",
        event_type="FOMC_STATEMENT",
        meeting_kind="regular",
        research_mode="explanatory_event_study",
        scheduled_event_ts=SCHEDULED,
        actual_release_ts=RELEASE,
        information_available_ts=AVAIL,
        feature_available_ts=FEATURE,
        response_window_start=WIN_START,
        response_window_end=WIN_END,
        source=dict(SOURCE),
        document=dict(DOCUMENT),
    )
    kwargs.update(overrides)
    if "document" not in overrides and kwargs["actual_release_ts"]:
        kwargs["document"]["published_at"] = canonical_utc_text(kwargs["actual_release_ts"],"published")
        available=kwargs["information_available_ts"] or kwargs["actual_release_ts"]
        kwargs["document"]["fetched_at"] = canonical_utc_text(
            datetime.fromisoformat(canonical_utc_text(available,"available").replace("Z","+00:00"))+timedelta(minutes=2),"fetch")
        if kwargs["information_available_ts"] is None:kwargs["document"]["role"]="background"
    elif "document" not in overrides:
        kwargs["document"].update(role="schedule",published_at="2026-01-01T00:00:00Z")
    return build_macro_event(**kwargs)


def pending_event(**overrides):
    return completed_event(**{
        "research_mode": "unclassified",
        "actual_release_ts": None,
        "information_available_ts": None,
        "feature_available_ts": None,
        "response_window_start": None,
        "response_window_end": None,
        "document":dict(DOCUMENT,role="schedule",published_at="2026-01-01T00:00:00Z"),
        **overrides,
    })


def predictive_event(**overrides):
    base = {
        "research_mode": "predictive",
        "feature_available_ts": PFEATURE,
        "prediction_decision_ts": DECISION,
        "prediction_horizon_start": HOR_START,
        "prediction_horizon_end": HOR_END,
        "response_window_start": None,
        "response_window_end": None,
    }
    return completed_event(**{**base, **overrides})


def as_mapping(record: MacroEvent) -> dict:
    """Rebuild the sealed serialized-mapping form of a record (v2 shape)."""
    return {
        "schema_version": record.schema_version,
        "event": {name: getattr(record, name)
                  for name in ("event_id", "event_type", "meeting_kind",
                               "research_mode", "scheduled_event_ts",
                               "actual_release_ts", "information_available_ts",
                               "feature_available_ts", "prediction_decision_ts",
                               "prediction_horizon_start",
                               "prediction_horizon_end",
                               "response_window_start",
                               "response_window_end")},
        "source": asdict(record.source),
        "document": asdict(record.document),
        "record_digest": record.record_digest,
    }


class BuildDigestTests(unittest.TestCase):
    def test_build_then_validate_round_trip(self):
        record = completed_event()
        self.assertIsInstance(record, MacroEvent)
        self.assertEqual(record.event_type, "FOMC_STATEMENT")
        self.assertEqual(record.meeting_kind, "regular")
        self.assertEqual(record.schema_version, SCHEMA_VERSION)

    def test_digest_is_deterministic(self):
        self.assertEqual(completed_event().record_digest,
                         completed_event().record_digest)

    def test_digest_independent_of_input_offset_spelling(self):
        # Same absolute instants via +01:00 datetimes must hash identically.
        record = completed_event(
            scheduled_event_ts=datetime(2026, 1, 28, 20, tzinfo=timezone(timedelta(hours=1))),
            actual_release_ts=datetime(2026, 1, 28, 20, tzinfo=timezone(timedelta(hours=1))),
            information_available_ts=datetime(2026, 1, 28, 20, 0, 1, tzinfo=timezone(timedelta(hours=1))),
            feature_available_ts=datetime(2026, 1, 28, 21, tzinfo=timezone(timedelta(hours=1))),
            response_window_start=datetime(2026, 1, 28, 21, tzinfo=timezone(timedelta(hours=1))),
            response_window_end=datetime(2026, 1, 28, 21, 45, tzinfo=timezone(timedelta(hours=1))),
        )
        self.assertEqual(record.record_digest, completed_event().record_digest)

    def test_canonical_bytes_are_ascii_sorted_and_versioned(self):
        payload = canonical_event_mapping(completed_event())
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)
        from research_macro.events import canonical_event_bytes
        raw = canonical_event_bytes(completed_event())
        self.assertNotIn(b'"record_digest"', raw)
        raw.decode("ascii")

    def test_digest_changes_when_content_changes(self):
        evolved = completed_event(response_window_start="2026-01-28T20:30:00Z")
        self.assertNotEqual(evolved.record_digest, completed_event().record_digest)

    def test_record_is_immutable(self):
        record = validate_macro_event(as_mapping(completed_event()))
        with self.assertRaises(Exception):
            record.event_type = "FOMC_MINUTES"
        with self.assertRaises(Exception):
            record.source.publisher = "someone else"

    def test_pending_scheduled_event_is_valid(self):
        record = pending_event()
        self.assertIsNone(record.actual_release_ts)
        self.assertFalse(is_in_sample(record))

    def test_is_in_sample_cutoff_completed_vs_future(self):
        past_completed = completed_event()
        upcoming = pending_event(event_id="FOMC-2026-10-28-STMT",
                                 scheduled_event_ts="2026-10-28T18:00:00Z")
        done_recently = completed_event(
            event_id="FOMC-2026-09-16-STMT",
            scheduled_event_ts="2026-09-16T18:00:00Z",
            actual_release_ts="2026-09-16T18:00:00Z",
            information_available_ts="2026-09-16T18:00:01Z",
            response_window_start="2026-09-16T19:00:00Z",
            response_window_end="2026-09-16T19:45:00Z",
            document=dict(DOCUMENT, fetched_at="2026-09-16T18:02:00Z",published_at="2026-09-16T18:00:00Z"))
        self.assertTrue(is_in_sample(past_completed))
        self.assertFalse(is_in_sample(upcoming))          # not yet occurred
        self.assertTrue(is_in_sample(done_recently))       # completed <= cutoff
        self.assertFalse(is_in_sample(done_recently, as_of="2026-01-01T00:00:00Z"))


class ExplanatoryEventStudyTests(unittest.TestCase):
    """Part A/B regressions: observation windows and pre-announcement features."""

    def test_audit_case_window_straddling_release_allowed(self):
        # Repro of the confirmed defect: release 19:00, window 18:30-19:30
        # was rejected with EventLeakageError; explanatory event-study
        # windows MUST be allowed to straddle the release instant.
        record = completed_event(
            feature_available_ts=None,
            response_window_start=STUDY_WIN_START,
            response_window_end=STUDY_WIN_END)
        self.assertEqual(record.response_window_start, STUDY_WIN_START)

    def test_window_starting_before_feature_availability_allowed(self):
        # Old rule (removed): response_window_start >= feature_available_ts.
        record = completed_event(
            response_window_start="2026-01-28T19:30:00Z")   # < FEATURE 20:00
        self.assertEqual(record.response_window_start, "2026-01-28T19:30:00Z")

    def test_genuinely_preannouncement_features_allowed(self):
        # Old rule (removed): feature_available_ts >= information_available_ts
        # rejected prior yields / volatility / regime indicators.
        record = completed_event(feature_available_ts="2026-01-28T18:00:00Z",
                                 response_window_start=None,
                                 response_window_end=None)
        self.assertEqual(record.feature_available_ts, "2026-01-28T18:00:00Z")

    def test_drift_baseline_window_entirely_before_release_allowed(self):
        record = completed_event(response_window_start="2026-01-28T18:00:00Z",
                                 response_window_end="2026-01-28T18:55:00Z")
        self.assertIsNotNone(record.response_window_end)

    def test_explanatory_may_not_carry_predictive_fields(self):
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(research_mode="explanatory_event_study",
                            prediction_decision_ts=DECISION)
        self.assertIn("predictive", str(caught.exception))

    def test_explanatory_requires_completed_release(self):
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(research_mode="explanatory_event_study",
                            actual_release_ts=None,
                            information_available_ts=None)
        self.assertIn("completed release", str(caught.exception))


class PredictiveModeTests(unittest.TestCase):
    """Part A/B regressions: ex-ante decision discipline, both directions."""

    def test_valid_preannouncement_predictive_record(self):
        record = predictive_event()
        self.assertEqual(record.research_mode, "predictive")
        self.assertEqual(record.prediction_decision_ts, DECISION)
        self.assertTrue(is_predictive_eligible(record))

    def test_decision_equal_to_release_rejected(self):
        with self.assertRaises(EventLeakageError) as caught:
            predictive_event(prediction_decision_ts=RELEASE)
        self.assertIn("ex-ante", str(caught.exception))

    def test_decision_after_release_rejected(self):
        with self.assertRaises(EventLeakageError):
            predictive_event(prediction_decision_ts="2026-01-28T19:30:00Z")

    def test_post_decision_features_rejected(self):
        with self.assertRaises(EventLeakageError) as caught:
            predictive_event(feature_available_ts="2026-01-28T18:30:00Z")
        self.assertIn("post-decision", str(caught.exception))

    def test_predictive_may_not_carry_observation_window(self):
        with self.assertRaises(EventSchemaError):
            predictive_event(response_window_start=WIN_START,
                             response_window_end=WIN_END)

    def test_predictive_requires_explicit_fields(self):
        with self.assertRaises(EventSchemaError) as caught:
            predictive_event(prediction_decision_ts=None)
        self.assertIn("prediction_decision_ts", str(caught.exception))

    def test_predictive_pending_release_without_information(self):
        record = predictive_event(actual_release_ts=None,
                                  information_available_ts=None)
        self.assertIsNone(record.information_available_ts)
        self.assertTrue(is_predictive_eligible(record))

    def test_predictive_pending_release_with_information_rejected(self):
        with self.assertRaises(EventLeakageError):
            predictive_event(actual_release_ts=None,
                             information_available_ts=AVAIL)

    def test_horizon_start_before_decision_rejected(self):
        with self.assertRaises(EventTimestampError):
            predictive_event(prediction_horizon_start="2026-01-28T17:00:00Z")

    def test_horizon_pair_must_be_set_together(self):
        with self.assertRaises(EventSchemaError):
            predictive_event(prediction_horizon_end=None)


class SampleCutoffTests(unittest.TestCase):
    """Part C regressions: verifiable as-of sample membership."""

    def test_audit_repro_information_after_cutoff_excluded(self):
        # Reviewer repro: release 2026-01-28, information available
        # 2026-10-25 (after the 2026-10-24 cutoff); v1 returned True.
        record = completed_event(
            information_available_ts="2026-10-25T00:00:00Z")
        self.assertFalse(is_in_sample(record))

    def test_information_availability_required_for_membership(self):
        record = completed_event(information_available_ts=None)
        self.assertFalse(is_in_sample(record))   # unverifiable availability

    def test_late_fetched_document_preserves_retrospective_membership(self):
        # A document fetched years later does NOT make the original release
        # unavailable for retrospective research; release/availability pair
        # is what must be established (fetched_at is never used here).
        record = completed_event(document=dict(
            DOCUMENT, fetched_at="2029-05-01T00:00:00Z"))
        self.assertTrue(is_in_sample(record))

    def test_predictive_feature_eligibility_is_distinct(self):
        record = predictive_event()
        self.assertTrue(is_predictive_eligible(record))
        self.assertTrue(is_in_sample(record))
        later = predictive_event(prediction_decision_ts="2027-06-01T18:00:00Z",
                                 prediction_horizon_start="2027-06-01T20:00:00Z",
                                 prediction_horizon_end="2027-06-01T20:45:00Z",
                                 actual_release_ts="2027-06-01T19:00:00Z",
                                 information_available_ts="2027-06-01T19:00:01Z",
                                 document=dict(DOCUMENT,
                                               published_at="2027-06-01T19:00:00Z",
                                               fetched_at="2027-06-01T19:02:00Z"))
        self.assertFalse(is_predictive_eligible(later))  # decision after cutoff
        self.assertFalse(is_in_sample(later))            # release after cutoff

    def test_explanatory_record_is_never_predictive_eligible(self):
        self.assertFalse(is_predictive_eligible(completed_event()))

    def test_cutoff_constant_unchanged(self):
        self.assertEqual(SAMPLE_CUTOFF_UTC, "2026-10-24T00:00:00Z")


class TemporalLeakageTests(unittest.TestCase):
    def test_release_information_before_release_rejected(self):
        with self.assertRaises(EventLeakageError) as caught:
            completed_event(information_available_ts="2026-01-28T18:59:59Z")
        self.assertIn("before", str(caught.exception))

    def test_post_event_information_without_release_rejected(self):
        with self.assertRaises(EventLeakageError) as caught:
            pending_event(information_available_ts=AVAIL)
        self.assertIn("no actual_release_ts", str(caught.exception))

    def test_response_window_end_before_start_rejected(self):
        with self.assertRaises(EventTimestampError):
            completed_event(response_window_end="2026-01-28T19:59:59Z")

    def test_response_window_half_open_without_pair_rejected(self):
        with self.assertRaises(EventSchemaError):
            completed_event(response_window_end=None)

    def test_release_before_schedule_rejected(self):
        with self.assertRaises(EventTimestampError):
            completed_event(scheduled_event_ts="2026-01-28T19:30:00Z")

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(EventTimestampError):
            completed_event(actual_release_ts=datetime(2026, 1, 28, 19),document=dict(DOCUMENT))

    def test_noncanonical_offset_string_rejected(self):
        with self.assertRaises(EventTimestampError):
            completed_event(actual_release_ts="2026-01-28T20:00:00+01:00")


class StrictSchemaTests(unittest.TestCase):
    """Part D regressions: unknown/absent keys and typed section errors."""

    def test_unknown_nested_event_field_rejected_with_unchanged_digest(self):
        # Exact reviewer repro: an unknown field added to the nested event
        # mapping while the ORIGINAL digest is kept must be rejected, not
        # silently discarded-and-accepted.
        mapping = as_mapping(completed_event())
        mapping["event"]["analyst_note"] = "x"
        with self.assertRaises(EventSchemaError) as caught:
            validate_macro_event(mapping)
        self.assertIn("analyst_note", str(caught.exception))

    def test_unknown_source_and_document_fields_rejected(self):
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(source=dict(SOURCE, editor="someone"))
        self.assertIn("editor", str(caught.exception))
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(document=dict(DOCUMENT, license="maybe"))
        self.assertIn("license", str(caught.exception))

    def test_missing_timestamp_key_rejected_not_interpreted_as_none(self):
        # Reviewer repro: a re-sealed mapping with an absent timestamp key
        # was silently interpreted as None. v2 rejects absent declared keys.
        mapping = as_mapping(completed_event())
        mapping["record_digest"] = event_record_digest(mapping)
        del mapping["event"]["information_available_ts"]
        with self.assertRaises(EventSchemaError) as caught:
            validate_macro_event(mapping)
        self.assertIn("information_available_ts", str(caught.exception))

    def test_wrong_section_type_rejected_as_schema_error(self):
        mapping = as_mapping(completed_event())
        mapping["document"] = ["not", "a", "dict"]
        with self.assertRaises(EventSchemaError) as caught:
            validate_macro_event(mapping)
        self.assertIn("document", str(caught.exception))

    def test_nonstring_key_rejected_as_schema_error(self):
        mapping = as_mapping(completed_event())
        event = dict(mapping["event"])
        event[1] = "x"                      # non-string key
        mapping["event"] = event
        mapping["record_digest"] = "0" * 64  # placeholder; strictness fires first
        with self.assertRaises(EventSchemaError) as caught:
            validate_macro_event(mapping)
        self.assertIn("non-string", str(caught.exception))

    def test_top_level_sections_required_and_typed(self):
        with self.assertRaises(EventSchemaError):
            validate_macro_event("not a mapping")
        record = completed_event()
        mapping = as_mapping(record)
        del mapping["event"]
        with self.assertRaises(EventSchemaError):
            validate_macro_event(mapping)

    def test_unclassified_may_not_carry_research_fields(self):
        with self.assertRaises(EventSchemaError):
            pending_event(feature_available_ts=PFEATURE)

    def test_expired_top_level_section_rejected(self):
        mapping = as_mapping(completed_event())
        mapping["notes"] = "extra"
        with self.assertRaises(EventSchemaError):
            validate_macro_event(mapping)


class CanonicalHashTests(unittest.TestCase):
    """Part E regressions: one canonical representation everywhere."""

    def test_audit_repro_digest_of_record_matches_record_digest(self):
        # Reviewer repro: event_record_digest(record) != record.record_digest
        # in v1 (flat dataclass layout vs nested seal form). v2 fixes this.
        record = completed_event()
        self.assertEqual(event_record_digest(record), record.record_digest)

    def test_digest_of_serialized_mapping_and_reconstruction_match(self):
        record = completed_event()
        mapping = as_mapping(record)
        self.assertEqual(event_record_digest(mapping), record.record_digest)
        r2 = validate_macro_event(mapping)                 # round trip
        self.assertEqual(r2, record)
        self.assertEqual(event_record_digest(r2), record.record_digest)

    def test_changed_field_fails_digest(self):
        mapping = as_mapping(completed_event())
        mapping["event"]["event_id"] = "FOMC-1999-01-01-STMT"
        with self.assertRaises(Exception) as caught:
            validate_macro_event(mapping)
        self.assertIn("mismatch", str(caught.exception))

    def test_v1_and_versionless_records_are_explicitly_rejected(self):
        mapping = as_mapping(completed_event())
        mapping["schema_version"] = 1
        mapping["record_digest"] = "0" * 64  # placeholder; version gate fires first
        with self.assertRaises(EventSchemaError) as caught:
            validate_macro_event(mapping)
        self.assertIn("schema_version", str(caught.exception))
        mapping2 = as_mapping(completed_event())
        del mapping2["schema_version"]
        with self.assertRaises(EventSchemaError):
            validate_macro_event(mapping2)


class SourceTrustTests(unittest.TestCase):
    """Part F regressions: declared metadata is not proof."""

    def test_audit_repro_non_gov_publisher_spoofing_us_gov_class(self):
        with self.assertRaises(EventLicenseError) as caught:
            completed_event(source=dict(SOURCE, publisher="not US government"),
                            document=dict(DOCUMENT,
                                          url="https://not-a-gov.example/doc.htm"))
        self.assertIn("catalog", str(caught.exception))

    def test_uncataloged_source_rejected(self):
        with self.assertRaises(EventLicenseError) as caught:
            completed_event(source=dict(SOURCE, source_id="MYSTERY_GOV"),
                            document=dict(DOCUMENT, source_id="MYSTERY_GOV"))
        self.assertIn("TRUSTED_SOURCE_CATALOG", str(caught.exception))

    def test_publisher_license_pair_must_match_catalog(self):
        # A catalog-verified source_id cannot be combined with a spoofed
        # publisher identity even when the license_class string matches.
        with self.assertRaises(EventLicenseError):
            completed_event(source=dict(SOURCE, source_id="BLS_CPI",
                                        publisher="Federal Reserve Board"),
                            document=dict(DOCUMENT, source_id="BLS_CPI",
                                          url="https://www.bls.gov/x.htm"))

    def test_url_outside_verified_domain_allowlist_rejected(self):
        with self.assertRaises(EventLicenseError) as caught:
            completed_event(document=dict(DOCUMENT,
                                          url="https://not-a-gov.example/"))
        self.assertIn("allowlist", str(caught.exception))

    def test_self_declared_verification_rejected(self):
        with self.assertRaises(EventLicenseError) as caught:
            completed_event(source=dict(SOURCE, verification="self_declared"))
        self.assertIn("self_declared", str(caught.exception))

    def test_declared_sha_is_metadata_until_byte_check(self):
        record = completed_event(
            document=dict(DOCUMENT, integrity_verified=False))
        self.assertFalse(record.document.integrity_verified)   # recordable
        with self.assertRaises(EventLicenseError) as caught:
            require_integrity_verified(record)                 # but not usable
        self.assertIn("declared", str(caught.exception))
        with self.assertRaises(EventLicenseError):
            require_integrity_verified(completed_event())      # True is not evidence

    def test_integrity_flag_must_be_bool(self):
        with self.assertRaises(EventSchemaError):
            completed_event(document=dict(DOCUMENT, integrity_verified=1))

    def test_restricted_and_unknown_license_classes_rejected(self):
        with self.assertRaises(EventLicenseError):
            completed_event(source=dict(SOURCE, license_class="MAGIC-FREE"))
        for restricted in ("FRED-ALFRED-RESTRICTED", "THIRD-PARTY-RESTRICTED"):
            with self.subTest(license=restricted):
                with self.assertRaises(EventLicenseError) as caught:
                    completed_event(source=dict(SOURCE, license_class=restricted))
                self.assertIn("retention", str(caught.exception))
        self.assertEqual(ARCHIVABLE_LICENSE_CLASSES, ("US-GOV-PD",))


class MetadataValidationTests(unittest.TestCase):
    def test_unknown_event_type_rejected(self):
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(event_type="FOMC_RUMOR")
        self.assertIn("unknown event_type", str(caught.exception))
        self.assertNotIn("FOMC_RUMOR", EVENT_TYPES)

    def test_unknown_meeting_kind_and_mode_rejected(self):
        with self.assertRaises(EventSchemaError):
            completed_event(meeting_kind="webcast_only")
        with self.assertRaises(EventSchemaError):
            completed_event(research_mode="hindsight")

    def test_fomc_requires_meeting_kind(self):
        with self.assertRaises(EventSchemaError):
            completed_event(meeting_kind="not_applicable")

    def test_extraordinary_kind_allowed_for_fomc(self):
        record = completed_event(event_id="FOMC-2025-08-22-NOTE",
                                 event_type="FOMC_STATEMENT",
                                 meeting_kind="extraordinary",
                                 response_window_start=None,
                                 response_window_end=None)
        self.assertEqual(record.meeting_kind, "extraordinary")

    def test_empty_event_id_rejected(self):
        with self.assertRaises(EventSchemaError):
            completed_event(event_id="   ")

    def test_invalid_source_reference_rejected(self):
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(document=dict(DOCUMENT, source_id="BLS_CPI"))
        self.assertIn("invalid source reference", str(caught.exception))

    def test_unauthorized_fetch_rejected(self):
        with self.assertRaises(EventLicenseError):
            completed_event(document=dict(DOCUMENT, fetch_authorized=False))

    def test_malformed_sha256_rejected(self):
        with self.assertRaises(EventSchemaError):
            completed_event(document=dict(DOCUMENT, sha256="XYZ"))
        with self.assertRaises(EventSchemaError):
            completed_event(document=dict(DOCUMENT, sha256="A" * 64))

    def test_zero_or_negative_bytes_size_rejected(self):
        with self.assertRaises(EventSchemaError):
            completed_event(document=dict(DOCUMENT, bytes_size=0))

    def test_non_http_url_rejected(self):
        with self.assertRaises(EventSchemaError):
            completed_event(document=dict(DOCUMENT, url="ftp://example.com/x"))

    def test_missing_document_field_typed_error(self):
        doc = dict(DOCUMENT)
        doc.pop("content_type")
        with self.assertRaises(EventSchemaError) as caught:
            completed_event(document=doc)
        self.assertIn("content_type", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
