# Stage 7 validation report

## Evidence classification

| Status | Actual evidence |
|---|---|
| IMPLEMENTED | Causal event records, fixed 4/16-bar labels, S/R ambiguity, conditional scenarios, expanding chronological diagnostics, untouched final holdout, four baselines, smoothed conditional frequency, calibration and paired session bootstrap |
| TESTED OFFLINE | Synthetic complete XNYS fixtures, deterministic numerical oracles, mocked provider pagination/batching, Windows Streamlit AppTest; public suite evidence below |
| EVALUATED WITH REAL HISTORICAL DATA | **No** Stage 7 evaluation. No credentials were read and no Market Data API download was performed during development |
| OUT-OF-SAMPLE VALIDATED | **No real predictive validation**. Synthetic chronological diagnostics test mechanics only |
| NOT YET VALIDATED | Real-data calibration, regime stability, cross-symbol consistency, independently authenticated vintage, licensing/entitlement, final holdout and any economic/trading benefit |

All user-facing scenario probabilities remain null. No price targets or success rates are inferred from synthetic fixtures. The final historical holdout has no evaluation switch.

## Factual commentary audit

At 35 replay checkpoints (21 through 259 bars, step 7), independently implemented scalar EMA recursion and Wilder RSI recursion agreed with the commentary evidence; RVOL was compared directly to current volume divided by the preceding 20 observations. Monotonically increasing/decreasing cases exercise EMA above/below and RSI 100/0. Missing zones, insufficient pivot/volume history and incomplete provenance are checked. Existing structure/zone tests separately verify HH/HL/LH/LL and equal/mixed states, confirmation timing, no backdated trendline geometry and correct historic zone display.

No factual commentary defect was demonstrated by these tests. They are not a proof that every possible input is correct and do not establish predictive value.

## Demonstrated provider defect and fix

The existing reader inferred the validation range from returned bars. If the requested first or last session was entirely absent, the remaining complete sessions could pass. A regression test reproduced **two failing cases before the fix**. The reader now compares returned timestamps to the originally requested calendar grid. Both cases pass by rejecting incomplete coverage. The separate Stage 7 collector also checks every requested batch; it never fills or relaxes missing IEX bars.

## Test scope and results

The verified Stage 6 base is 3a646e3477f741a793a62460ec66fa82167600ab. GitHub run #44 (40725369312), job 122947062110, directly inspected logs: 115 macro + 100 crypto + 31 FX + 194 workspace = **440 passed, zero failed/skipped**.

Stage 7 local complete run: **468 discovered, 467 passed, one existing Windows symlink-privilege skip, zero failures**. Suites: macro 115, crypto 100, FX 31, workspace 222. Exact timestamps and exit codes: [public_test_results.json](../evidence/public_test_results.json). The 28 new tests comprise 3 independent commentary tests, 24 research tests, and 1 Streamlit test. Final presentation changes also passed targeted replay/UI regression tests.

The first restricted run hit Windows temporary-directory access denial in the private-storage test. That was an environment permission failure, not an algorithmic failure. The unchanged test passed under normal local test permissions. No automated security review was bypassed and no integrity test was weakened.

Core checks cover:

- Feature and qualitative-scenario prefix invariance, pivot confirmation, historical line availability.
- Exact horizon completion and hidden future outcomes, endpoint return labels, S/R ambiguity, symmetric break definitions.
- Train-label purging, 16-bar embargo, chronological folds; replacing all holdout prices leaves development metrics identical.
- Hand-computed Brier/log loss/calibration and whole-session paired uncertainty, sparse-cell fallback.
- Insufficient history, actual data with unspecified feed, strict missing-bar/edge-session rejection.
- Explicit download consent, sealed dates before network, bounded batches, same-feed provenance, sanitized transport failure with no automatic retry.
- Private snapshot hash/coverage tampering, outside-Git storage, exclusive snapshot folder creation.
- Actual HTTP transport inspected through a mocked opener: GET-only market-data URL, no request body, no secret in URL, redirect refusal and sanitized HTTP 429. No live request is sent.
- Preserved chart plus all six Turkish research panels and replay result separation.

No new statistical result table is presented as market evidence: no qualifying real-data experiment has run.

## Interpretation boundaries

Ten hypothesis/horizon diagnostics are registered; running all three symbols adds multiple comparisons and must not be treated as ten independent confirmatory tests. No p-values or significance declarations are made. Session bootstrap recognizes intraday overlapping labels, but cross-session dependence and distribution shift remain. Split adjustment is not a historical vintage certificate and excludes dividends. Binary ties are not-positive. Metrics are direction diagnostics, not transaction P&L.

See [checkpoint](STAGE7_CHECKPOINT.md) for GitHub Actions verification and immutable source checks.

## Follow-up leakage audit — 29 October 2026

The initial implementation evidence above is historical. Nine new tests reproduce and guard against holdout exposure through chart/replay, moving partitions, invalid indices and unsafe private-writer inputs. Current local suite: 477 discovered, 476 passed, one existing Windows privilege skip; zero failures. See STAGE7_AUDIT.md and evidence/stage7_audit_checks.json. The audit found real software defects despite the earlier green suite; no real-market predictive claim follows from either test run.
