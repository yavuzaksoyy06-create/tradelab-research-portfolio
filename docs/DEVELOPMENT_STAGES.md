# Development stages

This is a curated snapshot of an existing local project, not a fabricated sequence of historical Git commits. The initial public commit contains earlier stages together. Stage ordering is architectural; exact dates are only given where execution evidence exists.

## 1. Support/resistance prototypes — V1 and V2

Implemented pivot/zone representation and iterative research scripts. These stages are retained for comparison in `research_sr` and `research_sr_v2`. They are not advertised as the final validated engine. The main learning was to make confirmation timing explicit rather than visually interpreting a pivot before future candles had completed.

## 2. Hypothetical execution — V3

Separated signal formation from trade accounting. Added explicit entry/exit rules, fixed holding horizons, costs and conservative treatment of OHLC candles whose internal path is unknown. A chart signal became a reproducible decision with assumptions, rather than a claim that an actual fill occurred.

## 3. Calendar-aware causal research — V4

Added XNYS session schedules, holidays/early closes, UTC-aware timestamps, strict complete-bar validation, causal feature snapshots and lifecycle tracking. Compared touch, rejection and trend-filtered variants with simple baselines. Preserved chronological diagnostic splits and reported costs, missing data and sample limitations. SQLite stored dataset metadata keyed by SHA-256.

## 4. Shared-capital portfolio — V4.1, 23 October 2026

Replaced the invalid idea of summing independently funded symbol experiments with a synchronized shared-cash timeline. Opening exits can release funds for opening allocations; unknowable intrabar proceeds cannot. Added aggregate exposure rules, deterministic symbol priority, ledger outcomes, portfolio risk and reconciliation invariants.

Applied paired session-block comparisons and withheld unstable statistics when sample requirements failed. Froze source/configuration hashes and a prospective window. The already-inspected replay was explicitly labeled historical, not fresh out-of-sample validation. V4.2 institutional validation was not claimed complete.

## 5. Research Terminal — 0.1.0 and 0.2.0

Built a local Streamlit/Plotly research interface around frozen engines. Added completed-bar market replay, decision inspection, portfolio/risk and audit views, explanatory exports and a separate future-data intake workflow. UI presentation reuses engine calculations instead of inventing a second financial implementation.

The historical terminal needs local evidence excluded from this public repository. Its source is retained for architecture review; absent evidence correctly blocks acceptance.

## 6. Trusted local production and immutable versions

Added producer registration, source/collector pins, receipts, sealed dataset folders, exact file-set verification, no-replace publication and read-only review. The equity prospective producer remains behind its original clock and data gates. Hashes establish local custody relative to a reference, not a vendor signature.

## 7. Multi-market foundations

Added a crypto UTC 24/7 calendar and versioned manifest contracts; Forex session/DST/rollover validation; and macro source/document schemas with availability, release and review constraints. Schema 3 audit fixes rejected malformed sources and inconsistent document provenance. No real crypto price feed or paid FX feed is claimed.

## 8. Research Workspace — 0.3.0 Preview, 25 October 2026

Created a separate dark local application with overview, Forex calendar, synthetic macro event-study lab, evidence audit and optional Turkish learning mode. Missing windows and not-yet-available observations suppress results. Every synthetic chart/result is visibly labeled. Original V4.1 and Terminal evidence remained preserved.

## 9. Real public reference sources — 26 October 2026

Added a separate read-only real-data page and explicit collectors for ECB daily FX reference rates and Treasury 2025 par yields. Stored raw XML, deterministic normalized CSV, source registry, collector digest, manifest and independent local pin receipt per version.

Kept TLS certificate validation, endpoint allowlists, no redirects, size/time limits and strict collector hash matching. A first Treasury version collected before the CA configuration change was retained but rejected by the new collector hash. A new version passed. No silent migration or hash-control weakening was used.

## 10. Public portfolio packaging — 27 October 2026

Exported reviewed source and tests into a separate repository without the original `.git`, credentials, brokerage configuration, licensed market caches, raw datasets, dependency vendor trees or personal workstation files. Added English technical documentation, Turkish CV guidance, source fingerprints and a public-package test selection. Original local files remain separate.

## 11. Read-only SQL catalog — 28 October 2026

Published the locally tested relational catalog and UI integration. Reports revalidate source snapshots, keep versions separate, reconcile declared and loaded rows, and exclude rejected observations. Added 12 SQL/UI tests; preserved strict collector hashes and the frozen V4.1 protocol. No source datasets are redistributed. [Design and limits](SQL_CATALOG.md).

## Next development priorities — not implemented in this snapshot

1. Broader independently reviewed SQL quality reports and dependency testing.
2. Provider-specific real intraday calendars and licensed OHLCV acquisition, if justified by research needs.
3. Point-in-time vintage evidence before using historical macro values in backtests.
4. Pre-registered new hypotheses and untouched samples; no parameter tuning against an already-inspected replay.
5. Independent review and broader dependency/platform testing.

None of these priorities authorizes broker orders or bypassing the frozen prospective gate.
