> Archived methodology from the original local project. Paths, private cache prerequisites and historical test counts below are not public-package verification. Do not run archive commands without reading the repository README.

# Portfolio research report — TradeLab 4.1.0

Date: 2026-10-23. This report describes deterministic local historical simulation, not submitted broker orders. V4.2 institutional statistical validation is not represented as complete.

## Conclusion

Shared-capital accounting is implemented and tested. No robust economic advantage is demonstrated. All three candidates lose money in the already-inspected 42-session replay. The touch candidate's descriptive paired daily difference versus its matched timing controls has an interval spanning zero. Rejection and trend-filtered samples are too sparse for the interval gate. No new untouched out-of-sample result exists.

## Baseline preservation and implementation

The original baseline reran successfully: 98 tests. Its hardcoded runner was invoked in checkpoint/ against byte-identical preserved source/data, so original outputs were not overwritten. 419 original files remain hash-identical, including V1–V4 source and outputs. New tests execute the authoritative new package. Recoverable checkpoint includes previous source/data and root handoff documents; no credentials were copied.

V4's unchanged causal feature engine is reused. A new synchronized timeline owns one cash pool, all positions, sequential deterministic allocation and portfolio-wide daily high-water risk. One symbol's unknown intrabar exit cannot finance another symbol's opening entry. Opening exits can release capital. Every accepted/rejected signal has a ledgered outcome. All output CSVs retain columns when empty.

100,000 USD starting cash; 10% maximum new position notional, 0.5% planned risk, 30% post-cost opening aggregate exposure, three positions maximum, one per symbol, long-only, no margin, EOD flat. Explicit allocation priority: MSFT, SPY, QQQ. Daily observed drawdown 2% blocks new entries and queues surviving positions for the next open; realized loss is not capped at 2%. Fixed opening costs: 3bp per side, zero percentage fees. Four-bar holding horizon and original V4 signal definitions are unchanged.

Daily drawdown now uses observable session high-water equity rather than V4's day-start basis. Opening exits are processed before allocations. These are explicit portfolio policies; numerical differences versus the sum of independent-account results are expected. No results were constructed by adding independent-account P&Ls.

## Data and frozen protocol

Read-only existing SIP/split-adjusted cache: April 1–October 22, 2026, 142 full XNYS sessions and 3,692 fifteen-minute bars per instrument. No network or new data download was needed. Complete matching calendars, timestamp ordering, timezone awareness, hashes and metadata are verified. Dividends and point-in-time corporate-action archives are absent.

| Symbol | Dataset SHA256 |
|---|---|
| MSFT | 97dd93d2e3a0b9f3c61f17e235cc6bac1367817d6eb2e18da73f60d381cb7d8c |
| QQQ | 89aa8458cdcff2da4d5e5b86f70f1956429a29a312eed50044ec47da5c9b432b |
| SPY | e831ad3b75d6953cd5639db0b6b7301040deadb96032641d88bd8ee8a1b60fd6 |

Protocol frozen at 2026-10-23T18:41:04.329598+00:00; SHA256 93e311df4885c13823dbf0db705c75dd0c9c6488bf8d8b2d114de237d80c7f6b. The manifest pins 12 source files across V4.1 and reused V4 modules. Production changes invalidate the protocol rather than silently changing a saved experiment.

## Consolidated portfolio diagnostics

Each candidate starts a separate comparison experiment with one shared 100k portfolio across all three symbols. These candidate variants are not simultaneously funded strategies.

| Period | Candidate | Signals | Trades | Active sessions | Net USD | Return % | Max observed DD % |
|---|---|---:|---:|---:|---:|---:|---:|
| training_diagnostic | rejection | 24 | 4 | 3 | 23.40 | 0.0234 | 0.0854 |
| training_diagnostic | touch | 143 | 92 | 41 | -130.11 | -0.1301 | 0.5264 |
| training_diagnostic | trend_filtered | 7 | 2 | 1 | 105.92 | 0.1059 | 0.0029 |
| validation_diagnostic | rejection | 10 | 3 | 3 | -12.27 | -0.0123 | 0.0506 |
| validation_diagnostic | touch | 70 | 38 | 18 | -167.63 | -0.1676 | 0.3066 |
| validation_diagnostic | trend_filtered | 1 | 0 | 0 | 0.00 | 0.0000 | 0.0000 |
| observed_replay | rejection | 20 | 9 | 7 | -131.15 | -0.1312 | 0.1312 |
| observed_replay | touch | 103 | 53 | 28 | -93.36 | -0.0934 | 0.2335 |
| observed_replay | trend_filtered | 6 | 4 | 4 | -24.88 | -0.0249 | 0.0520 |

Periods: training diagnostic April 1–July 13 (70 sessions), validation diagnostic July 14–August 24 (30), observed replay August 25–October 22 (42). All have been examined; none is newly untouched. No SR parameter tuning was performed.

## Matched comparisons

Each observed candidate opportunity produces one intended control for the same instrument/session/hourly bucket. A deterministic hash of seed and anchor selects a 0–3-bar delay, clipped to known calendar boundaries. The prior anchor percentage geometry is translated at the later completed close. Same costs, horizon, stop/target policy, portfolio risk and allocation constraints apply. Seeds: 11, 23, 37, 51, 71; all are retained.

This is a conditional timing comparison. It does not isolate the causal benefit of detecting support/resistance. Actual fills, risk utilization, holding durations and exposure can differ. Future realized returns or exits are never used to force equality. Seeds are not independent market observations. The same total portfolio-session blocks are resampled for paired differences, retaining within-session cross-symbol dependence.

| Candidate | Candidate avg exposure % | Control avg exposure % | Control / candidate exposure | Candidate trades | Mean control trades | Daily difference USD | 95% descriptive paired interval |
|---|---:|---:|---:|---:|---:|---:|---|
| rejection | 0.2405 | 0.2823 | 1.1735 | 9 | 9.6 | -0.4718 | not estimated: insufficient active sessions |
| touch | 1.3254 | 1.3177 | 0.9942 | 53 | 52.8 | 2.5740 | [-0.2866, 6.4930] |
| trend_filtered | 0.0790 | 0.1183 | 1.4970 | 4 | 4.0 | -0.6855 | not estimated: insufficient active sessions |

For touch, realized exposure is close to matched (ratio about 0.9942), but the paired interval includes zero. Rejection and trend-filtered controls have material exposure mismatch; the report does not label these exact exposure matches. Their sparse paired sessions fail the interval gate. No multiple-comparison-adjusted significance or causal alpha claim is made.

Bootstrap: 1,000 circular five-session blocks, minimum 20 sessions and 10 active paired sessions. Single-candidate intervals require 10 active trade sessions. Sharpe requires 60 sessions, 30 trades and 30 active trade sessions, so every 42-session replay Sharpe is null. Zero activity is not success. Exposure-normalized returns are bar-open proxies, not exact intrabar time weighting.

All seed net P&Ls are disclosed:

| Candidate | Seed 11 USD | Seed 23 USD | Seed 37 USD | Seed 51 USD | Seed 71 USD |
|---|---:|---:|---:|---:|---:|
| rejection | -45.50 | -143.13 | -177.85 | -86.85 | -103.37 |
| touch | -136.66 | -190.67 | -163.27 | -309.29 | -207.46 |
| trend_filtered | -5.10 | 41.11 | -29.08 | 17.72 | -5.10 |

The risk-consistent simple trend portfolio executed 256 trades for -1659.25 USD. Its exposure/turnover remains higher and it is a separate baseline, not the matched counterfactual.
Shared-cash buy-and-hold reference returned 575.60 USD with initial 10% allocation per symbol. It holds overnight, has no stops or daily lock, and excludes dividends and cash yield. It is not risk-equivalent.

## Cost sensitivity

All validation cost cases are retained; no winning cost/parameter combination was selected. Each number below is net hypothetical USD for the 30-session validation diagnostic.

| Cost per side bp | touch | rejection | trend_filtered |
|---:|---:|---:|---:|
| 0 | 30.45 | 4.95 | 0.00 |
| 3 | -167.63 | -12.27 | 0.00 |
| 6 | -364.79 | -29.50 | 0.00 |
| 10 | -649.89 | -52.46 | 0.00 |

Per-regime trade counts/P&L, explicit rejection reasons, transaction costs, mean R, profit factor and cash/equity records are in comparison_results.json and each experiment directory. 'Other' is not a sophisticated bear/sideways regime model.

## Verification and independent accounting evidence

Final suite: 145 passed (98 previous + 47 new), zero failures/skips. The eight new real-data/integration checks include all candidates, reverse-input deterministic replay, controls, timezone normalization, future gate and exact V3 MSFT executions.
Full frozen rerun reproduced 523 CSV/metrics/audit/comparison artifacts byte-for-byte. 419 protected original file hashes were unchanged. No broker trading-module imports found in new code.
Touch replay maximum accounting identity error: 5.82e-11 USD (floating-point roundoff; gate tolerance 1e-7 USD). Its final cash 99906.63679275 equals initial cash plus realized net trade P&L; all positions end flat.

Tests exercise simultaneous signals/exits, opening-versus-intrabar capital release, fees once, no cash borrowing, entry caps, marked exposure drift events, multi-zone and exact duplicates, gap losses beyond planned risk, daily reset/lock/next-open liquidation, stop-before-rebound excursions, incomplete/duplicate/unsorted/naive data and future mutations. A schema test initially hit sandbox temp-directory denial and a rising-exposure fixture initially specified an invalid stop; both harness issues were corrected and final tests rerun.

## Future window and incomplete work

The frozen future window is 2026-10-26–2027-01-21 (60 sessions), not complete until 2027-01-21 21:15:00+00:00. Time gate currently fails; no new data loaded and no new performance evaluated.

Implemented: source-hashed protocol and time gate. Not implemented: a dedicated future-data downloader/manifest intake/evaluation CLI. The future adapter must validate full sessions and unchanged source/dependency/data semantics before invoking the existing engine. Do not silently reinterpret current replay as new out-of-sample evidence.

Remaining limits: conditional timing controls rather than an independent SR-detection control; imperfect realized exposure matching; no multiplicity-adjusted inference; only three correlated assets and one historical window; same-calendar only; no latency/auction/quote/volume-capacity modeling; no one-minute path resolution; no total-return corporate actions; float rather than production money ledger; no mark-to-market rebalancing after exposure drift. Dashboard is deferred to V4.3 after V4.2 gates; no Streamlit or mock performance added.

Next: implement a read-only future dataset intake and manifest gate without modifying frozen V4.1 production code. Separately pre-register any V4.2 control/statistical changes before examining new outcomes. Preserve this protocol, checkpoint and observed results. No paper/live activation is authorized.

Primary implementation attribution: reused frozen local V4 calendar validation, causal features, ExecutionConfig and block-bootstrap function. The numerical claims are supported by saved local outputs and executed tests, not external market forecasts.
