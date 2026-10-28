# Stage 7 checkpoint

## Verified starting state (2026-10-28)

- Repository: yavuzaksoyy06-create/tradelab-research-portfolio.
- Branch: feature/equity-lab-stage6-slice1, base 3a646e3477f741a793a62460ec66fa82167600ab.
- PR #1: open, draft, not merged; base main aaafafe2e3ff5228b2ed06ecfda2c6ac08c0dbd5.
- Actions run #44 / 40725369312, job 122947062110: Windows Python 3.12, success. Job logs inspected directly, not inferred from an old README.
- Stage 6 modules inspected: data/provider, indicators/volume, zones/structure/commentary, UI, tests and frozen causal/calendar engine. No real dataset or sealed cache opened.
- Previous Stage 5 audit is safely preserved separately at checkpoint/stage5-audit, commit 6d33336; it was not force-pushed into the independently advanced main.
- Existing UI and commentary are descriptive. No calibrated predictive probabilities exist.

## Frozen boundaries

V4/V4.1 files remain unchanged. The prospective window starts 2026-10-26; its original release gate is 2027-01-21 21:15 UTC. Stage 7 v1 rejects that window outright, with no unlock option. No orders, automatic downloads, or private price commits. No PR merge.

## Implementation progress

Protocol/audit checkpoint: `821fee5`. Implementation checkpoint: `410d0f3`.

- Added stage7_events.py, stage7_validation.py, stage7_scenarios.py, stage7_history.py, stage7_ui.py and tools/stage7_research.py.
- Added three test modules (28 new tests); retained all earlier tests. Existing equity UI integration is two added lines. Existing provider has a two-line requested-calendar completeness fix.
- Local full suite: 468 discovered / 467 passed / 1 pre-existing Windows symlink privilege skip, zero failures. Latest presentation change also passed targeted UI/prefix regression.
- Source inventory: 115 files. All 23 tracked V4/V4.1 files byte-identical to the verified base; no private cache was read. The gate remains unchanged.
- Real historical evaluation: not run. Real calibrated predictive value: not established. Scenario probabilities: always suppressed. No broker orders or Market Data API downloads performed.
- Final holdout: never labeled/scored; no unlock switch. Offline code uses expanding training, fixed ten-session validation folds, 16-bar embargo and final 20-session holdout.
- Six Turkish UI panels and JSON/CSV summary exports implemented. Explicit historical download writes a new private snapshot outside Git, with coverage and hash manifest.

See [validation report](STAGE7_VALIDATION_REPORT.md), [limitations](STAGE7_LIMITATIONS.md) and [machine-readable checks](../evidence/stage7_checks.json). No Stage 5 audit changes were silently merged from the separate checkpoint branch.

## Reproducibility

On Windows / Python 3.12, use this development branch in a portfolio clone separate from the original TradeLab installation. Install requirements.txt, then run `python -B tools/run_public_tests.py`. The Streamlit entry point is `research_workspace/app.py`; choose Equity Research and the synthetic source for a fully offline check. Run only on 127.0.0.1.

The optional collection/evaluation commands are in STAGE7_LIMITATIONS.md. They require explicit consent, local environment credentials and a new private destination; they were not executed against a real provider in this stage.

## Upcoming work requiring actual evidence

An independently reviewed licensed historical snapshot, fixed experiment registration per symbol/feed, real OOS calibration and stability review, and separately authorized final-holdout handling remain outstanding. More dashboard polish or synthetic test success cannot substitute for these.

## Inspected GitHub checkpoint

Actions [run #45](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/runs/40731528521) at `2fcc36200b45eda76db2497a02730fe80c492595`: completed successfully; direct job logs show **467 passed, zero skipped/failed**. Windows runner could execute the symlink case skipped locally. A subsequent regression test verifies the actual GET request path/method, absent request body, redirect refusal and sanitized HTTP 429; local total is now **468 / 467 passed / one privilege skip**. PR checks identify the final head's separate CI run; this recorded #45 result is not relabeled as a test of a later commit.

Publication review: no price dataset additions, no credential-pattern or workstation-personal-path matches in the 22 changed files at 2fcc362. The only added credential-like literals are deliberate test sentinels. Source hashes are checked, prior evidence archived, draft PR retained and main not merged.
