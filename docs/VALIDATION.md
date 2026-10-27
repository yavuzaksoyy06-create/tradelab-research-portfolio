# Validation evidence

## Public package verification — 28 October 2026 (Europe/Istanbul)

The curated source copy was tested separately from the original checkout:

| Suite | Tests run | Skipped | Exit code |
|---|---:|---:|---:|
| Macro source/document/event-study contracts | 115 | 0 | 0 |
| Crypto calendar and manifests | 100 | 1 | 0 |
| Forex calendar/DST/rollover | 31 | 0 | 0 |
| Workspace adapters, evidence, real sources, SQL and UI | 90 | 0 | 0 |
| **Total** | **336** | **1** | **all zero** |

**335 passed, 1 environment-dependent symlink test skipped.** Machine-readable
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

`evidence/source_snapshot_sha256.json` records the current 81 source/test/config
files. The original export and initial SQL publication inventories are preserved
in `evidence/archive/`. In this stage, only the SQL module, its UI integration and
its tests changed relative to the previous source inventory. The newer bytes are
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

## Quality diagnostics publication

Fresh public-package selection: 336 tests, 335 passed and 1 Windows symlink-permission skip. Workspace now has 90 tests, including 8 new diagnostic tests. Initial regression tests detected Turkish text encoding errors introduced during editing; these were fixed before the successful rerun. Previous SQL publication evidence is archived under the `d04372a_` prefix; the preceding SQL publication section describes that historical stage. The current hash inventory includes the three modified SQL/UI/test files; these newer bytes are not claimed to match the separate original application. That original application and V4.1 were not modified in this stage.

Current publication checks and local test-log hashes are recorded in `evidence/quality_checks.json`.
