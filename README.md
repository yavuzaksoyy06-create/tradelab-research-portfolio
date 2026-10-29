# TradeLab
### Quantitative research, financial data engineering & statistical validation

[![Public research tests](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/workflows/public-tests.yml/badge.svg?branch=feature%2Fequity-lab-stage6-slice1)](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/workflows/public-tests.yml)

**Python 3.12 · pandas · NumPy · SQL/SQLite · Streamlit · Plotly · Statistical inference**

I built TradeLab to answer a practical question: **can an intuitive market observation survive explicit rules, transaction costs and reproducible testing?** I developed a shared-capital simulator, a financial data-quality workspace and a causal replay interface. I learned to make data lineage, timing and uncertainty explicit before interpreting a result.

**Current scope:** research software, not a trading service. No profitable edge has been established. Real-market Stage 7 calibration remains unvalidated; scenario probabilities stay disabled.

> **Latest development:** [draft PR #1](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/pull/1), branch `feature/equity-lab-stage6-slice1`. [Audited checkpoint: 477 tests passed in Windows CI](https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio/actions/runs/40858054701). This work is not merged into `main`.

## What I built

| Component | Technical implementation | What I learned |
|---|---|---|
| **Portfolio simulation** | Synchronized multi-asset timeline, shared cash, position limits, next-bar fills, transaction costs and cash/equity reconciliation | A strategy result depends on execution and capital allocation, not just its entry rule |
| **Trusted data pipeline** | Immutable version folders, SHA-256 manifests, parent lineage, strict XNYS session validation and explicit IEX/SIP provenance | Byte integrity and semantic completeness are different problems |
| **SQL analytics catalog** | Read-only SQLite queries, joins/aggregations, reconciliation, expected-series checks and source-specific publication calendars | Missing observations need a calendar and a series definition before they can be measured |
| **Financial analytics** | Treasury term spreads and basis-point changes; ECB FX returns and descriptive volatility | Units, frequency and overlapping coverage determine which comparisons are defensible |
| **Causal equity replay** | EMA 9/21/50/200, Wilder RSI, RVOL, confirmed pivots, historical S/R states and non-backdated trendlines | A historical feature must be available at its confirmation time, not merely visible in hindsight |
| **Scenario validation** | Fixed 4/16-bar outcomes, expanding chronological folds, purging, 16-bar embargo, a reserved final 20-session holdout, smoothed conditional frequencies and four baselines | Correct descriptions do not automatically have predictive value |

## Evidence: costs changed the conclusion

![Archived V4.1 replay losses and separate validation cost sensitivity](docs/images/research-results.png)

The study spans **142 sessions across MSFT, SPY and QQQ**. All three candidates lost money in the already-inspected **42-session replay** at 3 bp per side. Each uses a separate $100,000 account; results are not additive.

The touch candidate's daily difference versus timing controls had a descriptive interval of **−$0.2866 to +$6.4930**: it includes zero and is not multiplicity-adjusted. I retained these findings rather than claim an established edge.

The documented V4 sensitivity grid contains **36 configurations**; V4.1 retains **five timing-control seeds**. These reuse market observations and are not independent discoveries.

[Full results, assumptions and multiple-testing limits →](docs/SR_RESEARCH_EVIDENCE.md)

## From chart patterns to testable observations

![Causal replay generated from a synthetic educational fixture, showing historical zones, confirmed pivots, EMA, volume and RSI](docs/images/causal-replay.png)

**Synthetic data, not market prices or a screenshot.** This figure uses the project's causal-feature code: zones retain their historical states and pivots appear at confirmation. Replay shows outcomes only after their horizons complete.

Stage 7 uses **Brier score, log loss, balanced accuracy, five-bin calibration and session-block bootstrap intervals**. Its conditional-frequency model is compared with unconditional frequency, majority class, persistence and an EMA rule. Offline tests verify the mechanics; real predictive value remains unvalidated.

[Equity Research Lab](docs/EQUITY_RESEARCH_LAB.md) · [Commentary methods](docs/EQUITY_STRUCTURE_COMMENTARY.md) · [Registered research protocol →](docs/STAGE7_RESEARCH_PROTOCOL.md) · [Figure sources and reproduction →](docs/images/README.md)

## Two engineering lessons that changed the implementation

**A valid hash did not guarantee a complete dataset.** The Treasury parser omitted the `BC_1_5MONTH` tenor. Explicit series definitions recovered **218 observations**, taking the separately verified derivative from **3,237 to 3,455 rows**, while preserving the original snapshot and lineage. [Remediation case study](docs/TREASURY_REMEDIATION.md)

**A green test suite did not guarantee an untouched holdout.** My follow-up Stage 7 audit found that replay could expose reserved outcomes and move the test boundary as its cursor advanced. I unified the chart, label and evaluation boundary, bound private snapshots to immutable registrations and added nine adversarial tests. Previously viewed data cannot become unseen again. [Audit findings and fixes](docs/STAGE7_AUDIT.md)

## Development path

S/R prototypes → execution and shared-capital accounting → decision/replay terminal → trusted data and SQL analytics → causal equity inspection → scenario validation and leakage audit. [Detailed stages and checkpoints](docs/DEVELOPMENT_STAGES.md)

## Run the development workspace

Windows / Python 3.12. The synthetic Equity Research view runs without credentials or private market data.

```powershell
git clone --branch feature/equity-lab-stage6-slice1 https://github.com/yavuzaksoyy06-create/tradelab-research-portfolio.git
cd tradelab-research-portfolio
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B tools/run_public_tests.py
.\.venv\Scripts\python.exe -B -m streamlit run research_workspace/app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
```

Open **http://127.0.0.1:8502/** and select **Equity Research**. Real-data views require eligible local snapshots; unavailable data stays unavailable. Explicit private collection is documented separately and never runs automatically.

## Code & verification

Explore [`research_workspace/`](research_workspace/) for SQL and Stage 7, [`research_sr_v4_1/`](research_sr_v4_1/) for portfolio accounting, and [`research_terminal/`](research_terminal/) for historical inspection.

**477 tests passed in the linked Windows CI checkpoint.** Coverage includes causal prefix invariance, calendar coverage, label timing, purging, holdout isolation, manifest integrity, GET-only transport and UI rendering. Locally, one symlink-privilege case is skipped; [the audit record](evidence/stage7_audit_checks.json) preserves the exact scope. Software tests are not a security certification. Public tests do not reproduce the excluded private-price study.

**Research boundaries:** frozen V4/V4.1 remains unchanged; the prospective gate is **21 January 2027, 21:15 UTC**. Stage 7 rejects dates on/after 26 October 2026. No broker orders, private price caches or credentials are included. Historical retrieval is not independent point-in-time authentication. Public visibility does not itself grant an open-source license.

[Checkpoint](docs/STAGE7_CHECKPOINT.md) · [Validation](docs/STAGE7_VALIDATION_REPORT.md) · [Limitations](docs/STAGE7_LIMITATIONS.md) · [Data and security](docs/DATA_AND_SECURITY.md)
