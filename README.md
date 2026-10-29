# TradeLab
### Quantitative Trading Research · Statistical Validation · Portfolio Analytics

[![Public research tests](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/workflows/public-tests.yml/badge.svg)](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/workflows/public-tests.yml)

**Python · pandas · NumPy · SQL/SQLite · Streamlit · Plotly · Applied Statistics**

I started TradeLab to test whether ideas that look convincing on a price chart actually survive realistic assumptions, transaction costs, and statistical scrutiny.

My starting point was **support and resistance**. I wanted to turn discretionary chart patterns into rules I could explain, reproduce, and test without looking into future candles. The project later grew into a shared-capital portfolio simulator, a research terminal, and a financial data-quality workspace.

**Key result:** the three V4.1 S/R candidates lost money after assumed trading costs in the inspected historical replay. Rather than selecting a favorable chart or hiding a negative result, I kept the experiment and its limitations documented.

> **Scope:** Offline quantitative research, hypothetical execution and descriptive financial analytics. No profitable edge has been established; no broker orders have been sent. The historical research samples have already been examined and are not untouched out-of-sample evidence.

## What I built, and why it matters

I did not set out to build another chart that labels every support touch as a buying opportunity. I wanted to know **whether the signal was available at the time, whether an actual portfolio could have taken it, and whether any apparent advantage survived costs and comparison with a control**. Each unsuccessful experiment informed the next layer of the platform.

| Research question | What I implemented | Evidence or current boundary |
|---|---|---|
| **Can support/resistance rules survive realistic execution?** | Completed-bar signals, next-bar hypothetical fills, intraday session rules, shared cash and position limits; three V4.1 candidate portfolios | A **142-session, 3-symbol** research dataset; the inspected 42-session replay produced **negative net P&L for all three candidates** at an assumed 3 bp per side |
| **How much apparent performance comes from specification choices?** | A **36-cell** V4 diagnostic grid, five matched timing-control seeds, block-bootstrap uncertainty and explicit multiple-testing disclosures | The reported touch-versus-control confidence interval crosses zero; **no significant edge** or multiplicity-adjusted result is claimed |
| **Can I inspect past decisions without rewriting history?** | Read-only **Equity Research** charts for SPY/MSFT/QQQ: 15-minute candles, causal S/R zone histories, confirmed HH/HL/LH/LL pivots and trendlines, EMA 9/21/50/200, RSI(14), RVOL(20), replay and evidence-linked Turkish commentary | Synthetic offline mode works publicly; optional historical Alpaca GET and user CSV require explicit source handling. Indicators are descriptive, **not validated signals** |
| **Can an exploratory scenario study avoid future leakage?** | Stage 7 event labels at **4/16 completed-bar** horizons, expanding chronological diagnostics with purging/embargo, four baselines, calibration and a reserved final **20-session holdout** | Audited holdout/replay leaks were fixed and regression-tested. **No real Stage 7 historical evaluation, calibrated probabilities or predictive edge** has been established |
| **Can external financial data be trusted before it reaches analysis?** | Treasury/ECB normalization, SHA-256 provenance, SQL reconciliation, yield curves, term spreads, FX returns and volatility | A parser audit recovered **218 missing valid Treasury observations**, with the original source snapshot preserved |

The distinction between **implemented**, **tested offline**, and **validated on real market outcomes** is intentional. Passing a software test is not evidence of a profitable trading strategy.

## Repository map

| Where to start | Directory | Purpose |
|---|---|---|
| **Core quantitative research** | [`research_sr_v4_1/`](research_sr_v4_1/) | Shared-cash portfolio, positions, risk constraints, timing controls and statistics |
| Research engine | [`research_sr_v4/`](research_sr_v4/) | Causal S/R features, trading sessions, signal rules, hypothetical fills |
| Explore results | [`research_terminal/`](research_terminal/) | Historical replay and research inspection; private original cache not included |
| **Financial and equity research UI** | [`research_workspace/`](research_workspace/) | Treasury/ECB analytics, SQL/data integrity, read-only equity chart replay and rule-based commentary |
| Earlier experiments | [`research_sr/`](research_sr/), [`research_sr_v2/`](research_sr_v2/), [`research_sr_v3/`](research_sr_v3/) | Historical prototypes, retained for source comparisons |
| Other research foundations | [`research_fx/`](research_fx/), [`research_crypto/`](research_crypto/), [`research_macro/`](research_macro/) | Calendars, availability rules and synthetic event-study contracts |
| Methods and evidence | [`docs/`](docs/), [`evidence/`](evidence/) | Historical reports, test records, reproducibility boundaries |

The original Python package paths remain intact because the frozen research protocol, tests, imports and source hashes depend on them. Earlier versions are **historical**, not separate production-ready products.

---

## 1. Support/resistance research: numerical results

### Study design

| Setting | Recorded specification |
|---|---|
| Universe | **MSFT, SPY, QQQ** |
| Data | 15-minute regular-session SIP bars, split-adjusted; **3,692 bars per symbol** |
| Total sample | 1 Apr–22 Oct 2026, **142 XNYS sessions** |
| Training diagnostic | 70 sessions (1 Apr–13 Jul) |
| Validation diagnostic | 30 sessions (14 Jul–24 Aug) |
| Inspected historical replay | **42 sessions (25 Aug–22 Oct)** |
| Initial capital | **$100,000 per candidate experiment**; shared cash across the three instruments within each experiment |
| Transaction cost assumption | **3 basis points per side**, zero percentage commission |
| Execution policy | Long-only, no overnight positions, up to four 15-minute bars per trade |
| Position/risk policy | Max 10% new-position notional, 0.5% planned risk, 30% opening aggregate exposure, up to three positions |

Spread and slippage costs are **model assumptions**, not measured execution costs. A daily risk lock does not prevent a loss larger than its threshold after a gap.

### V4.1: the complete 42-session research summary

| Candidate | Universe / bars | Replay period | Cost / side | Trades | Net P&L | Net return | Max DD | 95% paired bootstrap interval* |
|---|---|---|---:|---:|---:|---:|---:|---|
| **Support touch** | MSFT, SPY, QQQ · 15m | 25 Aug–22 Oct 2026 · 42 sessions | 3 bp | **53** | **-$93.36** | **-0.0934%** | 0.2335% | **[-$0.2866, +$6.4930]/day** |
| **Rejection** | MSFT, SPY, QQQ · 15m | 25 Aug–22 Oct 2026 · 42 sessions | 3 bp | **9** | **-$131.15** | **-0.1312%** | 0.1312% | Not estimated; sparse sample |
| **Trend filtered** | MSFT, SPY, QQQ · 15m | 25 Aug–22 Oct 2026 · 42 sessions | 3 bp | **4** | **-$24.88** | **-0.0249%** | 0.0520% | Not estimated; sparse sample |

*The bootstrap interval is for the **average daily candidate-minus-matched-control P&L**, not for the total net return. It is descriptive, does not adjust for multiple comparisons, and crosses zero for support touch. The replay is previously inspected historical data—not a new unseen holdout.*

Each candidate uses a **separate** $100,000 shared-cash portfolio across the three instruments; returns cannot be added as if the strategies were funded together. Signal counts were 103 (touch), 20 (rejection), and 6 (trend filtered); active sessions were 28, 7 and 4, respectively.

### Matched timing controls and uncertainty

| Strategy | Candidate trades | Mean control trades | Mean daily candidate − control P&L | 95% descriptive paired bootstrap interval |
|---|---:|---:|---:|---|
| **Support touch** | 53 | 52.8 | **+$2.5740/day** | **[-$0.2866, +$6.4930]/day** |
| Rejection | 9 | 9.6 | -$0.4718/day | Not estimated: insufficient active sessions |
| Trend filtered | 4 | 4.0 | -$0.6855/day | Not estimated: insufficient active sessions |

The original comparison used **1,000 circular five-session block-bootstrap resamples**, retaining paired portfolio-session dependence. Five timing-control seeds were retained; they are simulations over the same market data, not independent observations.

The touch interval **includes zero**. Neither a statistically reliable improvement nor a causal S/R edge is established. The other two candidates have too few active sessions to estimate the specified intervals. A replay Sharpe ratio is not reported because the 42-session sample fails the experiment's minimum data gates.

### Cost sensitivity matters

In the separate **30-session validation** period, the support-touch candidate produced:

| Assumed cost per side | Net P&L |
|---|---:|
| 0 bp | +$30.45 |
| 3 bp | -$167.63 |
| 6 bp | -$364.79 |
| 10 bp | -$649.89 |

Under these assumptions, a small positive result without costs turns negative once trading friction is included. These validation numbers are from a **different time period** and should not be added to the replay results.

**Full tables, accounting checks and controls:** [S/R quantitative evidence](docs/SR_RESEARCH_EVIDENCE.md) · [Original V4.1 historical report](docs/v41-historical-research.md)

---

## 2. Multiple testing: what I can and cannot conclude

V4 validation documented **three entry definitions**, **three zone-width settings** and **four cost assumptions**: a **3 × 3 × 4 = 36-cell diagnostic configuration grid**. V4.1 subsequently evaluated three shared-capital candidate portfolios with five timing-control seeds.

These are not 36 independent discoveries: configurations overlap, candidates reuse data and the five control seeds are not independent market samples. Earlier V1–V3 prototypes also involved exploratory work; the available records do **not** establish an exact, deduplicated lifetime count of every trial.

This introduces **multiple-testing / data-snooping risk**. The chronological train/validation/replay split helps document the experiment, but all three intervals have since been inspected. The recorded paired confidence interval is **not multiplicity-adjusted**.

I have **not** calculated a Deflated Sharpe Ratio, White's Reality Check, Hansen's SPA, or a multiple-comparison-adjusted p-value. Those require a defensible trial inventory, aligned full return series and dependence-aware inference; summary P&L alone is not enough. They are possible directions for a **new, separately registered experiment**, not results being claimed here.

**Methods and counting boundaries:** [S/R research evidence](docs/SR_RESEARCH_EVIDENCE.md) · [Statistical methodology](docs/METHODOLOGY.md)

## 3. Research integrity and frozen protocol

Signals are formed only after the required price bars have completed. The hypothetical simulator then applies next-bar entry rules, capital limits, adverse transaction costs, conservative handling of ambiguous intrabar stop/target ordering and cash/equity reconciliation.

The original local V4.1 report records:
- **Local protocol freeze:** 23 October 2026, 18:41:04 UTC
- **Protocol SHA-256:** `93e311df4885c13823dbf0db705c75dd0c9c6488bf8d8b2d114de237d80c7f6b`
- **First public source snapshot:** [GitHub commit `780aab3`](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/commit/780aab32ab4d96508911fcea6518985219993cf0), published **27 October 2026**

The local freeze timestamp is part of historical project evidence; the GitHub commit proves public availability **from 27 October**, not preregistration before the already-inspected replay. Creating a tag later cannot retroactively establish a 23 October public timestamp.

A [manual GitHub Actions workflow](.github/workflows/anchor-v41-public-snapshot.yml) is provided to create the annotated tag `v4.1-public-snapshot-2026-10-27` on that **first public snapshot commit** without moving the tag afterward. This is a public-source anchor, **not** a retroactively dated preregistration. The tag is not claimed to exist until the workflow has actually succeeded.

The separate prospective protocol specifies **60 sessions from 26 October 2026 to 21 January 2027**, with an earliest completion gate of **21 January 2027, 21:15 UTC**. The clock alone is insufficient: complete validated data and unchanged protocol conditions are required. No prospective performance is reported.

[Protocol and research provenance](docs/SR_RESEARCH_EVIDENCE.md)

---

## 4. Financial data engineering and analytics

I extended TradeLab to work with verified public daily reference data, including **US Treasury par yields** and **ECB FX reference rates**, while keeping them separate from intraday trading data.

### A practical data-quality case

The original Treasury parser silently omitted the official **1.5-month tenor** (`BC_1_5MONTH`) because its field-matching rule only recognized integer maturity names.

| Verified version | Observations |
|---|---:|
| Original Treasury 2025 snapshot | 3,237 |
| Valid observations recovered | **218** |
| New separately verified v2 derivative | **3,455** |

The fix uses explicit tenor definitions and a new version with parent lineage, without rewriting the old source files, checksums or manifests. It illustrates why a matching SHA-256 file hash **does not by itself guarantee complete semantic extraction**.

### Available analysis

- **Treasury:** observed yield curves, 10Y–2Y and 10Y–3M spreads, basis-point changes and inversion diagnostics.
- **ECB FX:** EUR/USD, EUR/GBP and other verified EUR-base series; simple/log returns, rolling non-annualized descriptive volatility and CSV exports.
- **SQL and validation:** SQLite joins/aggregations, row reconciliation, publication-reference comparisons, source/version metadata and rejected-data states.

The supplied 2025 Treasury and 2026 ECB observation periods do not overlap. The application does not manufacture a cross-market correlation or treat today's downloaded data as historical point-in-time vintages.

[Data-quality case study](docs/TREASURY_REMEDIATION.md) · [Financial analytics methodology](docs/FINANCIAL_ANALYTICS.md)

## Screenshots

Actual captured local UI screens, not generated mockups. Raw provider snapshots are intentionally excluded from the repository.

**Treasury yield-curve analysis**

![Verified Treasury yield-curve view](docs/images/stage5-treasury.png)

**ECB reference-rate analysis**

![Verified ECB FX analysis](docs/images/stage5-ecb.png)

**Synthetic macro event-study teaching lab**

![Synthetic event-study example](docs/images/synthetic-event-study.png)

---

## Running the public research workspace

Documented development environment: **Windows, Python 3.12**.

```powershell
git clone https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio.git
cd tradelab-research-portfolio
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m streamlit run research_workspace/app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false --theme.base dark
```

Open `http://127.0.0.1:8502/`. The workspace can display educational/synthetic modules without private provider data. Financial Analytics requires locally verified snapshots for real charts; it shows unavailable states rather than inventing values. The historical Research Terminal 0.2.0 requires excluded private research evidence and is not a ready-to-run historical replay from a fresh public clone.

**Optional external collection** (explicit command, not performed automatically):

```powershell
.\.venv\Scripts\python.exe -B -m research_workspace.real_sources collect --source ecb_fx
.\.venv\Scripts\python.exe -B -m research_workspace.real_sources collect --source treasury_2025
.\.venv\Scripts\python.exe -B -m research_workspace.real_sources review
```

These collect official *daily reference data*, not intraday prices. The legacy Treasury collector and the separately derived Treasury v2 version are described in [Financial Analytics](docs/FINANCIAL_ANALYTICS.md). Do not treat the v2 derivative as a newly published historical vintage.

### Tests and CI

```powershell
.\.venv\Scripts\python.exe -B tools/run_public_tests.py
```

- **Current development-branch local evidence (29 October 2026):** 477 tests discovered, **476 passed and 1 existing Windows symlink-permission skip**; zero failures. [Machine-readable record](evidence/stage7_audit_checks.json).
- **Exact development-head CI:** [GitHub Actions run #47](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/runs/40858054701), Windows / Python 3.12 at commit [`82f4c22`](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/commit/82f4c22dc7234da1bfd7d9e279d77d416d2c96f6): **477 passed, 0 skipped, 0 failures**. Verified from the completed workflow's job logs. The default-branch badge at the top does **not** attest to this draft PR.
- **Platform limits:** The public test runner excludes private cached-price and frozen original research reproduction. Windows is the documented platform; Linux/macOS compatibility is **not certified**. The full frozen historical replay cannot be reproduced without the excluded original evidence.

[Validation scope and results](docs/VALIDATION.md) · [Recorded test evidence](evidence/public_test_results.json)

## Stage 7: evidence-based scenario research (draft development branch)

After building replay-safe charts, I wanted to investigate a harder question: **can observable market structure support a calibrated statement about what tends to happen next, rather than merely an explanation of what just happened?** I separated that question from strategy P&L and registered fixed hypotheses, observation horizons and validation rules before any real Stage 7 evaluation.

Stage 7 adds causal historical event records, fixed **4/16-completed-bar** outcomes, chronological expanding-window validation with **16-bar embargo and purged labels**, a reserved final **20-session historical holdout**, smoothed conditional frequencies, four transparent baselines, calibration and paired session-bootstrap diagnostics. The existing equity chart now includes six Turkish research panels with replay-safe outcome visibility and price-free summary exports.

**No real Stage 7 predictive edge has been validated.** Scenario probabilities remain suppressed. Synthetic tests exercise the pipeline; they are not evidence about SPY, MSFT or QQQ future performance. Explicit private historical collection uses only Alpaca Market Data GET requests, retains feed/adjustment provenance and rejects incomplete scheduled sessions. Stage 7 never opens the frozen prospective period or creates orders.

Continue on `feature/equity-lab-stage6-slice1`, [draft PR #1](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/pull/1); this slice is not merged into main. The default-branch badge is not proof of this PR's exact head. See the checkpoint for inspected Actions runs.

### What the 29 October leakage audit found

The first implementation withheld the final 20 sessions from model validation, but **replay could still display their outcome labels**. Worse, replay-prefix truncation **moved the holdout boundary** as the cursor advanced. The audit also reproduced invalid negative-index access and a private-manifest writer that accepted unvalidated dates and arbitrary metadata fields.

I addressed these with a **fixed, full-snapshot partition**, shared chart/label/evaluation visibility guards, registered input fingerprints, strict index/date checks and metadata allowlisting before private writes. **Nine additional adversarial regression tests** cover these pathways; [CI #47](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/runs/40858054701) passed all 477 public offline tests. This is **software integrity evidence**, not an independent market-data study or a security certification. Previously viewed data cannot become untouched again.

**Read more:** [Equity Research Lab](docs/EQUITY_RESEARCH_LAB.md) · [Chart commentary methods](docs/EQUITY_STRUCTURE_COMMENTARY.md) · [Stage 7 protocol](docs/STAGE7_RESEARCH_PROTOCOL.md) · [Leakage audit](docs/STAGE7_AUDIT.md) · [Validation](docs/STAGE7_VALIDATION_REPORT.md) · [Checkpoint](docs/STAGE7_CHECKPOINT.md) · [Limitations and private collection](docs/STAGE7_LIMITATIONS.md)

## Development history and limitations

TradeLab progressed from S/R prototypes (V1/V2), through explicit execution accounting (V3/V4), to synchronized shared-capital research (V4.1), a historical inspection terminal, verified public reference-data collection, SQL quality reports, and the Financial Analytics Lab.

The initial public commit on **27 October 2026** was a **curated snapshot of work developed locally across earlier stages**. It was not an attempt to recreate earlier chronological Git commits. Subsequent commits document the portfolio publication and follow-on data-analysis additions. See [development stages](docs/DEVELOPMENT_STAGES.md).

I use this project to practice making research decisions auditable: when a test cannot support a conclusion, the correct result is to document that uncertainty rather than turn it into a trading claim.

### More documentation

- [S/R numerical evidence, multiplicity and protocol](docs/SR_RESEARCH_EVIDENCE.md)
- [Original V4.1 historical report](docs/v41-historical-research.md)
- [Statistical methodology](docs/METHODOLOGY.md)
- [Data architecture](docs/ARCHITECTURE.md)
- [Financial analytics equations](docs/FINANCIAL_ANALYTICS.md)
- [SQL catalog and data quality](docs/SQL_CATALOG.md)
- [Validation and reproducibility](docs/VALIDATION.md)
- [Data provenance and publication policy](docs/DATA_AND_SECURITY.md)

Public references: [European Central Bank](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) and [US Treasury](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed). No raw provider files, credentials, or private historical market caches are distributed in this repository. Public visibility does not, by itself, grant an open-source license.

