"""TradeLab 0.3.0 — isolated 24/7 crypto research extension (Stage 1).

This package is independent from the frozen US-equity engines
(research_sr_v4, research_sr_v4_1) and from research_terminal. Stage 1 scope:
a deterministic, UTC-only 24/7 research calendar with hourly bar-open grids
and strict observation validation. No data download, no broker integration,
no strategy logic.
"""
from .calendar import (
    BarAlignmentError,
    CalendarError,
    CalendarReport,
    EmptyIntervalError,
    MaintenanceWindowError,
    NaiveTimestampError,
    as_utc,
    expected_grid,
    merge_maintenance_windows,
    validate_bars,
)
from .manifest import (  # Stage 2: crypto dataset manifest engine (see manifest.py)
    CANONICAL_BAR_OPEN_CONVENTION,
    DATASET_FIELD_ALIASES,
    DigestMismatchError,
    FundingError,
    FundingTerms,
    ManifestError,
    ManifestRecord,
    MAX_GRID_SPAN_HOURS,
    MAX_MAINTENANCE_WINDOWS,
    PathSafetyError,
    SchemaError,
    SchemaVersionError,
    SUPPORTED_SCHEMA_VERSIONS,
    SUPPORTED_SYMBOLS,
    SUPPORTED_TIMEFRAMES,
    VerifiedDataset,
    build_manifest,
    canonical_manifest_bytes,
    canonical_utc_text,
    manifest_digest,
    parse_manifest,
    validate_manifest,
    verify_dataset,
)

__version__ = "0.1.0.dev1"  # Stage 1 of the 0.3.0 program (see CRYPTO_RESEARCH_PLAN_030.md)

#: Markets supported in Stage 1/2. SOL/USDT stays explicitly out of scope.
SYMBOLS = ("BTC/USDT", "ETH/USDT")


def resolve_symbol(symbol):
    """Return *symbol* if it is a supported Stage 1 market, else raise ValueError."""
    if not isinstance(symbol, str) or symbol not in SYMBOLS:
        raise ValueError(
            f"unsupported symbol {symbol!r}; Stage 1 supports {', '.join(SYMBOLS)}"
        )
    return symbol
