# Validation evidence

## Public package verification — 28 October 2026 (Europe/Istanbul)

The curated source copy was tested separately from the original checkout:

| Suite | Tests run | Skipped | Exit code |
|---|---:|---:|---:|
| Macro source/document/event-study contracts | 115 | 0 | 0 |
| Crypto calendar and manifests | 100 | 1 | 0 |
| Forex calendar/DST/rollover | 31 | 0 | 0 |
| Workspace adapters, evidence, real sources, SQL, finance and UI | 133 | 0 | 0 |
| **Total** | **379** | **1** | **all zero** |

**378 passed, 1 environment-dependent symlink test skipped.** Machine-readable
start/end times and exit codes are in `evidence/public_test_results.json`.

The test environment was the existing Windows Python 3.12 environment. Its
already-installed calendar dependency was exposed to the exported copy for this
run; no third-party vendor directory is distributed. This is not a claim that a
fresh internet installation, Linux, macOS or every package version was tested.
`requirements.txt` records the dependency versions observed locally, including
the previously installed calendar version.

## What was actually tested

Schema/URL/document rejection, timezone awareness, known-at availability, empty
and delayed windows, expected trading grids, duplicate and invalid bars,
manifest hashes, normalized-data reproduction, corrupted or altered records,
collector source changes, Windows no-replace version publication, recovery
after failed collection, read-only review, synthetic-label preservation and
Streamlit page behavior with missing private data. The 12 SQL tests additionally cover relational coverage, rejected-row exclusion, duplicate keys, manifest counts, source conflicts, parameterized inputs, query-only enforcement, fresh verification, version isolation and UI success/error paths.

Tests use synthetic fixtures and do not contact data providers or submit orders.
The two public-source live downloads were verified separately in the original
local workspace on 26 October; those raw files are not in this public package.

## Historical evidence — different scopes, not additive

- 23 October V4.1 report: 145 baseline/new tests and 523 byte-identical research
  artifacts on the original local cache/checkpoint.
- 25 October workspace release: 519 tests, 518 passed and 1 skipped across a
  broader original-project suite.
- 26 October real-source extension: 95 tests (70 workspace + 25 provenance), all
  passing, and 1,393 protected original files unchanged.

These counts overlap. They must not be added together as unique tests or shown as
fresh public-clone results. The public package does not include licensed market
caches, original checkpoints or all original protected outputs. It intentionally
does not manufacture a replacement integrity manifest to make missing evidence
look valid.

## Source integrity

`evidence/source_snapshot_sha256.json` recorded the publication-reference stage’s 89 source/test/config/reference
files. The original export and initial SQL publication inventories are preserved
in `evidence/archive/`. In the publication-reference stage, the SQL module and its UI integration changed;
a new publication-reference module, test module and pinned metadata file were added. The newer bytes are
not claimed to match the separate original application. V4.1 and the collector
remain unchanged. Documentation and packaging tools are separate additions.
This is a local hash inventory, not a publisher signature or independent audit.

Credential-pattern and personal-path scans found no unresolved matches in the
publication text files. A URL-userinfo fixture (`name@...`) was manually reviewed
and confirmed to be deliberate invalid test input rather than a credential.

## Reproduce safely

Run `python -B tools/run_public_tests.py` from a configured Windows environment.
The runner writes only public-package evidence and local temporary test fixtures.
It does not invoke the older credentialed data collector or frozen research
runners. Successful tests demonstrate those implemented contracts, not trading
profitability or completeness of an unseen-data evaluation.

## Historical SQL publication verification (d04372a)

The first restricted-environment attempt encountered Windows temporary-directory access errors in the crypto suite; console output then failed with a character-encoding error before the remaining suites ran. The runner now explicitly uses UTF-8 for subprocess and console output. The unchanged test selection was rerun with normal local permissions and completed: 328 tests, 327 passed, 1 symlink-privilege skip. No integrity check was relaxed. Result timestamps are UTC; this run occurred on 28 October in Europe/Istanbul.

The frozen V4.1 tree, all prior source fingerprints except the intended real-data UI change, and the collector remained byte-identical to the previous public commit. The new SQL module and tests match the original locally tested implementation. `evidence/sql_publication_checks.json` records these checks. Full raw logs remain local because they contain workstation paths; their hashes are recorded for traceability.

## Historical quality diagnostics publication (8b45682)

Fresh public-package selection: 336 tests, 335 passed and 1 Windows symlink-permission skip. Workspace now has 90 tests, including 8 new diagnostic tests. Initial regression tests detected Turkish text encoding errors introduced during editing; these were fixed before the successful rerun. Previous SQL publication evidence is archived under the `d04372a_` prefix; the preceding SQL publication section describes that historical stage. The current hash inventory includes the three modified SQL/UI/test files; these newer bytes are not claimed to match the separate original application. That original application and V4.1 were not modified in this stage.

That stage’s publication checks and local test-log hashes are recorded in `evidence/quality_checks.json`.

## Publication reference stage (28 October 2026)

346 tests ran: 345 passed and one symlink-permission skip. Ten new tests cover reviewed profiles, tenor activation, entirely missing dates/series, TARGET holidays, unknown/partial ranges, reference tampering, version isolation and bounded output. The previous 336-test evidence is archived with prefix `8b45682_`. Current checks are in `evidence/calendar_checks.json`. Read-only integration found 218 absent 1.5-month Treasury observations; original snapshot files stayed byte-identical. ECB had zero missing pairs in the reviewed overlap, but one leading snapshot date was outside that reference. Neither result is a point-in-time or global completeness certification.


## Stage 5 final acceptance — 28 October 2026

Stage 5 historical complete public run: 379 tests (378 passed, one Windows symlink-permission skip).
Suite counts: macro 115, crypto 100, FX 31, workspace 133. Exact start/end UTC times
and exit codes are in public_test_results.json. The final workspace suite ran in
7.956 seconds per its local log (see the exact log summary if platform timing differs).
Prior counts are historical, not additive. Checkpoint 1 ran 356; checkpoint 2 ran 379.
The first checkpoint-2 run had one UI test failure because it counted the generic
sidebar information box; the assertion was corrected to test the real-data label,
and the unchanged behavior passed the full rerun.

New deterministic tests cover 10 normalizer/lineage cases and 23 calculation/UI cases.
Manual examples validate spread signs, percent-to-basis-point conversion, log/simple
changes and ddof=1 rolling volatility. Prefix-invariance tests check that future
observations do not alter earlier outputs. UI tests compare displayed dataframes to
backend results and explicitly test no-data/rejected states.

Read-only original-project verification checked 2,415 source/data files captured
before Stage 5: none changed. The existing protected-artifact verifier independently
checked 1,393 files with no changes. The prospective gate remains closed until at
least 2027-01-21 21:15 UTC; evaluation is disabled. See stage5_acceptance.json.
The new derivative resides only in Git-ignored public-workspace storage.

Two authentic browser screenshots show the running verified-data application.
No data is distributed as part of the repo; missing-data AppTest coverage verifies
that a public clone remains usable without private caches. Existing installed Windows
Python/calendar dependencies were used; fresh dependency installation was not tested.

## Stage 7 development validation

Current local selection: 468 discovered, 467 passed, one existing Windows symlink-privilege skip; zero failures. The current source inventory has 115 files and preserves the previous inventory under archive/3a646e3_. Twenty-three tracked V4/V4.1 files were compared byte-for-byte with Stage 6 base 3a646e3; none changed. No original private cache or prospective dataset was inspected. See [Stage 7 validation](STAGE7_VALIDATION_REPORT.md), [checkpoint](STAGE7_CHECKPOINT.md) and [checks](../evidence/stage7_checks.json). Earlier counts in this document describe their historical stages and are not additive.
