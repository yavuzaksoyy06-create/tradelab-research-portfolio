"""TradeLab Macro Event Registry (research_macro) — schema v3 (synthetic only).

Isolated package: no predictive ML, no news scraping, no data downloads, no
trading. Integrity patterns are inherited from research_crypto.manifest
(canonical JSON, SHA-256 digests, canonical UTC Z timestamps, fail-closed
validation). See MACRO_RESEARCH_PLAN_031.md revisions 2026-10-24b and
2026-10-24c (independent audit remediation).
"""
from .events import (
    ARCHIVABLE_LICENSE_CLASSES,
    DOCUMENT_FIELDS,
    EVENT_STR_FIELDS,
    EVENT_TS_FIELDS,
    EVENT_TYPES,
    EventDigestMismatchError,
    EventLeakageError,
    EventLicenseError,
    EventSchemaError,
    EventSource,
    EventTimestampError,
    MacroEvent,
    MacroEventError,
    RESEARCH_MODES,
    SAMPLE_CUTOFF_UTC,
    SCHEMA_VERSION,
    SOURCE_FIELDS,
    SourceDocument,
    TRUSTED_SOURCE_CATALOG,
    build_macro_event,
    canonical_event_bytes,
    canonical_event_mapping,
    event_record_digest,
    is_in_sample,
    is_predictive_eligible,
    require_integrity_verified,
    validate_macro_event,
)

__version__ = "0.3.0.dev1"  # schema v3: explicit role, usage and offline trust evidence
