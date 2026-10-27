# Read-only relational SQL catalog

Added to the public portfolio on 28 October 2026 (Europe/Istanbul).

## Data model and queries

`research_workspace/catalog_sql.py` builds three tables in an ephemeral SQLite database:

| Table | Key | Purpose |
|---|---|---|
| sources | source_id | Publisher and unit |
| versions | version_id; source_id foreign key | Verification status, declared count, collection time and rejection reason |
| observations | (version_id, observation_date, series) | Verified numeric observations; version foreign key |

The coverage query uses JOIN, GROUP BY, COUNT, MIN and MAX per version and series. The reconciliation query uses LEFT JOIN to retain empty/rejected versions and CASE to distinguish a verified row-count match from a rejected version's NULL result. Multiple snapshots are never pooled into one time series.

## Trust and read-only boundaries

The public `reports()` entry point accepts no caller-supplied trust flag. It calls the existing catalog verifier on every request. Source registry, exact file set, manifest pins, collector digest, deterministic normalization and availability checks remain unchanged. Rejected snapshots contribute only rejection metadata, never observations.

Loading uses parameters, foreign-key enforcement and a composite primary key. Conflicting source metadata, duplicate observations and declared-count mismatches fail. After loading, `PRAGMA query_only=ON` prevents database writes. The database is in memory and closed after fixed queries; there is no arbitrary SQL input, persistent database, data collection or prospective evaluation in this feature.

The Streamlit **Gerçek Veri** page exposes reports on an explicit button click. Verification errors are shown as errors. No-data reports are empty; they do not establish a successful data audit. The test suite covers click-only execution and error presentation.

## Reproduction and limitations

Run `python -B tools/run_public_tests.py` in the documented Windows environment. The 12 new SQL/UI tests use synthetic fixtures. Public source collection remains a separate explicit command described in the README. No original provider datasets, personal paths or original private test evidence are included in this feature.

Counts and first/last dates do not establish trading-calendar completeness. Collection time does not prove a historical publication vintage. Local hashes are not publisher signatures. This is a small analytical catalog, not a production warehouse, a trading signal, or a predictive model.

V4.1 files and the prospective clock gate are unchanged. No order submission functionality is added.

## Observed-grid quality diagnostics (28 October 2026)

Quality reports summarize per-version/per-series min/max values, zero/negative counts, observed date counts and absences relative to the union of dates actually observed in that version. Zero/negative counts are descriptive, not universal error flags. Invalid source values are still rejected by the unchanged upstream verifier.

An SQL anti-join lists absent series/date pairs, including boundary dates. These are candidates for source review, not confirmed missing publications: series may start late, end early or have intentionally unavailable values. A separate LAG query lists calendar intervals between observations. It does not label weekends or holidays as data loss. No publisher calendar or expected series universe has been verified; calendar completeness is explicitly `unknown`, including empty results. Entirely absent series, dates absent across all series, and outside-range dates cannot be certified by this comparison.

Both detail lists are deterministically ordered and capped at 500 rows. Exact total counts and truncation flags remain available. No values are filled, no snapshots modified, and no versions combined. Eight additional tests cover partial grids, boundary absence, weekends, common missing dates, value summaries, version/rejection isolation, empty/single observations and capped detail output.

## Source-specific reference extension

The observed-grid diagnostics above remain separate. New `publication_summary` and `publication_missing` reports use hash-pinned source-specific metadata. Unknown range/source states are retained; the general `calendar_completeness` field remains unknown because no global completeness certificate is issued. See [review, source links and scope](PUBLICATION_CALENDARS.md).
