# TradeLab
### Quantitative Research & Financial Data Analytics

**Python · pandas · NumPy · SQL/SQLite · Streamlit · Plotly · Applied Statistics**

I started TradeLab to understand a question that kept coming up while I was learning about financial markets: **how do you know whether a trading idea is actually useful, rather than just convincing on a chart?**

With a background in Economics and an interest in trading and quantitative research, I wanted to build something practical. What began as a support-and-resistance experiment gradually became a research workspace for testing ideas, studying financial data, and checking whether the results can be trusted.

The focus is not on finding a perfect strategy. It is on working with data carefully, making assumptions explicit, and being able to explain *why* a result should—or should not—be taken seriously.

> **Current scope:** Research and education. The project has not demonstrated a robust profitable trading edge. It does not place live, paper, or replay orders.

---

## What I've built

### 1. Financial Analytics Lab

A read-only Streamlit workspace for exploring verified public financial reference data.

**US Treasury**
- Compare observed yield curves across selected dates and available maturities.
- Calculate the **10Y–2Y** and **10Y–3M** yield spreads in basis points.
- Examine observed yield-curve inversions and changes between observations.
- Review data coverage, missing maturities, and source/version information.

**ECB foreign exchange**
- Explore EUR/USD, EUR/GBP, EUR/JPY, and other available ECB reference series.
- Calculate simple percentage changes, log returns, and cumulative changes.
- Study rolling descriptive volatility using clearly specified observation windows.
- Export analytical tables with source and dataset-version metadata.

These are **daily reference observations**, not executable trading prices. Treasury yield changes are not bond returns, and ECB rate changes are not broker trading results.

### 2. Strategy research and hypothetical execution

The original part of TradeLab investigates support/resistance behavior using causal, rule-based signals.

- Pivot and support/resistance zones are only usable **after** the required bars have closed.
- Entry and exit assumptions, transaction costs, gaps, and uncertain intrabar order are handled explicitly.
- Experiments use chronological diagnostics, comparison groups, and uncertainty checks.
- Portfolio simulations share the same cash and exposure limits instead of treating each symbol as an independently funded account.

An important finding: the tested V4.1 candidates **lost money after the assumed costs** in the inspected historical replay. I kept that result rather than presenting a misleading success story. It is part of the research, not something to hide.

### 3. Data quality, SQL and reproducibility

I've also worked on the less visible part of financial analysis: knowing whether the inputs are reliable.

- Validating timestamps, market calendars, missing observations, and duplicate records.
- Keeping source files and normalized datasets in separately verified versions.
- Using SHA-256 manifests and data-lineage records to detect unexpected changes.
- Building a small **read-only SQLite catalog** with JOIN/GROUP BY coverage and reconciliation reports.
- Making missing or rejected data visible instead of silently filling gaps.

The workspace includes separate foundations for US equities, crypto calendars, Forex sessions, and macroeconomic event studies. Some of these are research or synthetic teaching modules—not live market feeds.

---

## A real data-quality problem I found

One of the most useful parts of this project was discovering an issue in the US Treasury data pipeline.

The original dataset passed its file-integrity checks, but a normalization rule was silently skipping the **1.5-month Treasury maturity** (`BC_1_5MONTH`). The old pattern recognized integer maturity names but not that field.

I reproduced the issue, reviewed the expected Treasury series, and added a separately versioned normalizer with an explicit tenor mapping.

| | Observations |
|---|---:|
| Original verified version | 3,237 |
| Valid 1.5-month observations recovered | **218** |
| New independently verified derivative | **3,455** |

I kept the original snapshot, manifest, and collector unchanged. The corrected data lives in a new version with its own verification and a link to the parent source.

**The main lesson:** a file can be unchanged and correctly hashed while the data extracted from it is still incomplete.

[Read the case study](docs/TREASURY_REMEDIATION.md) · [Financial analytics methodology](docs/FINANCIAL_ANALYTICS.md)

---

## Screenshots

These screenshots were captured from the local application using verified existing reference snapshots. The underlying raw datasets are not distributed in this repository.

**US Treasury — observed yield curves**

![US Treasury yield curves in TradeLab](docs/images/stage5-treasury.png)

**ECB — daily FX reference data**

![ECB FX analytics in TradeLab](docs/images/stage5-ecb.png)

**Macro event-study learning module — synthetic example**

![Synthetic macro event-study module](docs/images/synthetic-event-study.png)

---

## Tech stack

| Area | Tools and methods |
|---|---|
| Programming and analysis | Python, pandas, NumPy |
| Statistics | Chronological testing, paired comparisons, block bootstrap, descriptive volatility |
| Financial research | Support/resistance, portfolio accounting, yield curves, FX returns |
| Data | SQLite, SQL joins/aggregations, validation rules, versioned manifests |
| Interface | Streamlit, Plotly |
| Quality and reproducibility | Unit/integration tests, SHA-256, source and availability tracking |

This is a local research application, not a production data warehouse or deployed trading platform.

## Run the Research Workspace

The documented development environment is **Windows with Python 3.12**.

```powershell
git clone https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio.git
cd tradelab-research-portfolio

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m streamlit run research_workspace/app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false --theme.base dark
```

Open **http://127.0.0.1:8502/**.

The teaching and calendar modules can run without private market data. The Financial Analytics screens need locally available **verified** public reference snapshots to display real observations. A fresh clone will show unavailable-data messages rather than fabricated charts.

The original Research Terminal 0.2.0 also depends on private historical research evidence that is intentionally not included in the public repository.

### Optional: collect public daily reference data

These commands **make external requests** to the documented official sources. They are optional and are not run automatically.

```powershell
.\.venv\Scripts\python.exe -B -m research_workspace.real_sources collect --source ecb_fx
.\.venv\Scripts\python.exe -B -m research_workspace.real_sources collect --source treasury_2025
.\.venv\Scripts\python.exe -B -m research_workspace.real_sources review
```

The Treasury collector above is the original 2025 collector. The revised Treasury v2 dataset is produced separately from an already verified original snapshot, without rewriting it. See the [methodology](docs/FINANCIAL_ANALYTICS.md) for the offline derivation procedure.

### Run the published test selection

```powershell
.\.venv\Scripts\python.exe -B tools/run_public_tests.py
```

**Last published full test result (28 October 2026): 379 tests, 378 passed and 1 Windows symlink-permission skip.**

This is the recorded result from the documented Windows environment, not a guarantee that every fresh installation or platform will produce identical results. [Validation details](docs/VALIDATION.md).

---

## How the project evolved

1. **Support/resistance prototypes (V1–V2):** Defining price zones and eliminating future-looking pivot signals.
2. **Execution research (V3–V4):** Turning chart ideas into testable rules with costs, calendars, and data checks.
3. **Portfolio research (V4.1):** Shared-cash accounting, exposure limits, and statistical comparisons.
4. **Research Terminal and Workspace:** Building an interface to inspect the data, assumptions, and research evidence.
5. **Real reference data and SQL:** Working with official daily Treasury/ECB sources and verifying their coverage.
6. **Financial Analytics Lab (Stage 5):** Recovering omitted Treasury observations and adding yield-curve and FX analytics.

The older historical samples have already been examined. They cannot be treated as fresh out-of-sample evidence. The separate V4.1 prospective protocol stays frozen, with its time gate no earlier than **21 January 2027, 21:15 UTC**.

[Full development history](docs/DEVELOPMENT_STAGES.md)

## What I'm taking away from it

TradeLab has taught me as much about **questioning a result** as calculating one. A convincing backtest can still be misleading if timestamps, execution costs, missing data, or portfolio constraints are handled poorly. The same principle applies to financial and business analytics: a useful conclusion needs reliable inputs and assumptions that someone else can examine.

I'm continuing to work on stronger data-quality checks and research validation. My goal is to keep building analytical tools that are useful, understandable, and honest about their limitations.

## Documentation

- [Architecture and data contracts](docs/ARCHITECTURE.md)
- [Statistical methodology and limitations](docs/METHODOLOGY.md)
- [Financial Analytics methodology](docs/FINANCIAL_ANALYTICS.md)
- [Treasury data-quality case study](docs/TREASURY_REMEDIATION.md)
- [SQL catalog and data-quality reports](docs/SQL_CATALOG.md)
- [Validation evidence](docs/VALIDATION.md)
- [Data provenance and publication boundaries](docs/DATA_AND_SECURITY.md)
- [Stage 5 delivery report (Turkish)](docs/STAGE5_DELIVERY_TR.md)

## A note on development

I developed TradeLab iteratively with AI-assisted coding tools, including Codex. The repository documents the research questions, decisions, implementation, tests, and limitations of that process; it is not a claim that every line was written without assistance.

Public sources used for the reference-data modules include the [European Central Bank](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) and the [US Treasury](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed). Raw provider datasets, private research caches, and credentials are not part of this repository. No open-source license has been granted for reuse of the repository code.
