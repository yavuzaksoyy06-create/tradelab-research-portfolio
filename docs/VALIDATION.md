# Validation evidence

## Public package verification — 27 October 2026

The curated source copy was tested separately from the original checkout:

| Suite | Tests run | Skipped | Exit code |
|---|---:|---:|---:|
| Macro source/document/event-study contracts | 115 | 0 | 0 |
| Crypto calendar and manifests | 100 | 1 | 0 |
| Forex calendar/DST/rollover | 31 | 0 | 0 |
| Workspace adapters, evidence, real sources and UI | 70 | 0 | 0 |
| **Total** | **316** | **1** | **all zero** |

**315 passed, 1 environment-dependent symlink test skipped.** Machine-readable
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
Streamlit page behavior with missing private data.

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

`evidence/source_snapshot_sha256.json` records the 79 exported source/test/config
files as copied from the original project. Their contents were verified unchanged
after export. Public documentation and packaging tools are additions. This is a
local hash inventory, not a publisher signature or independent third-party audit.

Credential-pattern and personal-path scans found no unresolved matches in the
publication text files. A URL-userinfo fixture (`name@...`) was manually reviewed
and confirmed to be deliberate invalid test input rather than a credential.

## Reproduce safely

Run `python -B tools/run_public_tests.py` from a configured Windows environment.
The runner writes only public-package evidence and local temporary test fixtures.
It does not invoke the older credentialed data collector or frozen research
runners. Successful tests demonstrate those implemented contracts, not trading
profitability or completeness of an unseen-data evaluation.
