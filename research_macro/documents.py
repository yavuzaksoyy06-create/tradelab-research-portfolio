"""Offline byte verification against an independently pinned local trust registry.

The registry pin must be provisioned by a reviewer, independently of the event.
This proves byte identity relative to that trust anchor, not publisher identity,
legal rights or cryptographic vendor provenance. No network/filesystem access.
"""
from dataclasses import dataclass
import hashlib,json
from .events import (EventLicenseError,EventSchemaError,_canonical_ts,_parse_ts,
                     _is_sha256,canonical_event_mapping,validate_macro_event)

def registry_digest(registry):
    return hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(",",":"),
                                    ensure_ascii=True,allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class VerificationEvidence:
    event_digest: str
    document_sha256: str
    registry_sha256: str
    bytes_size: int
    reviewer: str
    review_reference: str
    verified_at: str
    trust_kind: str = "independently_pinned_local_review"

def verify_document_bytes(event,*,document_bytes=None,trust_registry=None,registry_sha256=None,verified_at=None):
    # Revalidate canonical content: a directly instantiated dataclass is not authority.
    validate_macro_event({**canonical_event_mapping(event),"record_digest":event.record_digest})
    if not isinstance(document_bytes,bytes) or not isinstance(trust_registry,dict) or not _is_sha256(registry_sha256):
        raise EventLicenseError("declared integrity flag/hash is insufficient: actual bytes and independently pinned trust registry required")
    if registry_digest(trust_registry)!=registry_sha256:
        raise EventLicenseError("Trust registry pin mismatch")
    if set(trust_registry)!={"schema_version","documents"} or type(trust_registry["schema_version"]) is not int or trust_registry["schema_version"]!=1:
        raise EventSchemaError("Unsupported trust registry schema")
    records=trust_registry["documents"]
    if not isinstance(records,dict):raise EventSchemaError("Trust documents must be a mapping")
    record=records.get(event.document.url)
    keys={"source_id","sha256","bytes_size","reviewer","review_reference","reviewed_at","terms_url","allowed_uses"}
    if not isinstance(record,dict) or set(record)!=keys:raise EventLicenseError("No complete reviewed trust record for document URL")
    if (record["source_id"]!=event.source.source_id or record["terms_url"]!=event.source.access_terms_url or
            record["allowed_uses"]!=["local_descriptive_research"]):
        raise EventLicenseError("Reviewed source/terms/usage scope mismatch")
    for key in ("reviewer","review_reference"):
        if not isinstance(record[key],str) or not record[key].strip():raise EventLicenseError("Explicit trusted review evidence required")
    checked=_canonical_ts(verified_at,"verified_at")
    reviewed=_canonical_ts(record["reviewed_at"],"reviewed_at")
    if _parse_ts(checked)<max(_parse_ts(event.document.fetched_at),_parse_ts(reviewed)):
        raise EventLicenseError("Verification precedes fetch or trusted review")
    actual=hashlib.sha256(document_bytes).hexdigest()
    if (not _is_sha256(record["sha256"]) or actual!=record["sha256"] or actual!=event.document.sha256 or
            type(record["bytes_size"]) is not int or len(document_bytes)!=record["bytes_size"] or
            len(document_bytes)!=event.document.bytes_size or not document_bytes):
        raise EventLicenseError("Document bytes do not match independent pin, declared digest and size")
    return VerificationEvidence(event.record_digest,actual,registry_sha256,len(document_bytes),
                                record["reviewer"],record["review_reference"],checked)
