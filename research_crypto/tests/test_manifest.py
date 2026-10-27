"""Stage 2 tests: crypto data manifest & integrity engine (manifest.py).

All fixtures are synthetic and live in temporary directories created with
``tempfile.TemporaryDirectory`` (deleted after every test). Dataset bytes are
tiny deterministic CSV-shaped payloads — never real market data.
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_crypto.manifest import (
    CANONICAL_BAR_OPEN_CONVENTION,
    DigestMismatchError,
    FundingError,
    FundingTerms,
    ManifestError,
    ManifestRecord,
    MAX_MAINTENANCE_WINDOWS,
    PathSafetyError,
    SchemaError,
    SchemaVersionError,
    SUPPORTED_SCHEMA_VERSIONS,
    SUPPORTED_SYMBOLS,
    SUPPORTED_TIMEFRAMES,
    build_manifest,
    canonical_manifest_bytes,
    manifest_digest,
    parse_manifest,
    validate_manifest,
    verify_dataset,
)
from research_crypto.calendar import (
    BarAlignmentError,
    EmptyIntervalError,
    NaiveTimestampError,
    expected_grid,
)

UTC = timezone.utc
START = "2026-01-01T00:00:00Z"
END = "2026-01-01T06:00:00Z"          # [start,end) → 6 hourly opens
CREATED = "2026-01-02T08:00:00Z"
PROVENANCE = {
    "producer": "TradeLab test producer",
    "feed": "synthetic template klines",
    "requested_window": "2026-01-01 UTC +00:00..06:00",
    "collected_on": "2026-01-01T06:30:00Z",
}
FAKE_SHA = "a" * 64
FAKE_BYTES = 42


def make_dataset_bytes(kind="btc"):
    header = {"btc": "timestamp,open,high,low,close,volume", "eth": "timestamp,open,high,low,close,volume"}[kind]
    rows = []
    for hour in range(6):
        rows.append(f"2026-01-01T{hour:02d}:00:00Z,{48000 + hour},48001,47900,48000 + hour,120.5")
    return (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")


def real_sha(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def good_fixture(dataset=FAKE_SHA, size=FAKE_BYTES, **overrides):
    params = dict(
        provider="TestProducer",
        venue="TestVenue",
        market_type="spot",
        symbol="BTC/USDT",
        base="BTC",
        quote="USDT",
        timeframe="1h",
        start=START,
        end=END,
        created_at=CREATED,
        dataset_file="data/btc_usdt.csv",
        dataset_sha256=dataset,
        dataset_bytes=size,
        expected_bars=6,
        observed_bars=6,
        provenance=PROVENANCE,
    )
    params.update(overrides)
    return build_manifest(**params)


def write_dataset(tmp: Path, payload: bytes, ref="data/btc_usdt.csv"):
    path = tmp / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return real_sha(payload), len(payload)


class BuildDigestTests(unittest.TestCase):
    def test_build_then_validate_round_trip(self):
        manifest = good_fixture()
        record = validate_manifest(manifest)
        self.assertIsInstance(record, ManifestRecord)
        self.assertEqual(record.symbol, "BTC/USDT")
        self.assertEqual(record.market_type, "spot")

    def test_digest_is_deterministic(self):
        one = good_fixture()
        two = good_fixture()
        self.assertEqual(manifest_digest(one), manifest_digest(two))
        self.assertEqual(one["digest"], two["digest"])

    def test_digest_ignores_key_order(self):
        base = good_fixture()
        shuffled = {key: base[key] for key in reversed(list(base))}
        self.assertEqual(manifest_digest(shuffled), manifest_digest(base))

    def test_canonical_bytes_exclude_digest_and_are_ascii(self):
        manifest = good_fixture(provenance={"producer": "Prøducer-Ω"})  # unicode producer
        payload = canonical_manifest_bytes(manifest)
        self.assertFalse(payload.startswith(b"{") and b'"digest"' in payload)
        self.assertNotIn('"digest"', payload.decode("ascii"))  # digest never hashed
        payload.decode("ascii")  # ASCII-safe by construction
        self.assertIn(b'"producer":"Pr\\u00f8ducer-\\u03a9"', payload)

    def test_digest_changes_when_created_at_changes(self):
        changed = good_fixture()
        changed.pop("digest")
        changed["created_at"] = "2026-01-02T09:00:00Z"
        changed["digest"] = manifest_digest(changed)
        self.assertNotEqual(changed["digest"], good_fixture()["digest"])

    def test_record_is_immutable(self):
        record = validate_manifest(good_fixture())
        with self.assertRaises(Exception):
            record.symbol = "ETH/USDT"


class ValidationRejectTests(unittest.TestCase):
    def test_missing_required_field(self):
        manifest = good_fixture()
        manifest.pop("created_at")
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("created_at", str(caught.exception))

    def test_unknown_field_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["notes"] = "extra"
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError):
            validate_manifest(manifest)

    def test_unsupported_schema_version(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["schema_version"] = 2
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaVersionError) as caught:
            validate_manifest(manifest)
        self.assertIn("supported", str(caught.exception))

    def test_boolean_schema_version_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["schema_version"] = True
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaVersionError):
            validate_manifest(manifest)

    def test_naive_created_at_rejected(self):
        with self.assertRaises(NaiveTimestampError):
            good_fixture(created_at=datetime(2026, 1, 2, 8, 0))

    def test_empty_range_rejected(self):
        with self.assertRaises(EmptyIntervalError):
            good_fixture(end=START)

    def test_unaligned_boundary_rejected(self):
        with self.assertRaises(BarAlignmentError):
            good_fixture(start="2026-01-01T00:30:00Z")

    def test_inconsistent_expected_bar_count(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["expected_bars"] = 7
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(ManifestError) as caught:
            validate_manifest(manifest)
        self.assertIn("computed 6", str(caught.exception))

    def test_observed_exceeding_expected_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["observed_bars"] = 7
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_invalid_digest_format_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["digest"] = "XYZ-not-hex"
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_uppercase_digest_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["digest"] = "A" * 64
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_tampered_manifest_detected(self):
        manifest = good_fixture()
        manifest["provider"] = "DifferentProducer"  # flip a field without resealing
        with self.assertRaises(DigestMismatchError):
            validate_manifest(manifest)

    def test_maintenance_windows_consistent_count(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["maintenance_windows"] = [["2026-01-01T04:00:00Z", "2026-01-01T05:00:00Z"]]
        manifest["expected_bars"] = 5
        manifest["observed_bars"] = 5
        manifest["digest"] = manifest_digest(manifest)
        record = validate_manifest(manifest)
        self.assertEqual(record.expected_bars, 5)

    def test_maintenance_windows_count_mismatch(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["maintenance_windows"] = [["2026-01-01T04:00:00Z", "2026-01-01T05:00:00Z"]]
        # expected_bars stays 6 although the window removes the 04:00 bar.
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(ManifestError):
            validate_manifest(manifest)

    def test_bad_maintenance_window_shape(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["maintenance_windows"] = [["2026-01-01T04:00:00Z"]]
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError):
            validate_manifest(manifest)

    def test_reversed_maintenance_window_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["maintenance_windows"] = [["2026-01-01T05:00:00Z", "2026-01-01T04:00:00Z"]]
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(Exception):
            validate_manifest(manifest)


class HeaderRuleTests(unittest.TestCase):
    def test_unsupported_symbol(self):
        with self.assertRaises(SchemaError):
            good_fixture(symbol="SOL/USDT", base="SOL")

    def test_symbol_currency_inconsistency(self):
        with self.assertRaises(SchemaError):
            good_fixture(symbol="BTC/USDT", base="ETH")

    def test_unsupported_timeframe(self):
        with self.assertRaises(SchemaError):
            good_fixture(timeframe="7m")

    def test_bad_market_type(self):
        with self.assertRaises(SchemaError):
            good_fixture(market_type="option")


class SpotPerpFundingTests(unittest.TestCase):
    def test_spot_with_funding_rejected(self):
        with self.assertRaises(FundingError):
            good_fixture(funding={"interval_hours": 8, "applied": False})

    def test_spot_without_funding_accepted(self):
        record = validate_manifest(good_fixture())
        self.assertEqual(record.market_type, "spot")

    def test_perp_requires_funding(self):
        with self.assertRaises(FundingError):
            good_fixture(market_type="perp")

    def test_perp_with_insufficient_funding_rejected(self):
        with self.assertRaises(FundingError):
            good_fixture(market_type="perp", funding={"interval_hours": 8})

    def test_perp_with_unknown_funding_keys_rejected(self):
        with self.assertRaises(FundingError):
            good_fixture(
                market_type="perp",
                funding={"interval_hours": 8, "applied": True, "taker_fee": 0.1},
            )

    def test_perp_with_funding_accepted(self):
        record = validate_manifest(good_fixture(
            market_type="perp", funding={"interval_hours": 8, "applied": True}
        ))
        self.assertEqual(record.market_type, "perp")

    def test_perp_funding_meta_survives_to_record(self):
        # Reproduced finding #1: validate_manifest dropped funding metadata.
        record = validate_manifest(good_fixture(
            market_type="perp", funding={"interval_hours": 8, "applied": False}
        ))
        self.assertIsInstance(record.funding, FundingTerms)
        self.assertEqual(record.funding.interval_hours, 8)
        self.assertEqual(record.funding.applied, False)

    def test_perp_funding_record_is_immutable(self):
        record = validate_manifest(good_fixture(
            market_type="perp", funding={"interval_hours": 8, "applied": False}
        ))
        with self.assertRaises(Exception):
            record.funding.applied = True
        with self.assertRaises(Exception):
            record.funding = FundingTerms(interval_hours=1, applied=True)

    def test_spot_record_funding_is_none(self):
        record = validate_manifest(good_fixture())
        self.assertIsNone(record.funding)


class PathSafetyAndContentTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "dataset_root"
        self.root.mkdir()
        self.addCleanup(self._tmp.cleanup)

    def test_happy_dataset_verification(self):
        payload = make_dataset_bytes()
        sha, size = write_dataset(self.root, payload)
        manifest = good_fixture(dataset=sha, size=size)
        record = validate_manifest(manifest)
        verified = verify_dataset(record, self.root)
        self.assertEqual(verified.sha256, sha)
        self.assertFalse(verified.empty)
        self.assertEqual(verified.bytes, size)

    def test_file_tampering_detected(self):
        payload = make_dataset_bytes()
        sha, size = write_dataset(self.root, payload)
        record = validate_manifest(good_fixture(dataset=sha, size=size))
        dataset_path = self.root / "data/btc_usdt.csv"
        tampered = byte_array_push(dataset_path.read_bytes())
        dataset_path.write_bytes(tampered)
        with self.assertRaises(DigestMismatchError):
            verify_dataset(record, self.root)

    def test_empty_dataset_rejected(self):
        write_dataset(self.root, b"")
        # Manifest validation itself enforces numeric positivity; here a
        # manifest claims 1 byte while the real file is 0 bytes — verify_dataset
        # must reject it as empty rather than fall through to a size mismatch.
        manifest = good_fixture(dataset=real_sha(b""), size=1)
        with self.assertRaises(ManifestError) as caught:
            verify_dataset(validate_manifest(manifest), self.root)
        self.assertIn("empty", str(caught.exception).lower())

    def test_byte_size_mismatch_detected(self):
        payload = make_dataset_bytes()
        sha, size = write_dataset(self.root, payload)
        record = validate_manifest(good_fixture(dataset=sha, size=size + 1))
        with self.assertRaises(ManifestError) as caught:
            verify_dataset(record, self.root)
        self.assertIn("byte size mismatch", str(caught.exception))

    def test_missing_dataset_file_rejected(self):
        record = validate_manifest(good_fixture())
        with self.assertRaises(PathSafetyError):
            verify_dataset(record, self.root)

    def test_path_traversal_rejected_at_build_time(self):
        write_dataset(self.root, make_dataset_bytes(), ref="btc_usdt.csv")
        with self.assertRaises(PathSafetyError):
            good_fixture(dataset_file="../btc_usdt.csv")

    def test_absolute_path_rejected_at_build_time(self):
        with self.assertRaises(PathSafetyError):
            good_fixture(dataset_file="C:/etc/passwd")

    def test_backslash_reference_rejected_at_build_time(self):
        with self.assertRaises(PathSafetyError):
            good_fixture(dataset_file="data\\btc_usdt.csv")

    def test_reviewer_reproduced_unsafe_references_rejected(self):
        # Reproduced finding #2: these escaped manifest build/validation and
        # were only caught later by verify_dataset. All must fail closed
        # during build, without touching any filesystem.
        for bad_ref in ("../private.csv", "C:/secrets.csv", "/etc/passwd",
                        "data/../outside.csv"):
            with self.subTest(ref=bad_ref):
                with self.assertRaises(PathSafetyError):
                    good_fixture(dataset_file=bad_ref)

    def test_unsafe_references_rejected_at_validation_time(self):
        # Malformed references smuggled into a resealed manifest dict must
        # also fail validation, not survive until dataset verification.
        for bad_ref in ("../private.csv", "C:/secrets.csv", "data/../outside.csv"):
            with self.subTest(ref=bad_ref):
                manifest = good_fixture()
                manifest.pop("digest")
                manifest["dataset"] = dict(manifest["dataset"], file=bad_ref)
                manifest["digest"] = manifest_digest(manifest)
                with self.assertRaises(PathSafetyError):
                    validate_manifest(manifest)

    def test_symlink_escape_rejected(self):
        try:
            outside_target = Path(self._tmp.name) / "outside_secret.csv"
            outside_target.write_bytes(b"corsair data")
            dataset_path = self.root / "data"
            dataset_path.mkdir()
            link = dataset_path / "escape.csv"
            os.symlink(outside_target, link)
        except OSError:
            self.skipTest("os.symlink unavailable in this environment")
        sha = real_sha(b"corsair data")
        record = validate_manifest(good_fixture(
            dataset_file="data/escape.csv", dataset=sha,
        ))
        with self.assertRaises(PathSafetyError):
            verify_dataset(record, self.root)

    def test_provenance_credential_key_rejected(self):
        with self.assertRaises(SchemaError) as caught:
            good_fixture(provenance={"producer": "x", "api_key": "S3CR3T"})
        self.assertIn("credential", str(caught.exception).lower())

    def test_duplicate_json_keys_rejected(self):
        text = '{"schema_version": 1, "schema_version": 1}'
        with self.assertRaises(SchemaError) as caught:
            parse_manifest(text)
        self.assertIn("duplicate", str(caught.exception).lower())

    def test_conflicting_dataset_reference_rejected(self):
        manifest = good_fixture()  # validated eagerly by build_manifest
        manifest.pop("digest")
        manifest["file"] = "data/btc_usdt.csv"  # legacy alias must conflict
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("conflicting dataset reference", str(caught.exception))

    def test_parse_manifest_round_trip(self):
        manifest = good_fixture()
        reparsed = parse_manifest(json.dumps(manifest))
        self.assertEqual(reparsed["digest"], manifest["digest"])


class AuditRemediationTests(unittest.TestCase):
    """Regression tests for the independent Stage 1/2 code audit findings."""

    def test_null_maintenance_windows_rejected(self):
        # Reproduced finding #3: null was silently treated as no maintenance.
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["maintenance_windows"] = None
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("null", str(caught.exception))

    def test_non_list_maintenance_windows_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["maintenance_windows"] = "04:00-05:00"
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError):
            validate_manifest(manifest)

    def test_credential_like_provenance_key_variants_rejected(self):
        # Reproduced finding #4: api-key / private_key / access_token
        # bypassed the sensitive-key set via separator/name variants.
        for key in ("api-key", "private_key", "access_token", "API Token",
                    "secret_key", "x-password"):
            with self.subTest(key=key):
                with self.assertRaises(SchemaError) as caught:
                    good_fixture(
                        provenance={"producer": "x", key: "SYNTHETIC_PLACEHOLDER"}
                    )
                self.assertIn("credential", str(caught.exception).lower())

    def test_noncredential_provenance_keys_still_accepted(self):
        manifest = good_fixture(
            provenance={"producer": "x", "key_rotation_policy": "quarterly",
                        "author_signature_note": "unsigned fixture"}
        )
        record = validate_manifest(manifest)
        self.assertEqual(record.provenance["key_rotation_policy"], "quarterly")

    def test_star_import_does_not_raise(self):
        # Reproduced finding #5: __all__ listed DATASET_FIELD_ALIASES while
        # the name was undefined, so star-importing exploded.
        namespace = {}
        exec("from research_crypto.manifest import *", namespace)
        self.assertIn("DATASET_FIELD_ALIASES", namespace)
        self.assertIn("FundingTerms", namespace)
        self.assertIn("MAX_GRID_SPAN_HOURS", namespace)

    def test_same_instant_different_offset_same_digest(self):
        # Reproduced finding #6: identical instants through different UTC
        # offsets produced diverging digests. Canonical UTC Z normalization
        # makes them byte-identical payloads.
        offset = timezone(timedelta(hours=1))
        one = good_fixture()
        two = good_fixture(
            start=datetime(2026, 1, 1, 1, 0, tzinfo=offset),
            end=datetime(2026, 1, 1, 7, 0, tzinfo=offset),
            created_at=datetime(2026, 1, 2, 9, 0, tzinfo=offset),
        )
        self.assertEqual(one["start"], "2026-01-01T00:00:00Z")
        self.assertEqual(one["digest"], two["digest"])
        self.assertEqual(
            canonical_manifest_bytes(one), canonical_manifest_bytes(two)
        )

    def test_noncanonical_serialized_timestamp_rejected(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["start"] = "2026-01-01T02:00:00+02:00"  # same instant, non-Z
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("canonical UTC Z", str(caught.exception))

    def test_non_string_manifest_key_typed_error(self):
        # Reproduced finding #7a: an integer key leaked a raw TypeError.
        manifest = good_fixture()
        manifest.pop("digest")
        manifest[1] = "malformed"
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("keys must be strings", str(caught.exception))

    def test_non_string_dataset_key_typed_error(self):
        manifest = good_fixture()
        manifest.pop("digest")
        manifest["dataset"] = dict(manifest["dataset"])
        manifest["dataset"][2] = "malformed"
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("keys must be strings", str(caught.exception))

    def test_grid_span_limit_enforced(self):
        # Reproduced finding #7b: an unbounded range forced grid
        # materialization of ~840k hour bars.
        with self.assertRaises(SchemaError) as caught:
            good_fixture(start="1800-01-01T00:00:00Z")
        self.assertIn("supported limit", str(caught.exception))

    def test_maintenance_window_count_limit_enforced(self):
        manifest = good_fixture()
        manifest.pop("digest")
        windows = [["2026-01-01T04:00:00Z", "2026-01-01T05:00:00Z"]] * (
            MAX_MAINTENANCE_WINDOWS + 1
        )
        manifest["maintenance_windows"] = windows
        manifest["digest"] = manifest_digest(manifest)
        with self.assertRaises(SchemaError) as caught:
            validate_manifest(manifest)
        self.assertIn("supported limit", str(caught.exception))


def byte_array_push(payload: bytes) -> bytes:
    """Deterministic tamper helper: flip the last byte's lowbit content."""
    if not payload:
        return b"X"
    return payload[:-1] + bytes([payload[-1] ^ 0x51])


if __name__ == "__main__":
    unittest.main()
