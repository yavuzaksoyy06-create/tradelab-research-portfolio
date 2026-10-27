"""TradeLab Macro Event Registry — schema v3 (synthetic, integrity-first, no ML).

Scope (MACRO_RESEARCH_PLAN_031.md revisions 2026-10-24b and 2026-10-24c):
- Typed, immutable event sources, source documents and macro events.
- ONE documented canonical representation (canonical_event_mapping) used by
  both the builder and the validator, so that digest(record) ==
  digest(serialized mapping) == digest(reconstructed mapping) ==
  record.record_digest always (audit Part E).
- Explicit mode separation (audit Part A):
    explanatory_event_study  historical observation windows; windows MAY
                             straddle the release instant and are never
                             constrained by feature availability
    predictive               ex-ante decision discipline: all features were
                             available at/before the decision instant and the
                             decision strictly precedes the announcement
    unclassified             plain schedule/provenance record, no research
                             semantics assigned yet
- feature_available_ts semantics corrected (audit Part B): it is measured
  relative to the model decision time, NOT to the announcement; genuinely
  pre-announcement predictors (prior yields, prior volatility, regime
  indicators) are legitimate. Realized announcement content is still never
  available before its actual release.
- Sample membership (audit Part C): retrospective eligibility requires
  verifiable event release AND information availability by the cutoff;
  document.fetched_at never retroactively removes a historical release from
  the retrospective sample; predictive feature eligibility is a separate,
  explicit check.
- Strict schema (audit Part D): every section declares its exact key set;
  unknown nested fields are rejected (never silently discarded), all keys are
  required to be present (None is allowed only for nullable fields), wrong
  section types and non-string keys raise typed EventSchemaError.
- Source authenticity (audit Part F): declared license/publisher metadata is
  NOT proof of permission; documents may only be recorded against sources
  verified against the trusted source catalog (publisher + license class +
  URL-domain allowlist). A declared SHA-256 string is unverified metadata
  until require_integrity_verified() passes against actual bytes.
- No network, no scraping, no downloads, no predictive ML, no trading.

Project policy: this engine refuses FRED/ALFRED-restricted records fail-closed.
Catalog locators are not a fresh legal review or a blanket permission grant.
Each usable document needs independent, scope-specific local review evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Mapping, Optional, Tuple
from urllib.parse import urlsplit

from research_crypto.calendar import CalendarError
from research_crypto.manifest import canonical_utc_text

__all__ = [
    "ARCHIVABLE_LICENSE_CLASSES",
    "EVENT_TYPES",
    "EVENT_STR_FIELDS",
    "EVENT_TS_FIELDS",
    "EventDigestMismatchError",
    "EventLeakageError",
    "EventLicenseError",
    "EventSchemaError",
    "EventSource",
    "EventTimestampError",
    "MacroEvent",
    "MacroEventError",
    "RESEARCH_MODES",
    "SAMPLE_CUTOFF_UTC",
    "SCHEMA_VERSION",
    "SOURCE_FIELDS",
    "DOCUMENT_FIELDS",
    "SourceDocument",
    "TRUSTED_SOURCE_CATALOG",
    "build_macro_event",
    "canonical_event_bytes",
    "canonical_event_mapping",
    "event_record_digest",
    "is_in_sample",
    "is_predictive_eligible",
    "require_integrity_verified",
    "validate_macro_event",
]

# Explicit sample cutoff (plan revision 2026-10-24b, R5): events not completed
# by this instant (e.g. the 2026-10-27/28 and later FOMC meetings) are excluded
# from the exploratory pilot sample.
SAMPLE_CUTOFF_UTC = "2026-10-24T00:00:00Z"

SCHEMA_VERSION = 3  # explicit document role/publication and usage scope; no silent migration

EVENT_TYPES: Tuple[str, ...] = (
    "FOMC_STATEMENT",
    "FOMC_IMPL_NOTE",
    "FOMC_PRESS_CONF",
    "FOMC_MINUTES",
    "CPI_RELEASE",
    "NFP_RELEASE",
    "ECB_GOVC_DECISION",
    "ECB_PRESS_CONF",
    "GEOPOLITICAL_OFFICIAL",
)

MEETING_KINDS: Tuple[str, ...] = ("regular", "extraordinary", "not_applicable")

RESEARCH_MODES: Tuple[str, ...] = (
    "explanatory_event_study",
    "predictive",
    "unclassified",
)

# Only source classes that verifiably permit byte-level local retention may
# back a SourceDocument. FRED/ALFRED content is explicitly NOT archivable.
ARCHIVABLE_LICENSE_CLASSES: Tuple[str, ...] = ("US-GOV-PD",)
LICENSE_CLASSES: Tuple[str, ...] = (
    "US-GOV-PD",
    "ECB-PD-REVIEW-PENDING",
    "UNVERIFIED-REVIEW-PENDING",
    "FRED-ALFRED-RESTRICTED",
    "THIRD-PARTY-RESTRICTED",
)

EVENT_STR_FIELDS: Tuple[str, ...] = (
    "event_id", "event_type", "meeting_kind", "research_mode",
)
EVENT_TS_FIELDS: Tuple[str, ...] = (
    "scheduled_event_ts",
    "actual_release_ts",
    "information_available_ts",
    "feature_available_ts",
    "prediction_decision_ts",
    "prediction_horizon_start",
    "prediction_horizon_end",
    "response_window_start",
    "response_window_end",
)
SOURCE_FIELDS: Tuple[str, ...] = (
    "source_id", "publisher", "license_class", "verification",
    "access_terms_url", "verified_at",
    "usage_policy",
)
DOCUMENT_FIELDS: Tuple[str, ...] = (
    "source_id", "url", "fetched_at", "fetch_authorized", "sha256",
    "bytes_size", "integrity_verified", "content_type",
    "role", "published_at",
)

# Catalog constraints inherited from the research plan. Locators and declared
# publisher/license strings are not independent proof of legal rights or bytes.
# The offline verifier additionally requires a pinned document review record.
TRUSTED_SOURCE_CATALOG: Mapping[str, dict] = {
    "FRB_FOMC": {
        "publisher": "Federal Reserve Board",
        "license_class": "US-GOV-PD",
        "url_domains": ("federalreserve.gov",),
        "terms_urls": ("https://www.federalreserve.gov/aboutthefed/contact-us-topics.htm",),
        "event_types": ("FOMC_STATEMENT","FOMC_IMPL_NOTE","FOMC_PRESS_CONF","FOMC_MINUTES"),
    },
    "BLS_CPI": {
        "publisher": "Bureau of Labor Statistics",
        "license_class": "US-GOV-PD",
        "url_domains": ("bls.gov",),
        "terms_urls": ("https://www.bls.gov/bls/linksite.htm",),
        "event_types": ("CPI_RELEASE",),
    },
    "BLS_NFP": {
        "publisher": "Bureau of Labor Statistics",
        "license_class": "US-GOV-PD",
        "url_domains": ("bls.gov",),
        "terms_urls": ("https://www.bls.gov/bls/linksite.htm",),
        "event_types": ("NFP_RELEASE",),
    },
}

_HEX = frozenset("0123456789abcdef")
_DIGEST_FIELD = "record_digest"


def _parse_ts(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MacroEventError(ValueError):
    """Base class for macro-event registry validation failures."""


class EventSchemaError(MacroEventError):
    """Invalid/missing/unknown schema fields, sections or cross-references."""


class EventTimestampError(MacroEventError):
    """Missing, naive or non-canonical UTC timestamps."""


class EventLeakageError(MacroEventError):
    """Post-event/unavailable information classified as pre-event."""


class EventLicenseError(MacroEventError):
    """Source licensing or authenticity does not permit the attempted record."""


class EventDigestMismatchError(MacroEventError):
    """Recorded digest does not match recomputed canonical content."""


def _canonical_bytes(obj) -> bytes:
    """Deterministic canonical JSON bytes of an already-sectioned mapping."""
    def to_plain(value):
        if hasattr(value, "__dataclass_fields__"):
            return to_plain(asdict(value))
        if isinstance(value, dict):
            return {key: to_plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [to_plain(item) for item in value]
        return value

    try:
        text = json.dumps(
            {key: item for key, item in to_plain(obj).items()
             if key != _DIGEST_FIELD},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EventSchemaError(f"event not canonically serializable: {exc}") from exc
    return text.encode("utf-8")


def canonical_event_mapping(obj) -> dict:
    """THE single canonical representation of a macro-event record (Part E).

    Builder and validator MUST both hash exactly this shape:
    ``{"schema_version", "event": {...}, "source": {...}, "document": {...}}``
    (``record_digest`` excluded). Accepts a MacroEvent or a sealed serialized
    mapping. Non-string keys and unknown top-level sections are rejected here
    before any canonicalization (audit Part D); records whose
    schema_version differs from SCHEMA_VERSION are explicitly rejected
    (no silent migration of stored records).
    """
    if isinstance(obj, MacroEvent):
        return {
            "schema_version": obj.schema_version,
            "event": {name: getattr(obj, name)
                      for name in EVENT_STR_FIELDS + EVENT_TS_FIELDS},
            "source": asdict(obj.source),
            "document": asdict(obj.document),
        }
    if not isinstance(obj, dict):
        raise EventSchemaError(
            f"event must be a mapping, got {type(obj).__name__}"
        )
    bad_keys = [key for key in obj if not isinstance(key, str)]
    if bad_keys:
        raise EventSchemaError(
            f"top-level mapping contains non-string key(s): "
            f"{', '.join(repr(k) for k in bad_keys)}"
        )
    required = ("schema_version", "event", "source", "document")
    missing = [key for key in required if key not in obj]
    if missing:
        raise EventSchemaError(
            f"missing required top-level section(s): {', '.join(missing)}"
        )
    unknown = sorted(set(obj) - set(required) - {_DIGEST_FIELD})
    if unknown:
        raise EventSchemaError(
            f"unknown top-level section(s): {', '.join(unknown)}; "
            "unrecognized data is rejected, never discarded"
        )
    version = obj["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise EventSchemaError(
            f"unsupported schema_version {version!r}; this registry seals "
            f"SCHEMA_VERSION {SCHEMA_VERSION} only and explicitly rejects "
            "records sealed under other schemas (rebuild via "
            "build_macro_event); stored records are never silently migrated"
        )
    for section in ("event", "source", "document"):
        if not isinstance(obj[section], dict):
            raise EventSchemaError(
                f"section '{section}' must be a mapping/dict, got "
                f"{type(obj[section]).__name__}"
            )
        for key in obj[section]:
            if not isinstance(key, str):
                raise EventSchemaError(
                    f"section '{section}' contains non-string key "
                    f"{key!r}; non-string keys are rejected, not coerced"
                )
    return {
        "schema_version": version,
        "event": dict(obj["event"]),
        "source": dict(obj["source"]),
        "document": dict(obj["document"]),
    }


def canonical_event_bytes(obj) -> bytes:
    """Canonical bytes of *obj* (digest field excluded)."""
    return _canonical_bytes(canonical_event_mapping(obj))


def event_record_digest(obj) -> str:
    """SHA-256 over the one canonical representation (digest field excluded)."""
    return hashlib.sha256(canonical_event_bytes(obj)).hexdigest()


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and set(value.lower()) <= _HEX and value == value.lower()
    )


def _canonical_ts(value, label: str, *, required: bool = True) -> Optional[str]:
    """Validate one timestamp and return its canonical ``Z`` string (or None).

    Policy (plan R1): stored timestamps must already be in canonical UTC Z
    notation; other offset spellings of the same instant are rejected rather
    than silently reinterpreted, so digests stay stable across authors.
    """
    if value is None:
        if required:
            raise EventTimestampError(f"field '{label}' is required, got None")
        return None
    try:
        canonical = canonical_utc_text(value, label)
    except CalendarError as exc:
        raise EventTimestampError(str(exc)) from exc
    if isinstance(value, str) and value != canonical:
        raise EventTimestampError(
            f"field '{label}' must use canonical UTC Z notation "
            f"{canonical!r}, got {value!r}; per-field offsets would "
            "fragment the digest space"
        )
    return canonical


def _check_text(obj: Mapping, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EventSchemaError(f"field '{key}' must be a non-empty string, got {value!r}")
    return value


def _strict_section_keys(raw: dict, allowed: Tuple[str, ...], label: str) -> None:
    """Unknown nested fields are REJECTED (not discarded), and every declared
    key must be explicitly present (None allowed only for nullable fields)."""
    unknown = sorted(set(raw) - set(allowed))
    if unknown:
        raise EventSchemaError(
            f"unknown {label} field(s): {', '.join(unknown)}; unrecognized "
            "data is rejected, never discarded"
        )
    missing = [key for key in allowed if key not in raw]
    if missing:
        raise EventSchemaError(
            f"missing {label} field(s): {', '.join(missing)}; every declared "
            "key must be present explicitly (None where nullable) — absent "
            "keys are never silently interpreted as None"
        )


def _url_domain(url: str) -> str:
    return (urlsplit(url).netloc or "").lower()


def _domain_allowed(url: str, domains: Tuple[str, ...]) -> bool:
    try:
        parsed=urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None,443):
            return False
    except ValueError:
        return False
    netloc = (parsed.hostname or "").lower()
    return any(
        netloc == domain or netloc.endswith("." + domain) for domain in domains
    )


@dataclass(frozen=True)
class EventSource:
    """Immutable, typed event source.

    ``license_class``/``publisher`` are DECLARED metadata. ``verification`` is
    the separate verified-permission state; only ``catalog_verified`` sources
    (proven against TRUSTED_SOURCE_CATALOG) may back retained documents.
    """

    source_id: str
    publisher: str
    license_class: str
    verification: str  # 'catalog_verified' | 'self_declared'
    access_terms_url: str
    verified_at: str  # canonical UTC Z
    usage_policy: str  # local descriptive research only; not blanket rights


@dataclass(frozen=True)
class SourceDocument:
    """Immutable byte-pinned origin of truth for one fetched document."""

    source_id: str  # must equal the backing EventSource.source_id
    url: str
    fetched_at: str  # canonical UTC Z
    fetch_authorized: bool  # explicit, auditable fetch permission
    sha256: str  # DECLARED digest; not proof until IntegrityVerified gate passes
    bytes_size: int  # positive int
    integrity_verified: bool  # legacy declaration only; never trusted as evidence
    content_type: str
    role: str  # announcement, schedule or background
    published_at: str


@dataclass(frozen=True)
class MacroEvent:
    """Immutable macro-event record with explicit temporal semantics (v2)."""

    schema_version: int
    event_id: str
    event_type: str
    meeting_kind: str
    research_mode: str
    scheduled_event_ts: Optional[str]
    actual_release_ts: Optional[str]
    information_available_ts: Optional[str]
    feature_available_ts: Optional[str]
    prediction_decision_ts: Optional[str]
    prediction_horizon_start: Optional[str]
    prediction_horizon_end: Optional[str]
    response_window_start: Optional[str]
    response_window_end: Optional[str]
    source: EventSource
    document: SourceDocument
    record_digest: str


def _validate_source(raw: Mapping) -> EventSource:
    if not isinstance(raw, dict):
        raise EventSchemaError(
            f"section 'source' must be a mapping/dict, got {type(raw).__name__}"
        )
    _strict_section_keys(raw, SOURCE_FIELDS, "EventSource")
    source_id = _check_text(raw, "source_id")
    _check_text(raw, "publisher")
    license_class = _check_text(raw, "license_class")
    if license_class not in LICENSE_CLASSES:
        raise EventLicenseError(
            f"unknown license_class {license_class!r}; supported: {LICENSE_CLASSES}"
        )
    verification = _check_text(raw, "verification")
    if verification not in ("catalog_verified", "self_declared"):
        raise EventSchemaError(
            f"source.verification must be 'catalog_verified' or "
            f"'self_declared', got {verification!r}"
        )
    if verification != "catalog_verified":
        raise EventLicenseError(
            "source.verification 'self_declared' is not proof of permission: "
            "declared publisher/license_class strings are metadata only; "
            "retained documents require a TRUSTED_SOURCE_CATALOG-verified "
            "source (or a future explicit-authorization mechanism)"
        )
    entry = TRUSTED_SOURCE_CATALOG.get(source_id)
    if entry is None:
        raise EventLicenseError(
            f"source_id {source_id!r} is not in TRUSTED_SOURCE_CATALOG; "
            "self-declared license metadata cannot establish usage "
            "permission; add the source after an explicit verification "
            "review, or use an existing catalog entry"
        )
    if license_class not in ARCHIVABLE_LICENSE_CLASSES:
        raise EventLicenseError(
            f"license_class {license_class!r} does not permit byte-level "
            "local retention; do not archive, cache or train on restricted "
            "data (FRED/ALFRED ToU explicitly forbids archiving and ML "
            "training; third-party classes need individual review)"
        )
    if (raw["publisher"] != entry["publisher"] or
            license_class != entry["license_class"]):
        raise EventLicenseError(
            f"source authentication failed: declared publisher "
            f"{raw['publisher']!r} / license_class {license_class!r} do not "
            f"match the catalog entry for {source_id!r} "
            f"({entry['publisher']!r} / {entry['license_class']!r}); "
            "self-declared license_class is not proof of authenticity"
        )
    access_terms_url = _check_text(raw, "access_terms_url")
    if not access_terms_url.startswith(("http://", "https://")):
        raise EventSchemaError(
            f"access_terms_url must be an http(s) URL, got {access_terms_url!r}"
        )
    if access_terms_url not in entry["terms_urls"]:
        raise EventLicenseError("access_terms_url is not an explicitly reviewed catalog locator")
    if raw["usage_policy"] != "local_descriptive_research":
        raise EventLicenseError("Only local_descriptive_research scope is supported; no blanket licensing rights")
    verified_at = _canonical_ts(raw["verified_at"], "source.verified_at")
    return EventSource(
        source_id=source_id,
        publisher=raw["publisher"],
        license_class=license_class,
        verification=verification,
        access_terms_url=access_terms_url,
        verified_at=verified_at,
        usage_policy=raw["usage_policy"],
    )


def _validate_document(raw: Mapping, source: EventSource) -> SourceDocument:
    if not isinstance(raw, dict):
        raise EventSchemaError(
            f"section 'document' must be a mapping/dict, got {type(raw).__name__}"
        )
    _strict_section_keys(raw, DOCUMENT_FIELDS, "SourceDocument")
    doc_source_id = raw["source_id"]
    if doc_source_id != source.source_id:
        raise EventSchemaError(
            f"invalid source reference: document.source_id {doc_source_id!r} "
            f"does not match event source {source.source_id!r}"
        )
    url = _check_text(raw, "url")
    if not url.startswith(("http://", "https://")):
        raise EventSchemaError(f"document url must be http(s), got {url!r}")
    entry = TRUSTED_SOURCE_CATALOG[source.source_id]
    if not _domain_allowed(url, entry["url_domains"]):
        raise EventLicenseError(
            f"document url host {_url_domain(url)!r} is outside the verified "
            f"domain allowlist {entry['url_domains']} for source "
            f"{source.source_id!r}; a non-governor URL cannot prove the "
            "claimed provenance"
        )
    if raw["fetch_authorized"] is not True:
        raise EventLicenseError(
            "document.fetch_authorized must be an explicit True; unauthorized "
            "fetches may never enter the registry"
        )
    if source.license_class not in ARCHIVABLE_LICENSE_CLASSES:
        raise EventLicenseError(
            f"license_class {source.license_class!r} does not permit "
            "byte-level local retention; do not archive, cache or train on "
            "restricted data (FRED/ALFRED ToU explicitly forbids archiving "
            "and ML training; third-party classes need individual review)"
        )
    fetched_at = _canonical_ts(raw["fetched_at"], "document.fetched_at")
    published_at = _canonical_ts(raw["published_at"], "document.published_at")
    if raw["role"] not in ("announcement","schedule","background"):
        raise EventSchemaError("Explicit document role required")
    if _parse_ts(fetched_at) < _parse_ts(published_at):
        raise EventTimestampError("Document fetched before publication")
    if not _is_sha256(raw["sha256"]):
        raise EventSchemaError(
            "document.sha256 must be a lowercase 64-character hex SHA-256, "
            f"got {raw['sha256']!r}"
        )
    size = raw["bytes_size"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise EventSchemaError(
            f"document.bytes_size must be a positive integer, got {size!r}"
        )
    if not isinstance(raw["integrity_verified"], bool):
        raise EventSchemaError(
            "document.integrity_verified must be a bool (False means the "
            "declared SHA-256 has NOT yet been checked against actual bytes), "
            f"got {raw['integrity_verified']!r}"
        )
    _check_text(raw, "content_type")
    return SourceDocument(
        source_id=source.source_id,
        url=url,
        fetched_at=fetched_at,
        fetch_authorized=True,
        sha256=raw["sha256"],
        bytes_size=size,
        integrity_verified=raw["integrity_verified"],
        content_type=raw["content_type"],
        role=raw["role"],
        published_at=published_at,
    )


def _validate_event_fields(raw: Mapping) -> dict:
    if not isinstance(raw, dict):
        raise EventSchemaError(
            f"section 'event' must be a mapping/dict, got {type(raw).__name__}"
        )
    _strict_section_keys(raw, EVENT_STR_FIELDS + EVENT_TS_FIELDS, "Event")

    event_id = _check_text(raw, "event_id")
    event_type = _check_text(raw, "event_type")
    if event_type not in EVENT_TYPES:
        raise EventSchemaError(
            f"unknown event_type {event_type!r}; supported: {EVENT_TYPES}"
        )
    meeting_kind = _check_text(raw, "meeting_kind")
    if meeting_kind not in MEETING_KINDS:
        raise EventSchemaError(
            f"unknown meeting_kind {meeting_kind!r}; supported: {MEETING_KINDS}"
        )
    research_mode = _check_text(raw, "research_mode")
    if research_mode not in RESEARCH_MODES:
        raise EventSchemaError(
            f"unknown research_mode {research_mode!r}; supported: {RESEARCH_MODES}"
        )
    if event_type.startswith("FOMC_") and meeting_kind == "not_applicable":
        raise EventSchemaError(
            "FOMC events must declare meeting_kind 'regular' or "
            "'extraordinary' (completed-meeting classification, plan R5/R6)"
        )

    ts_values = {
        name: _canonical_ts(raw[name], name, required=False)
        for name in EVENT_TS_FIELDS
    }
    scheduled_event_ts = ts_values["scheduled_event_ts"]
    actual_release_ts = ts_values["actual_release_ts"]
    information_available_ts = ts_values["information_available_ts"]
    feature_available_ts = ts_values["feature_available_ts"]
    decision_ts = ts_values["prediction_decision_ts"]
    horizon_start = ts_values["prediction_horizon_start"]
    horizon_end = ts_values["prediction_horizon_end"]
    window_start = ts_values["response_window_start"]
    window_end = ts_values["response_window_end"]

    # --- Global structural window/integrity rules -------------------------
    if (window_start is None) != (window_end is None):
        raise EventSchemaError(
            "response_window_start and response_window_end must be set "
            "together; both or neither"
        )
    if window_start is not None and window_end is not None and (
            _parse_ts(window_end) <= _parse_ts(window_start)):
        raise EventTimestampError(
            f"response_window_end {window_end} must be after "
            f"response_window_start {window_start}"
        )
    if (horizon_start is None) != (horizon_end is None):
        raise EventSchemaError(
            "prediction_horizon_start and prediction_horizon_end must be set "
            "together; both or neither"
        )
    if horizon_start is not None and horizon_end is not None and (
            _parse_ts(horizon_end) <= _parse_ts(horizon_start)):
        raise EventTimestampError(
            f"prediction_horizon_end {horizon_end} must be after "
            f"prediction_horizon_start {horizon_start}"
        )

    # --- Release/schedule/information ordering (not mode-dependent) -------
    if (actual_release_ts is not None and scheduled_event_ts is not None and
            _parse_ts(actual_release_ts) < _parse_ts(scheduled_event_ts)):
        raise EventTimestampError(
            f"actual_release_ts {actual_release_ts} precedes "
            f"scheduled_event_ts {scheduled_event_ts}; if the release really "
            "happened earlier, correct the schedule or record an "
            "'extraordinary' revision instead of reordering time"
        )
    if (actual_release_ts is not None and
            information_available_ts is not None and
            _parse_ts(information_available_ts) < _parse_ts(actual_release_ts)):
        raise EventLeakageError(
            f"information_available_ts {information_available_ts} precedes "
            f"actual_release_ts {actual_release_ts}; realized announcement "
            "information can never become available before its actual release"
        )
    if actual_release_ts is None and information_available_ts is not None:
        raise EventLeakageError(
            "event has no actual_release_ts yet carries "
            f"information_available_ts {information_available_ts}; an "
            "advance-published schedule must not be classified as published "
            "information (schedule-vs-decision distinction)"
        )

    research_fields = ("feature_available_ts", "prediction_decision_ts",
                       "prediction_horizon_start", "prediction_horizon_end",
                       "response_window_start", "response_window_end")

    if research_mode == "unclassified":
        # Plain schedule/provenance record: no research semantics assigned.
        present = [name for name in research_fields
                   if ts_values[name] is not None]
        if present:
            raise EventSchemaError(
                "research_mode 'unclassified' may not carry research "
                f"field(s): {', '.join(present)}; assign an explicit "
                "research_mode instead"
            )

    elif research_mode == "explanatory_event_study":
        # Historical observation of a completed event. Observation windows
        # MAY straddle the release instant (e.g. [-30min,+30min]) and are
        # NEVER constrained by feature availability (audit Part A/B).
        if decision_ts is not None or horizon_start is not None:
            raise EventSchemaError(
                "research_mode 'explanatory_event_study' does not carry "
                "predictive fields (prediction_decision_ts / "
                "prediction_horizon_*); predictive decisions and observation "
                "windows are separate record semantics and must never be "
                "merged"
            )
        if actual_release_ts is None:
            raise EventSchemaError(
                "explanatory event study requires an observed completed "
                "release (actual_release_ts); a schedule-only event cannot "
                "constitute a historical observation"
            )

    else:  # predictive
        # Ex-ante discipline (audit Part A): decision strictly before the
        # announcement; features complete at/before the decision — never
        # post-decision, never post-announcement features.
        if decision_ts is None or feature_available_ts is None or (
                horizon_start is None or horizon_end is None):
            missing = [name for name in (
                "prediction_decision_ts", "feature_available_ts",
                "prediction_horizon_start", "prediction_horizon_end")
                if ts_values[name] is None]
            raise EventSchemaError(
                "research_mode 'predictive' requires explicitly set "
                f"{', '.join(missing)}; absent keys are never interpreted as "
                "values"
            )
        if window_start is not None:
            raise EventSchemaError(
                "research_mode 'predictive' does not carry observation "
                "windows (response_window_*); historical event-observation "
                "windows belong to explanatory_event_study records and the "
                "two semantics must remain separated"
            )
        if actual_release_ts is not None and (
                _parse_ts(decision_ts) >= _parse_ts(actual_release_ts)):
            raise EventLeakageError(
                f"prediction_decision_ts {decision_ts} is not strictly "
                f"earlier than actual_release_ts {actual_release_ts}; an "
                "ex-ante predictive model must decide before the "
                "announcement, never at/after it"
            )
        if _parse_ts(feature_available_ts) > _parse_ts(decision_ts):
            raise EventLeakageError(
                f"feature_available_ts {feature_available_ts} is later than "
                f"prediction_decision_ts {decision_ts}: a predictive decision "
                "cannot use features that were unavailable at decision time "
                "(post-decision features are forbidden)"
            )
        if _parse_ts(horizon_start) < _parse_ts(decision_ts):
            raise EventTimestampError(
                f"prediction_horizon_start {horizon_start} precedes "
                f"prediction_decision_ts {decision_ts}; a prediction horizon "
                "starts at/after the decision, in the future"
            )

    return {
        "event_id": event_id,
        "event_type": event_type,
        "meeting_kind": meeting_kind,
        "research_mode": research_mode,
        "scheduled_event_ts": scheduled_event_ts,
        "actual_release_ts": actual_release_ts,
        "information_available_ts": information_available_ts,
        "feature_available_ts": feature_available_ts,
        "prediction_decision_ts": decision_ts,
        "prediction_horizon_start": horizon_start,
        "prediction_horizon_end": horizon_end,
        "response_window_start": window_start,
        "response_window_end": window_end,
    }


def validate_macro_event(event: dict) -> MacroEvent:
    """Strictly validate a macro-event mapping; return an immutable record.

    Fails closed with typed errors on: unknown section/field names (never
    discarded), absent declared keys, wrong section types, non-string keys,
    unverified or unknown sources, non-archivable licenses, unauthorized
    fetches, malformed SHA-256 formats, naive or non-canonical timestamps,
    schema-version mismatches, digest mismatches and every structural
    temporal-leakage permutation. Never repairs anything.
    """
    canonical = canonical_event_mapping(event)
    source = _validate_source(canonical["source"])
    document = _validate_document(canonical["document"], source)
    fields = _validate_event_fields(canonical["event"])
    if fields["event_type"] not in TRUSTED_SOURCE_CATALOG[source.source_id]["event_types"]:
        raise EventSchemaError("Event type is incompatible with reviewed source")
    if document.role == "announcement":
        if fields["actual_release_ts"] is None or fields["information_available_ts"] is None:
            raise EventTimestampError("Announcement document requires an observed release and availability")
        if (_parse_ts(document.published_at) < _parse_ts(fields["actual_release_ts"]) or
                _parse_ts(document.published_at) > _parse_ts(fields["information_available_ts"]) or
                _parse_ts(document.fetched_at) < _parse_ts(fields["information_available_ts"])):
            raise EventTimestampError("Announcement publication/fetch chronology contradicts release availability")
    elif document.role == "schedule":
        if fields["scheduled_event_ts"] is None or _parse_ts(document.published_at)>_parse_ts(fields["scheduled_event_ts"]):
            raise EventTimestampError("Schedule document must precede its scheduled event")

    recorded = event.get(_DIGEST_FIELD)
    if not _is_sha256(recorded):
        raise EventSchemaError(
            "field 'record_digest' must be a lowercase 64-character hex "
            f"SHA-256, got {recorded!r}"
        )
    computed = event_record_digest({
        "schema_version": canonical["schema_version"],
        "event": fields,
        "source": asdict(source),
        "document": asdict(document),
    })
    if computed != recorded:
        raise EventDigestMismatchError(
            f"record_digest mismatch: recorded {recorded}, recomputed "
            f"{computed} — the record changed after sealing"
        )
    return MacroEvent(
        schema_version=canonical["schema_version"],
        record_digest=recorded,
        source=source,
        document=document,
        **fields,
    )


def build_macro_event(
    *,
    event_id: str,
    event_type: str,
    meeting_kind: str,
    research_mode: str,
    source: dict,
    document: dict,
    scheduled_event_ts=None,
    actual_release_ts=None,
    information_available_ts=None,
    feature_available_ts=None,
    prediction_decision_ts=None,
    prediction_horizon_start=None,
    prediction_horizon_end=None,
    response_window_start=None,
    response_window_end=None,
) -> MacroEvent:
    """Build, seal and eager-validate one macro event; return a frozen record.

    Timestamps passed as datetimes or strings are canonicalized first (same
    policy as research_crypto builders); source and document pass through the
    same validators used by validate_macro_event, so the sealed digest is
    computed over exactly the canonical representation the validator will
    recompute. Raises the same typed errors at build time: a builder can
    never emit leaked, unsealed or schema-invalid records silently.
    """
    event_input = {
        "event_id": event_id,
        "event_type": event_type,
        "meeting_kind": meeting_kind,
        "research_mode": research_mode,
        "scheduled_event_ts": scheduled_event_ts,
        "actual_release_ts": actual_release_ts,
        "information_available_ts": information_available_ts,
        "feature_available_ts": feature_available_ts,
        "prediction_decision_ts": prediction_decision_ts,
        "prediction_horizon_start": prediction_horizon_start,
        "prediction_horizon_end": prediction_horizon_end,
        "response_window_start": response_window_start,
        "response_window_end": response_window_end,
    }
    validated_source = _validate_source(dict(source))
    validated_document = _validate_document(dict(document), validated_source)
    fields = _validate_event_fields(event_input)
    canonical = {
        "schema_version": SCHEMA_VERSION,
        "event": fields,
        "source": asdict(validated_source),
        "document": asdict(validated_document),
    }
    mapping = {**canonical, _DIGEST_FIELD: event_record_digest(canonical)}
    return validate_macro_event(mapping)


def is_in_sample(event: MacroEvent, as_of: str = SAMPLE_CUTOFF_UTC) -> bool:
    """Retrospective sample membership as of ``as_of`` (audit Part C).

    True only when the record establishes BOTH a verifiable announcement
    (``actual_release_ts``) AND public information availability
    (``information_available_ts``) no later than the cutoff. A release known
    earlier whose information only became available after the cutoff is NOT
    sample-eligible. ``document.fetched_at`` is deliberately NEVER used here:
    a document fetched years later does not make the original publication
    unavailable in historical retrospective research; the original
    release/availability pair is what must be established. Scheduled-only
    events (e.g. the 2026-10-27/28 FOMC meeting) are never members.
    """
    cutoff = _parse_ts(_canonical_ts(as_of, "as_of"))
    if event.actual_release_ts is None or event.information_available_ts is None:
        return False
    return (
        _parse_ts(event.actual_release_ts) <= cutoff
        and _parse_ts(event.information_available_ts) <= cutoff
    )


def is_predictive_eligible(event: MacroEvent, as_of: str = SAMPLE_CUTOFF_UTC) -> bool:
    """Predictive-feature eligibility as of ``as_of`` (audit Part C).

    Separate from retrospective membership: a predictive record is eligible
    when its decision was made and its feature snapshot was verifiably
    available no later than the cutoff. Historical observation membership
    (``is_in_sample``) and predictive feature availability are never mixed.
    """
    cutoff = _parse_ts(_canonical_ts(as_of, "as_of"))
    if event.research_mode != "predictive":
        return False
    if event.prediction_decision_ts is None or event.feature_available_ts is None:
        return False
    return (
        _parse_ts(event.prediction_decision_ts) <= cutoff
        and _parse_ts(event.feature_available_ts) <= cutoff
    )


def require_integrity_verified(event: MacroEvent, **verification_inputs):
    """Byte identity gate against an independently pinned local review record.

    ``document.sha256`` is a DECLARED string; the registry records it, but it
    does not prove anything about the actual fetched bytes until an explicit
    byte-level SHA-256 re-check has passed. Call this before any downstream
    analysis uses a document. This does not prove publisher authorship or
    blanket legal permission. The legacy Boolean is never trusted.
    """
    from .documents import verify_document_bytes
    return verify_document_bytes(event,**verification_inputs)
