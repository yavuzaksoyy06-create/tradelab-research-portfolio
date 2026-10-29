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

## 12. Observed-grid quality diagnostics — 28 October 2026

Added per-series descriptive quality summaries, missing cells relative to observed dates, and calendar-gap diagnostics. Unknown publisher calendars remain explicitly unknown; no calendar completeness claim is made. Eight new tests accompany the read-only UI reports.

## 13. Source publication references — 28 October 2026

Reviewed official ECB calendar/currency sources and Treasury XML/developer notices. Added a bounded ECB TARGET comparison and a retrospective Treasury 2025 publication grid, with pinned reference metadata and ten new tests. The report exposes an existing omitted Treasury tenor without changing the collector or accepting new hashes for historical snapshots.

## 14. Stage 5 Financial Analytics Lab — 28 October 2026

Checkpoint d1a5c29 introduced offline v2 remediation; faa90de introduced validated financial transforms and Streamlit views. The final checkpoint supplies authentic screenshots, methods, case study, CV guidance and acceptance evidence. No new data was downloaded and frozen research remained unchanged.

## 15. Stage 6 — read-only causal Equity Research Lab, 28 October 2026

Added an isolated Streamlit page for SPY, MSFT and QQQ. Synthetic fixtures, optional explicitly loaded Alpaca historical IEX/SIP bars and user CSVs share strict completed-bar XNYS validation. Chart replay includes historical S/R zone bands, confirmed swing/structure labels, non-backdated trendlines, EMA 9/21/50/200, Wilder RSI and RVOL, as well as descriptive Turkish commentary. Provider GET never sends orders or stores public price caches. The frozen V4/V4.1 source, outputs and prospective gate were left untouched. [Equity contract](EQUITY_RESEARCH_LAB.md).

## 16. Stage 7 — registered conditional-outcome research and leakage audit, 28–29 October 2026

Registered fixed 4/16-bar descriptive outcomes, expanding chronological diagnostics with purging/embargo, four baselines, smoothed conditional frequencies, calibration and a reserved final 20-session historical holdout. Initial tests verified mechanics but a subsequent adversarial review found replay label leakage and a cursor-dependent holdout boundary. These paths, invalid indices and unsafe metadata publication were fixed with nine additional tests. [Audit](STAGE7_AUDIT.md), [protocol](STAGE7_RESEARCH_PROTOCOL.md).

The final audited Windows CI checkpoint passed 477 public offline tests; a separate Linux probe exposed Windows-only no-replace publication behavior and does not establish Linux portability. **No qualifying real historical Stage 7 predictive study has been run, no scenario probabilities released and no broker orders sent.** The separate frozen prospective gate remains 21 January 2027, 21:15 UTC.

## Open research and engineering work — not yet completed

1. Independently archived point-in-time market-data vintage and licensing/entitlement review.
2. Qualifying real-data calibration and cross-symbol stability review under a freshly registered protocol; no retrospectively invented out-of-sample period.
3. Linux implementation of immutable publication without weakening no-overwrite guarantees, followed by full cross-platform CI.
4. A separately opted-in, synthetic-only public demo if deployment is suitable; no real keys or private market caches in a hosted app.

None of these next steps authorizes broker orders or changes frozen historical research.
