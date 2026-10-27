"""Versioned crypto dataset manifest engine (Stage 2 of the 0.3.0 program).

Purpose: a deterministic, strictly validated manifest describing one locally
produced dataset file per BTC/USDT or ETH/USDT symbol, hash-pinned and
bar-count-consistent with the Stage 1 UTC calendar.

Scope discipline (see CRYPTO_RESEARCH_PLAN_030.md):

- Standard library only. No network, no downloads, no vendor calls, no
  broker anything.
- Canonical hashing: the manifest digest covers every field except
  ``digest`` itself, serialized with sorted keys, compact separators and
  ASCII-safe output (``json.dumps(..., sort_keys=True, separators=(",", ":"),
  ensure_ascii=True)`` encoded as UTF-8). Two byte-equal canonical payloads
  always hash identically across platforms. All serialized timestamps are
  normalized to canonical UTC ``Z`` notation before hashing, so different
  offset spellings of the same instant cannot fragment the digest space.
- Evidence semantics, kept distinct on purpose:
  1. *Manifest integrity* — proven by ``digest`` + ``dataset.sha256``:
     byte-level consistency relative to a trusted reference.
  2. *Source authenticity* — NOT proven by any hash. ``provenance`` is a
     producer attestation recorded from the dataset producer; a SHA-256
     digest never establishes that a dataset was supplied by the claimed
     exchange.
  3. *OHLCV semantic validity* — NOT proven at this stage. Stage 2 validates
     schema shape, UTC alignment, bar counts and path safety only; the bar
     level adapter (Stage 3) owns OHLC/volume plausibility checks.
- Accepted manifests are returned as frozen records (including an immutable
  ``FundingTerms`` snapshot for perpetual datasets); validators never repair,
  fill or fabricate data. Fail closed, always.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence, Tuple

from .calendar import (
    CalendarError,
    NaiveTimestampError,
    as_utc,
    expected_grid,
    merge_maintenance_windows,
)

__all__ = [
    "CANONICAL_BAR_OPEN_CONVENTION",
    "DATASET_FIELD_ALIASES",
    "DigestMismatchError",
    "FundingError",
    "FundingTerms",
    "ManifestError",
    "ManifestRecord",
    "MAX_GRID_SPAN_HOURS",
    "MAX_MAINTENANCE_WINDOWS",
    "PathSafetyError",
    "SchemaError",
    "SchemaVersionError",
    "SUPPORTED_SCHEMA_VERSIONS",
    "SUPPORTED_SYMBOLS",
    "SUPPORTED_TIMEFRAMES",
    "VerifiedDataset",
    "build_manifest",
    "canonical_manifest_bytes",
    "canonical_utc_text",
    "manifest_digest",
    "parse_manifest",
    "validate_manifest",
    "verify_dataset",
]

SUPPORTED_SCHEMA_VERSIONS: Tuple[int, ...] = (1,)
SUPPORTED_SYMBOLS: Tuple[str, ...] = ("BTC/USDT", "ETH/USDT")
SUPPORTED_TIMEFRAMES: Tuple[str, ...] = ("1h",)
CANONICAL_BAR_OPEN_CONVENTION = (
    "hourly UTC bar opens; a bar covers the half-open interval [open, open+1h)"
)
DATASET_FIELD_ALIASES: Tuple[str, ...] = ("data_file", "csv_file", "file", "path")
# Defensive caps so a hostile manifest cannot force unbounded grid or window
# materialization. 200k hours ≈ 22.8 years of hourly bars.
MAX_GRID_SPAN_HOURS = 200_000
MAX_MAINTENANCE_WINDOWS = 10_000
_SENSITIVE_TOKENS = (
    "api_key", "apikey", "secret", "token", "password", "passwd",
    "credential", "authorization", "auth", "private_key", "access_key",
)
_HEX = frozenset("0123456789abcdef")

_DIGEST = "digest"


class ManifestError(ValueError):
    """Base class for manifest validation failures."""


class SchemaVersionError(ManifestError):
    """Raised for a missing, mistyped or unsupported schema version."""


class SchemaError(ManifestError):
    """Raised for missing/unknown/duplicate fields and malformed values."""


class PathSafetyError(ManifestError):
    """Raised for dataset references escaping the allowed dataset root."""


class DigestMismatchError(ManifestError):
    """Raised when a recorded digest does not match freshly computed content."""


class FundingError(ManifestError):
    """Raised when funding metadata is missing (perp) or present (spot)."""


def canonical_manifest_bytes(manifest: Mapping) -> bytes:
    """Serialize *manifest* minus its ``digest`` field canonically.

    Every manifest field except ``digest`` participates in the digest. Keys
    are sorted, separators are compact and output is ASCII-safe, so the byte
    stream is identical on any platform regardless of dict insertion order.
    """
    payload = {key: value for key, value in manifest.items() if key != _DIGEST}
    try:
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"manifest is not canonically serializable: {exc}") from exc
    return text.encode("utf-8")


def manifest_digest(manifest: Mapping) -> str:
    """SHA-256 hex digest of the canonical manifest bytes (digest excluded)."""
    return hashlib.sha256(canonical_manifest_bytes(manifest)).hexdigest()


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and set(value.lower()) <= _HEX and value == value.lower()
    )


def canonical_utc_text(value, label: str) -> str:
    """Return *value* as a canonical UTC ISO-8601 string with a ``Z`` suffix.

    Policy: every serialized timestamp entering the manifest is normalized to
    ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z`` in UTC before hashing, so two manifests
    referring to the same absolute instant through different UTC offsets
    produce byte-identical canonical payloads and therefore identical
    digests. Naive inputs still raise ``NaiveTimestampError``.
    """
    moment = as_utc(value, label).astimezone(timezone.utc)
    return moment.isoformat().replace("+00:00", "Z")


def _is_sensitive_key(key: str) -> bool:
    """Conservative credential-key detector for provenance maps.

    Normalization: every non-alphanumeric character becomes a separator, then
    the key is decomposed into lowercase components (``api-key`` → api, key;
    ``apiKey`` → apikey). A key is rejected when any sensitive token matches
    a full run of consecutive components — so ``author_signature_note`` is
    accepted while ``auth``, ``authorization``, ``access_token``,
    ``private_key`` and ``secret_key`` are rejected. Deliberately
    conservative in the security direction: over-rejecting an innocuous
    attestation is recoverable (rename the key), a leaked credential in a
    manifest is not.
    """
    components = [
        chunk for chunk in
        "".join(ch if ch.isalnum() else "_" for ch in key).lower().split("_")
        if chunk
    ]
    for token in _SENSITIVE_TOKENS:
        parts = token.split("_")
        width = len(parts)
        for start in range(len(components) - width + 1):
            if components[start:start + width] == list(parts):
                return True
    return False


def _reject_pairs(pairs):
    """object_pairs_hook that fails closed on duplicate JSON keys."""
    seen = {}
    duplicates = []
    for key, value in pairs:
        if key in seen:
            duplicates.append(key)
        seen[key] = value
    if duplicates:
        raise SchemaError(f"duplicate JSON keys in manifest: {', '.join(sorted(set(duplicates)))}")
    return seen


def parse_manifest(text: str) -> dict:
    """Parse manifest JSON strictly: object only, no duplicate keys."""
    try:
        manifest = json.loads(text, object_pairs_hook=_reject_pairs)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError(f"manifest must be a JSON object, got {type(manifest).__name__}")
    return manifest


def _check_string(manifest: Mapping, key: str) -> str:
    value = manifest.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"field '{key}' must be a non-empty string, got {value!r}")
    return value


_REQUIRED_FIELDS = (
    "schema_version", "provider", "venue", "market_type", "symbol",
    "base", "quote", "timeframe", "start", "end",
    "bar_open_convention", "expected_bars", "observed_bars",
    "dataset", "provenance", "created_at",
)


def _validate_header(manifest: Mapping) -> dict:
    non_string_keys = sorted(repr(key) for key in manifest if not isinstance(key, str))
    if non_string_keys:
        raise SchemaError(
            "manifest keys must be strings, got non-string key(s): "
            f"{', '.join(non_string_keys)}"
        )
    missing = [key for key in _REQUIRED_FIELDS if key not in manifest]
    if missing:
        raise SchemaError(f"missing required field(s): {', '.join(sorted(missing))}")

    aliases = [alias for alias in DATASET_FIELD_ALIASES if alias in manifest]
    if aliases:
        raise SchemaError(
            "conflicting dataset reference(s): dataset file must be declared "
            f"once under 'dataset.file', not via {', '.join(aliases)} field(s)"
        )

    known = set(_REQUIRED_FIELDS) | {_DIGEST} | {"maintenance_windows", "funding"}
    unknown = sorted(set(manifest) - known)
    if unknown:
        raise SchemaError(f"unknown field(s): {', '.join(unknown)}")

    version = manifest["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise SchemaVersionError(
            f"schema_version must be an integer, got {type(version).__name__}"
        )
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionError(
            f"unsupported schema_version {version}; supported: "
            f"{list(SUPPORTED_SCHEMA_VERSIONS)}. Refusing to guess semantics."
        )

    for key in ("provider", "venue", "market_type", "symbol", "base", "quote",
                "timeframe"):
        _check_string(manifest, key)

    if manifest["market_type"] not in ("spot", "perp"):
        raise SchemaError(
            f"market_type must be 'spot' or 'perp', got {manifest['market_type']!r}"
        )
    if manifest["symbol"] not in SUPPORTED_SYMBOLS:
        raise SchemaError(
            f"unsupported symbol {manifest['symbol']!r}; supported: {SUPPORTED_SYMBOLS}"
        )
    expected_symbol = f"{manifest['base']}/{manifest['quote']}"
    if manifest["symbol"] != expected_symbol:
        raise SchemaError(
            f"inconsistent currencies: symbol {manifest['symbol']!r} vs "
            f"base/quote {expected_symbol!r}"
        )
    if manifest["timeframe"] not in SUPPORTED_TIMEFRAMES:
        raise SchemaError(
            f"unsupported timeframe {manifest['timeframe']!r}; supported: {SUPPORTED_TIMEFRAMES}"
        )
    if manifest["bar_open_convention"] != CANONICAL_BAR_OPEN_CONVENTION:
        raise SchemaError(
            "bar_open_convention must be the canonical convention string: "
            f"{CANONICAL_BAR_OPEN_CONVENTION!r}, got {manifest['bar_open_convention']!r}"
        )

    for key in ("expected_bars", "observed_bars"):
        value = manifest[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SchemaError(f"field '{key}' must be a non-negative integer, got {value!r}")
    return version


def _validate_window_shape(value, label: str):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SchemaError(f"{label} must be a [start, end) pair, got {value!r}")
    for stamp in value:
        if not isinstance(stamp, str):
            raise SchemaError(f"{label} timestamps must be ISO-8601 strings, got {stamp!r}")
    return tuple(value)


def _reject_noncanonical_timestamp(manifest: Mapping, key: str) -> None:
    """Fail closed on serialized timestamps outside canonical UTC Z notation.

    Policy decision: instead of silently interpreting ``+01:00``/``+00:00``
    spellings to the same instant (which would make the digest depend on the
    author's clock spelling), accepted manifests must declare timestamps in
    canonical UTC ``Z`` notation. Builders normalize; raw validators reject.
    """
    stamp = manifest[key]
    if isinstance(stamp, str):
        canonical = canonical_utc_text(stamp, key)
        if stamp != canonical:
            raise SchemaError(
                f"field '{key}' must use canonical UTC Z notation "
                f"{canonical!r}, got {stamp!r}; per-field offsets like "
                "'+01:00' would fragment the digest space"
            )


def _validate_temporal(manifest: Mapping) -> Tuple[datetime, datetime, Tuple[Tuple[datetime, datetime], ...]]:
    # Calendar validation propagates its own typed errors: NaiveTimestampError,
    # BarAlignmentError, EmptyIntervalError — all fail closed with actionable
    # messages, and the canonical gate convention (hourly UTC opens) is enforced
    # by construction.
    for key in ("start", "end", "created_at"):
        _reject_noncanonical_timestamp(manifest, key)
    start = as_utc(manifest["start"], "start")
    end = as_utc(manifest["end"], "end")
    if end - start > timedelta(hours=MAX_GRID_SPAN_HOURS):
        raise SchemaError(
            f"[start, end) span exceeds the supported limit of "
            f"{MAX_GRID_SPAN_HOURS} hourly bars; refusing to materialize an "
            "unbounded expected-bar grid"
        )
    if "maintenance_windows" in manifest and manifest["maintenance_windows"] is None:
        raise SchemaError(
            "maintenance_windows must be a list of [start, end) pairs, not "
            "null; declare [] explicitly for no maintenance downtime"
        )
    windows_raw = manifest.get("maintenance_windows", ())
    if not isinstance(windows_raw, (list, tuple)):
        raise SchemaError(
            f"maintenance_windows must be a list of [start, end) pairs, got {windows_raw!r}"
        )
    if len(windows_raw) > MAX_MAINTENANCE_WINDOWS:
        raise SchemaError(
            f"maintenance_windows exceeds the supported limit of "
            f"{MAX_MAINTENANCE_WINDOWS} entries, got {len(windows_raw)}"
        )
    windows_entries = tuple(
        _validate_window_shape(window, f"maintenance_windows[{index}]")
        for index, window in enumerate(windows_raw)
    )
    for index, window in enumerate(windows_entries):
        for position, stamp in enumerate(window):
            canonical = canonical_utc_text(stamp, f"maintenance_windows[{index}]")
            if stamp != canonical:
                raise SchemaError(
                    f"maintenance_windows[{index}][{position}] must use "
                    f"canonical UTC Z notation {canonical!r}, got {stamp!r}"
                )
    created_at = as_utc(manifest["created_at"], "created_at")
    return start, end, merge_maintenance_windows(windows_entries), created_at


def _validate_dataset_path_syntax(file_ref: str) -> Tuple[str, ...]:
    """Lexical dataset path validation — no filesystem access involved.

    Rejects: backslashes, drive/absolute/tilde'd references, empty, '.', '..'
    or whitespace-padded components, NUL bytes. Returns the path components
    for the later filesystem-level containment check inside verify_dataset.
    """
    if "\\" in file_ref:
        raise PathSafetyError(
            f"dataset.file must use '/' separators, got {file_ref!r}"
        )
    if not file_ref or file_ref.strip() != file_ref or file_ref in (".", ".."):
        raise PathSafetyError(f"dataset.file is empty or not normalized: {file_ref!r}")
    if ":" in file_ref:
        raise PathSafetyError(
            f"dataset.file must not contain ':' (drive paths are absolute): "
            f"{file_ref!r}"
        )
    if file_ref.startswith(("/", "~")):
        raise PathSafetyError(
            f"absolute paths are not allowed for dataset.file: {file_ref!r}; "
            "the reference must stay inside the allowed dataset root"
        )
    parts = file_ref.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise PathSafetyError(
                f"dataset.file must be a plain relative path without '.', '..' "
                f"or empty components: {file_ref!r}"
            )
        if part != part.strip() or "\x00" in part:
            raise PathSafetyError(f"dataset.file contains an unsafe component: {part!r}")
    return parts


def _validate_dataset(manifest: Mapping) -> Tuple[str, str]:
    dataset = manifest["dataset"]
    if not isinstance(dataset, dict):
        raise SchemaError(
            f"dataset must be an object with file/sha256/bytes, got {type(dataset).__name__}"
        )
    non_string_keys = sorted(repr(key) for key in dataset if not isinstance(key, str))
    if non_string_keys:
        raise SchemaError(
            "dataset keys must be strings, got non-string key(s): "
            f"{', '.join(non_string_keys)}"
        )
    extra_keys = sorted(set(dataset) - {"file", "sha256", "bytes"})
    if extra_keys:
        raise SchemaError(f"dataset has unknown key(s): {', '.join(extra_keys)}")
    file_ref = dataset.get("file")
    if not isinstance(file_ref, str) or not file_ref.strip():
        raise SchemaError(f"dataset.file must be a non-empty relative path, got {file_ref!r}")
    # Early lexical validation: malformed references fail at manifest build
    # and validation time, long before any filesystem is touched.
    _validate_dataset_path_syntax(file_ref)
    sha256_value = dataset.get("sha256")
    if not _is_sha256(sha256_value):
        raise SchemaError(
            "dataset.sha256 must be a lowercase 64-character hex SHA-256, "
            f"got {sha256_value!r}"
        )
    size = dataset.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise SchemaError(
            f"dataset.bytes must be a positive byte count, got {size!r}"
        )
    return file_ref, sha256_value


def _validate_provenance(manifest: Mapping) -> MappingProxyType:
    provenance = manifest["provenance"]
    if not isinstance(provenance, dict) or not provenance:
        raise SchemaError(
            "provenance must be a non-empty object of producer attestations"
        )
    for key, value in provenance.items():
        if not isinstance(key, str):
            raise SchemaError(f"provenance key must be a string, got {key!r}")
        if _is_sensitive_key(key):
            raise SchemaError(
                f"provenance key '{key}' looks like a credential field; secrets "
                "must never enter a manifest"
            )
        if not isinstance(value, str) or not value.strip():
            raise SchemaError(
                f"provenance['{key}'] must be a non-empty string, got {value!r}"
            )
    return MappingProxyType(dict(provenance))


def _validate_counts(manifest: Mapping, *, computed_expected: int) -> None:
    declared_expected = manifest["expected_bars"]
    if declared_expected != computed_expected:
        raise ManifestError(
            f"expected_bars {declared_expected} is inconsistent with the "
            f"[{manifest['start']}, {manifest['end']}) grid plus maintenance "
            f"windows; computed {computed_expected}"
        )
    observed = manifest["observed_bars"]
    if observed > declared_expected:
        raise ManifestError(
            f"observed_bars {observed} exceeds expected_bars {declared_expected}"
        )


def _validate_funding(manifest: Mapping) -> dict | None:
    """Single consolidated funding gate (null check + spot/perp rules).

    Returns the raw funding mapping for record construction, or None for
    spot datasets. Spot datasets must not carry funding metadata at all;
    perpetual datasets require exactly {interval_hours, applied}.
    """
    market_type = manifest["market_type"]
    funding = manifest.get("funding")
    if funding is None:
        if "funding" in manifest:
            raise SchemaError(
                "funding key present with null value; remove it for spot or "
                "provide a complete funding object for perp"
            )
    if market_type == "spot":
        if "funding" in manifest:
            raise FundingError(
                "spot datasets must not carry funding metadata; found key 'funding'"
            )
        return None
    if not isinstance(funding, dict):
        raise FundingError(
            "perpetual-futures datasets require an object 'funding' field, "
            f"got {funding!r}"
        )
    required = {"interval_hours", "applied"}
    missing = sorted(required - set(funding))
    if missing:
        raise FundingError(f"funding is missing required key(s): {', '.join(missing)}")
    extra = sorted(set(funding) - required)
    if extra:
        raise FundingError(f"funding has unknown key(s): {', '.join(extra)}")
    interval = funding["interval_hours"]
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        raise FundingError(
            f"funding.interval_hours must be a positive integer, got {interval!r}"
        )
    if not isinstance(funding["applied"], bool):
        raise FundingError(
            f"funding.applied must be a boolean, got {funding['applied']!r}"
        )
    return funding


@dataclass(frozen=True)
class FundingTerms:
    """Immutable, typed snapshot of perpetual-futures funding metadata.

    Remaining structural (scalar) fields make post-validation mutation
    impossible without a new instance. No funding payments or ledger live
    here — Stage 2 records only the dataset's funding *settings*.
    """

    interval_hours: int
    applied: bool


@dataclass(frozen=True)
class ManifestRecord:
    """Immutable accepted manifest. Mutating via attribute assignment raises."""

    schema_version: int
    provider: str
    venue: str
    market_type: str
    symbol: str
    base: str
    quote: str
    timeframe: str
    start: datetime
    end: datetime
    created_at: datetime
    bar_open_convention: str
    expected_bars: int
    observed_bars: int
    maintenance_windows: Tuple[Tuple[datetime, datetime], ...]
    dataset_file: str
    dataset_sha256: str
    dataset_bytes: int
    provenance: MappingProxyType
    digest: str
    funding: FundingTerms | None


def validate_manifest(manifest: Mapping) -> ManifestRecord:
    """Strictly validate a manifest mapping and return an immutable record.

    Fails closed with typed, actionable errors on missing/unknown/duplicate
    fields, unsupported schema/symbol/timeframe, naive or misaligned UTC
    boundaries, inconsistent bar counts, malformed digests, funding misuse
    and credential-like provenance keys. Never repairs anything.
    """
    if not isinstance(manifest, dict):
        raise ManifestError(f"manifest must be a mapping, got {type(manifest).__name__}")
    version = _validate_header(manifest)
    start, end, windows, created_at = _validate_temporal(manifest)
    _validate_dataset(manifest)
    provenance = _validate_provenance(manifest)
    grid = expected_grid(start, end, maintenance=windows)
    _validate_counts(manifest, computed_expected=len(grid))
    funding_raw = _validate_funding(manifest)

    recorded_digest = manifest.get(_DIGEST)
    if not _is_sha256(recorded_digest):
        raise ManifestError(
            "field 'digest' must be a lowercase 64-character hex SHA-256, "
            f"got {recorded_digest!r}"
        )
    computed = manifest_digest(manifest)
    if computed != recorded_digest:
        raise DigestMismatchError(
            f"manifest digest mismatch: recorded {recorded_digest}, "
            f"recomputed {computed} — the manifest content changed or the "
            "digest was built with a different serializer version"
        )

    dataset = manifest["dataset"]
    return ManifestRecord(
        schema_version=version,
        provider=manifest["provider"],
        venue=manifest["venue"],
        market_type=manifest["market_type"],
        symbol=manifest["symbol"],
        base=manifest["base"],
        quote=manifest["quote"],
        timeframe=manifest["timeframe"],
        start=start,
        end=end,
        created_at=created_at,
        bar_open_convention=manifest["bar_open_convention"],
        expected_bars=manifest["expected_bars"],
        observed_bars=manifest["observed_bars"],
        maintenance_windows=windows,
        dataset_file=dataset["file"],
        dataset_sha256=dataset["sha256"],
        dataset_bytes=dataset["bytes"],
        provenance=provenance,
        digest=recorded_digest,
        funding=(
            FundingTerms(
                interval_hours=funding_raw["interval_hours"],
                applied=funding_raw["applied"],
            )
            if funding_raw is not None
            else None
        ),
    )


@dataclass(frozen=True)
class VerifiedDataset:
    """Result of hashing a dataset file against a validated manifest."""

    file: str
    sha256: str
    bytes: int
    manifest_digest: str
    empty: bool = field(default=False)


def safe_dataset_path(dataset_root: Path, file_ref: str) -> Path:
    """Full path check: lexical validation + filesystem root containment.

    verify_dataset's defense-in-depth: even a lexically clean reference must
    resolve to a regular file strictly inside the *real* (resolved) dataset
    root — this is what stops symlink/directory-junction escapes that lexical
    validation alone cannot see.
    """
    parts = _validate_dataset_path_syntax(file_ref)
    root = Path(dataset_root).resolve()
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathSafetyError(
            f"dataset.file escapes the allowed dataset root: {file_ref!r} "
            f"resolves to {resolved} outside {root}"
        ) from exc
    if not resolved.is_file():
        raise PathSafetyError(
            f"dataset.file does not resolve to a regular file inside the "
            f"dataset root: {file_ref!r}"
        )
    return resolved


def verify_dataset(record: ManifestRecord, dataset_root) -> VerifiedDataset:
    """Hash the referenced dataset file inside *dataset_root* and verify it.

    Path-safety rules: relative '/'-separated references only, no absolute
    paths, drive letters, '..' traversal, drive-absolute or symlink
    components escaping the real (resolved) dataset root. Content checks:
    SHA-256 equality with the recorded pin, exact byte-size match and a
    non-empty file. Stage 2 stops here; bar-level CSV parsing belongs to the
    Stage 3 data adapter.
    """
    path = safe_dataset_path(Path(dataset_root), record.dataset_file)
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
            size += len(chunk)
    if size == 0:
        raise ManifestError(
            f"dataset {record.dataset_file!r} is empty (0 bytes); empty research "
            "datasets are rejected instead of being accepted silently"
        )
    if size != record.dataset_bytes:
        raise ManifestError(
            f"dataset byte size mismatch: recorded {record.dataset_bytes}, "
            f"actual {size}"
        )
    actual_sha = hasher.hexdigest()
    if actual_sha != record.dataset_sha256:
        raise DigestMismatchError(
            f"dataset content mismatch: recorded sha256 {record.dataset_sha256}, "
            f"actual {actual_sha} — the file changed after the manifest was sealed"
        )
    return VerifiedDataset(
        file=record.dataset_file,
        sha256=actual_sha,
        bytes=size,
        manifest_digest=record.digest,
        empty=False,
    )


def build_manifest(
    *,
    provider: str,
    venue: str,
    market_type: str,
    symbol: str,
    base: str,
    quote: str,
    timeframe: str,
    start,
    end,
    created_at,
    dataset_file: str,
    dataset_sha256: str,
    dataset_bytes: int,
    expected_bars: int,
    observed_bars: int,
    maintenance_windows: Sequence = (),
    provenance: Mapping[str, str],
    funding: Mapping | None = None,
) -> dict:
    """Build a complete, digest-stamped, ready-to-validate manifest dict.

    ``created_at`` is required (no hidden utcnow) so fixtures stay
    deterministic. The returned dict includes the canonical ``digest`` over
    every other field; validate it immediately so builders cannot emit wrong
    manifests silently.
    """
    manifest = {
        "schema_version": max(SUPPORTED_SCHEMA_VERSIONS),
        "provider": provider,
        "venue": venue,
        "market_type": market_type,
        "symbol": symbol,
        "base": base,
        "quote": quote,
        "timeframe": timeframe,
        "start": canonical_utc_text(start, "start"),
        "end": canonical_utc_text(end, "end"),
        "bar_open_convention": CANONICAL_BAR_OPEN_CONVENTION,
        "expected_bars": expected_bars,
        "observed_bars": observed_bars,
        "dataset": {
            "file": dataset_file,
            "sha256": str(dataset_sha256).lower(),
            "bytes": dataset_bytes,
        },
        "provenance": dict(provenance),
        "created_at": canonical_utc_text(created_at, "created_at"),
    }
    if maintenance_windows:
        manifest["maintenance_windows"] = [
            [
                canonical_utc_text(window[0], "maintenance.start"),
                canonical_utc_text(window[1], "maintenance.end"),
            ]
            for window in maintenance_windows
        ]
    if funding is not None:
        manifest["funding"] = dict(funding)
    manifest[_DIGEST] = manifest_digest(manifest)
    # Eager validation: a builder can never hand out an unsealed or invalid
    # manifest. Typed errors (naive timestamps, empty range, misaligned bar
    # opens, unsupported symbol/timeframe/market_type, funding misuse,
    # credential-like provenance keys) surface at build time.
    validate_manifest(manifest)
    return manifest
