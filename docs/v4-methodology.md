> Archived methodology from the original local project. Paths, private cache prerequisites and historical test counts below are not public-package verification. Do not run archive commands without reading the repository README.

# TradeLab V4 — causal support/resistance research

Status: audited V3 reproduction, validated SIP data, causal features, three long-only entry models, and preliminary chronological experiments. This is an offline arithmetic simulator, not an order-routing system.

## Quick start (Windows PowerShell)

~~~powershell
Set-Location <LOCAL_PROJECT>
& .\.venv\Scripts\python.exe -B -m research_sr_v4.run_tests
& .\.venv\Scripts\python.exe -B -m research_sr_v4.audit_v3
& .\.venv\Scripts\python.exe -B -m research_sr_v4.data
& .\.venv\Scripts\python.exe -B -m research_sr_v4.research
& .\.venv\Scripts\python.exe -B -m research_sr_v4.verify_outputs
~~~

The data command uses a verified local cache when available. A missing cache causes a read-only historical API request using existing credentials; it never switches SIP to IEX. Research reruns overwrite V4 output tables deterministically. Archive an experiment directory before changing code or settings. Original versions and configuration must remain untouched.

## Architecture

- audit_v3.py: exact original MSFT reproduction, independent fill/risk arithmetic, confirmation-time checks, and synthetic defect probes.
- data.py: explicit SIP/split historical ingestion, RTH selection, XNYS holiday/early-close calendar, completeness and integrity checks, CSV cache with SHA256/JSON metadata and SQLite dataset index.
- causal.py: prefix-invariant streaming pivot/zone engine; lifecycle and per-bar snapshots.
- execution.py: next-bar long-only accounting, fixed stops/targets, adverse costs, conservative intrabar collision policy, cash/mark-to-market equity, EOD flat policy.
- research.py: frozen protocol, chronological splits, five strategy/control variants, 10%-allocation buy-and-hold comparison, validation sensitivity, test folds, descriptive uncertainty and equity plots.
- run_tests.py: five isolated subprocess suites, structured counts and protected-file verification.
- verify_outputs.py: cached-data rerun of 45 test CSVs, source hashes, V3/refetched SIP comparison and production-import check.
- tests/: deterministic financial invariants, real cached-data integrations, V3 regression.
- out/: evidence, RTH caches, metadata, lifecycle/features, decisions, trades, equity, metrics and logs.

## Data contract

Bars are start-labelled, timezone-aware, UTC. bar_end is 15 minutes later. Session labels use New York dates. XNYS schedules determine every expected opening and closing timestamp, including DST and shortened days. Duplicate timestamps, NaN/infinite/invalid prices, inconsistent OHLC, negative volume, naive times, unfinished bars and missing expected bars abort validation. No interpolation or forward fill.

Extended-hours rows from Alpaca are explicitly removed and counted. All expected RTH bars must exist. A truncated day invalidates a run before any hypothetical fills are committed. Validation does not prove the provider's economic accuracy; raw provider responses outside RTH are not retained. Cached files are normalized RTH data, not raw HTTP payloads.

Corporate action policy: Alpaca split adjustment, not total return. Dividends are not included; historical adjustments are not a point-in-time corporate-action archive. CSV is adequate for 11,076 bars; a Parquet dependency is unnecessary at this scale.

## Frozen research definitions

All settings are in EXPERIMENT_CONFIG.json; origins are design choices, not fitted profit-maximizers.

- Strict pivots: three bars on each side, available only at the close of the third right-hand bar (inherited from V3).
- Wilder-style ATR: 14-bar recursive average; warm-up suppresses initial signals.
- Rolling pivot memory: 520 trading bars, approximately 20 full sessions; fixed engineering choice.
- Zone member width: ±0.20 ATR measured at confirmation. Same-kind connected intervals merge transitively if gap is at most 0.10 current ATR. Older member intervals expire individually; whole zones expire when no members remain.
- Support invalidates after two closes below lower edge minus 0.25 ATR; resistance mirrors this rule. Lifecycle timestamps are known-at times.
- A new independent touch requires departure/re-entry and at least four bars since that zone's last counted touch. A newly merged zone must be left again before another touch. Touch counts are lifetime diagnostics, not a rolling significance estimate.
- At least two confirmed pivots are required for actionable support. Same signal candle contacting multiple eligible supports is rejected. Support and resistance retain separate identities; shorts are not simulated.
- A: eligible support contact at completed candle.
- B: A plus close above upper edge, close above open, and close-minus-low at least 0.10 ATR. This is same-candle rejection, not a discretionary later rebound.
- C: B plus completed session-anchored hourly EMA9 > EMA21 and last hourly close > the close three completed hours earlier, after at least 21 completed hourly buckets. Incomplete closing hourly buckets are ignored.
- Relative volume uses the preceding 20 bar volumes; recorded as a diagnostic, not an entry requirement or a seasonally adjusted volume signal.
- Trend baseline: eligible hourly uptrend on every fourth global bar. Timed control: every fourth global bar regardless of trend. Both use the same risk, cost and horizon policy, a synthetic one-ATR stop geometry, and a five-session warm-up. These are controls, not matched-exposure counterfactuals.

## Execution contract

Signal must be known exactly at the signal bar's end; the immediately following same-session opening is the earliest entry. No overnight entries from a final candle. Entry distance outside the zone is limited to 0.50 ATR. Raw open at/below the fixed stop is rejected before costs. Stops are lower edge minus 0.10 ATR.

Defaults: 100,000 virtual USD, planned risk <=0.5% of current equity, entry notional <=10%, daily close-observed drawdown threshold 2%. Whole shares and available cash cap quantity. Known entry/exit fees and spread/slippage are included in planned stop risk. Target geometry yields 2R net of assumed costs. Defaults assume 1bp half-spread + 2bp slippage per side, zero fees; these are assumptions, not measured bid/ask spreads.

A gap through stop exits at observed open with adverse costs. A gap beyond target also uses observed open, never an untraded historical target. If both stop and target are touched intrabar, stop wins and ambiguity is recorded. Full-session data is required. Exit after at most four held bars at close or at exchange session close, whichever arrives first; intrabar stop/target has priority. An open position blocks another entry, including the same bar as its exit.

Cash pays entry notional and fees and receives exit proceeds minus fees. Equity is cash plus remaining position valued at each candle close. Daily threshold is checked at close; if breached while still holding, liquidation occurs at next available same-session open, with EOD closure taking priority on the final candle. Gap losses can exceed planned risk. This is not an intrabar hard loss guarantee.

Observed MFE/MAE includes the entire entry-through-exit candle ranges, which can contain post-exit movement. Exact position-valid MFE/MAE is null on intrabar exits whose sequence is unknown; lower/upper bounds are reported instead. Gap/open and scheduled close exits can have exact bounds. No one-minute execution resolution is implemented.

## Validation and output interpretation

70 chronological training sessions, 30 validation sessions, 42 held-out test sessions. The test is additionally partitioned into three consecutive 14-session walk-forward blocks; prior history remains available to the causal engine. Parameters are fixed, so this is rolling causal evaluation without model refitting or winner selection. Fold accounts reset; fold P&L must not be summed as a compounded portfolio.

Three zone widths and four costs are compared only in validation, with all combinations retained. No test-based parameter selection. Future changes must use a new research version and new holdout; this test has now been examined.

Metrics include decisions/rejections, trades, trade sessions, wins/losses, USD/R expectancy, profit factor when defined, close-marked drawdown, exposure proxies, costs, regimes and five-session block-bootstrap intervals. Sharpe/Sortino are withheld below 60 sessions or 30 trades. Flat strategies produce zero-P&L bootstrap distributions, not evidence of robustness. Other sparse-trade intervals are descriptive only. Exposure is a bar/open-notional proxy, not exact intrabar time-weighted exposure. A losing high-turnover control does not establish alpha for an inactive strategy.

Each symbol/strategy is an independent 100k account. There is no shared multi-symbol capital allocator, consolidated portfolio drawdown engine, or brokerage connection.

## Dependencies and preservation

Existing environment: Python 3.12.10, numpy 2.5.4, pandas 3.1.0, alpaca-py 0.44.0, python-dotenv 1.2.4, matplotlib 3.11.2. Isolated additions in vendor/: exchange-calendars 4.13.2, pyluach 2.3.0, toolz 1.2.0, korean-lunar-calendar 0.4.0. See DEPENDENCIES.json. The existing .venv packages and root requirements were not changed. A calendar-library pandas deprecation warning is non-fatal in the tested environment.

V3 source/output backup: backup/v3_original/. Original 47-file fingerprints: out/protected_hashes_before.json. Do not modify .env, broker settings, V1–V3, ATLAS, Windows security or TradingView MCP settings. SUBMIT_PAPER_ORDERS=NO was verified unchanged. No real, paper, or replay order was submitted.

## Incomplete priorities

P3 remains preliminary: exact exposure-matched controls, joint portfolio risk, genuinely unseen subsequent samples, broader regimes, robust multiple-testing analysis, full point-in-time corporate actions and one-minute execution resolution remain open. P4 Streamlit dashboard is deliberately not implemented until these research limitations are addressed. Generated plots/CSVs are real research outputs, not mock performance.

See RESEARCH_REPORT.md, project-level TRADELAB_PROJECT_STATE.md and Turkish HANDOFF_FOR_CHATGPT.md.

