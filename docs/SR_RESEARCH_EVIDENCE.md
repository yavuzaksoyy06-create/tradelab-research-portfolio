# S/R research evidence, multiplicity, and protocol provenance

This page makes the numerical results in the archived V4.1 research report easier to inspect. It is a historical **offline simulation** summary, not a fresh independent audit and not an evaluation of the frozen future period.

**Primary source:** [V4.1 historical research report](v41-historical-research.md). For original V4 candidate definitions and diagnostic sensitivity grid, see [V4 methodology](v4-methodology.md).

## Market sample and simulation assumptions

| Item | Recorded setting |
|---|---|
| Instruments | MSFT, SPY, QQQ (three correlated US equity instruments) |
| Data | Existing SIP, split-adjusted 15-minute regular-session bars |
| Data coverage | 1 April–22 October 2026, 142 XNYS sessions; 3,692 bars per symbol |
| Training diagnostic | 1 April–13 July, 70 sessions |
| Validation diagnostic | 14 July–24 August, 30 sessions |
| Previously inspected replay | 25 August–22 October, 42 sessions |
| Capital | USD 100,000 **per candidate experiment**, one shared-cash account across three instruments |
| Position policy | Long-only, no margin, end-of-day flat, no more than 3 positions |
| Risk policy | Max 10% new-position notional; planned risk 0.5%; max aggregate opening exposure 30%; observed daily drawdown lock at 2% |
| Trading cost assumption | 3 basis points per side (combined fixed spread/slippage), zero percentage fees |
| Holding horizon | Maximum four 15-minute bars; intrabar collisions treated conservatively |
| Nature of fills | Hypothetical, not broker executions |

The 2% observed drawdown lock is **not** a guaranteed maximum loss, particularly across price gaps.

## V4.1 previously inspected 42-session replay

Each row is a separate candidate research experiment; returns **must not** be added as one combined funded portfolio.

| Candidate | Signals | Executed trades | Active sessions | Net P&L (USD) | Return on USD 100k | Max observed drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Support touch | 103 | 53 | 28 | -93.36 | -0.0934% | 0.2335% |
| Rejection | 20 | 9 | 7 | -131.15 | -0.1312% | 0.1312% |
| Trend filtered | 6 | 4 | 4 | -24.88 | -0.0249% | 0.0520% |

**None of the three candidates showed a positive net portfolio result in this historical replay under the configured costs.** There is no evidence here of a robust trading advantage.

### Matched timing comparisons

Five pre-specified control seeds were retained (11, 23, 37, 51, 71). Each is an alternate timing simulation over the **same historical market observations**; they are not five independent samples.

| Candidate | Candidate trades | Average control trades | Daily candidate-minus-control difference (USD) | 95% descriptive paired bootstrap interval (USD/day) |
|---|---:|---:|---:|---|
| Support touch | 53 | 52.8 | +2.5740 | **[-0.2866, +6.4930]** |
| Rejection | 9 | 9.6 | -0.4718 | Not estimated: insufficient active sessions |
| Trend filtered | 4 | 4.0 | -0.6855 | Not estimated: insufficient active sessions |

Intervals used 1,000 circular five-session bootstrap block resamples with minimum sample/active-session requirements. The touch interval crosses zero. The other two candidates fail the active-session interval gate. These are **descriptive, not multiple-testing-adjusted confidence intervals**. Control and candidate exposure can differ; the comparison is conditional on timing and does not establish the causal value of S/R detection.

All 42-session replay Sharpe estimates are withheld by the pre-existing minimum thresholds (60 sessions, 30 trades, 30 active trade sessions). A missing Sharpe is not zero performance or a passing result.

### Validation cost sensitivity: touch candidate

Different period: **30-session validation diagnostic**, not the 42-session replay. These values must not be mixed with replay P&L.

| Assumed cost per side | Net P&L (USD) |
|---|---:|
| 0 bp | +30.45 |
| 3 bp | -167.63 |
| 6 bp | -364.79 |
| 10 bp | -649.89 |

Under the recorded execution assumptions the touch result changes sign when costs rise from 0 to 3 bp per side. These are *assumed* costs, not observed broker fills.

## How many hypotheses and settings were tested?

The documented V4 validation design contains **three long-only entry definitions** (touch, rejection, trend filtered), **three zone-width settings**, and **four transaction-cost settings**. This constitutes **3 × 3 × 4 = 36 strategy/width/cost diagnostic cells** when considered as a full Cartesian grid. All reported combinations were retained; the source describes validation sensitivity, not selection of a winning replay parameter.

V4.1 then tested three portfolio candidates against timing controls with five seeds each. Those seeds and V4.1 results are **not** added to the 36 cells as independent strategy discoveries. Earlier V1–V3 exploratory iterations also exist, but the available records do **not** provide a trustworthy, deduplicated all-time count of every variant tried. The 36-cell documented grid is **not** a claim that only 36 hypotheses were ever considered.

## Multiple testing and data snooping

Repeatedly testing variations on the same SPY/MSFT/QQQ history can select a seemingly favorable result by chance. The original diagnostic, validation, and replay samples have now been inspected. No new untouched out-of-sample performance can be claimed from them.

**Not calculated or claimed:** Deflated Sharpe Ratio (DSR), White's Reality Check, Hansen's SPA, or family-wise/FDR-adjusted statistical significance. In particular, the replay Sharpe is unavailable under the stated thresholds, and summary tables are not sufficient to manufacture a valid DSR or Reality Check p-value.

Future multiplicity analysis would require a defensible inventory of all candidate trials, full aligned strategy and benchmark return series, the dependence structure between trials, an appropriate block bootstrap, explicit selection rules, and genuinely subsequent data for confirmation. The historical reports do **not** establish alpha.

## What was frozen, and what is publicly timestamped?

The original local research report records a freeze at **2026-10-23 18:41:04.329598 UTC**, protocol SHA-256:

`93e311df4885c13823dbf0db705c75dd0c9c6488bf8d8b2d114de237d80c7f6b`

That fingerprint covers a manifest of 12 source files from the original local V4/V4.1 research. It is a **historical self-recorded hash**, not a GitHub-signed, independently timestamped preregistration.

The first **public GitHub commit** containing this curated research snapshot is [780aab3](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/commit/780aab32ab4d96508911fcea6518985219993cf0), created **27 October 2026**, after the historical replay. That commit provides a publicly checkable source snapshot **as of its actual commit date only**. A tag added now would also be a later public anchor. Neither should be misrepresented as proof that the hypotheses were registered before the 42-session replay.

The prospective evaluation window is recorded as **26 October 2026–21 January 2027**, 60 sessions, with the earliest complete-after time **21 January 2027 21:15 UTC**. Reaching the clock threshold does not bypass source, coverage, or protocol-validation requirements. The public workspace does not contain or run a prospective evaluator.

For any new experiment: publish the immutable protocol, code/config hashes, hypothesis family, decision rule, data-access rules, and candidate count **before** collecting or opening subsequent outcomes, then retain the exact public Git reference.

## Limits

- Observed historical price bars, not an order-book-level execution study.
- Three correlated instruments and one examined historical period.
- Spread/slippage are assumptions, not empirical measured transaction costs.
- Corporate action history is split-adjusted and does not provide full dividend/point-in-time total returns.
- Controls do not guarantee identical realized exposure or holding duration.
- No multiplicity-adjusted statistical significance or profitable alpha is claimed.
- Private provider caches and original research output artifacts are intentionally not redistributed; their historical results cannot all be freshly recomputed from this public clone.

Read [the original numerical report](v41-historical-research.md) and [validation boundaries](VALIDATION.md) before interpreting this summary.
