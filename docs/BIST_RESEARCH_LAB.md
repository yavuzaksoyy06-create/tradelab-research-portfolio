# BIST daily research lab

I added a separate daily BIST workflow with source registration, strict coverage checks, real-data charts and a fixed cost-aware backtest. It does not extend the frozen V4.1 study or reuse the US 15-minute calendar. The [protocol](BIST_RESEARCH_PROTOCOL.md) was committed at `0f73532` before any real BIST observations were imported.

**Actual evidence status:** no entitled BIST file has been supplied in this development session. Real BIST backtests and chart artifacts have not been produced. The implemented path is tested with explicitly simulated software fixtures; no simulated return is presented as market performance.

## Local UI

Start the development workspace on loopback:

```powershell
python -B -m streamlit run research_workspace/app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
```

Choose **BIST Research**. Upload your entitled daily CSV, select THYAO/GARAN/ASELS and enter the provider, HTTPS source reference and license/permission reference. Confirm your local research rights, then submit. Do not enter credentials or account numbers. This declaration does not independently verify a provider or licensing rights.

The input must contain exactly `date,open,high,low,close,volume,adjusted_close`, with complete XIST sessions for 2020–2024, no missing/duplicate/unsorted dates, finite valid OHLC values and provider-adjusted close. The cap is 2,000,000 bytes. Prices are never backfilled. 2025 holdout and sealed dates are rejected before numeric interpretation. The pinned calendar, including exceptional closures, remains an implementation dependency rather than exchange-certified coverage.

On a successful explicit submission, three private charts show raw 2023–2024 OHLC candles, adjusted-close EMA20/60 and cost-adjusted strategy/buy-and-hold equity. Raw OHLC and adjusted prices are labeled separately. Statistical output includes net return, volatility, drawdown, exposure, turnover, annual returns, three cost settings, zero-yield cash baseline and a paired moving-block interval. Results clear on a subsequent rerun. Missing or rejected input produces no chart or invented result. No automatic network call or broker/order path exists in this lab.

## Immutable private registration

Use an absolute path to your licensed CSV and a **new destination outside every Git repository**. Replace the example source reference with the provider's actual documented reference. These examples are not claims that a source file already exists:

```powershell
python -B tools/bist_research.py register --input C:\PrivateTradeLabData\THYAO_2020_2024.csv --symbol THYAO --provider "Your entitled provider" --source-url https://provider.example/history --license-reference "Local research entitlement reference" --output C:\PrivateTradeLabData\bist_thyao_v001 --confirm-local-research-rights
python -B tools/bist_research.py evaluate --snapshot C:\PrivateTradeLabData\bist_thyao_v001
```

Registration validates before creating the destination. It writes original `bars.csv` bytes and a sanitized `manifest.json` using exclusive creation; existing folders are never overwritten. Source URLs cannot contain authentication, query or fragment parameters. The manifest includes CSV SHA-256, canonical price fingerprint and a registration hash binding source fields, symbol, protocol and canonical data. Read-back validates all three bindings plus declared byte/session bounds. Arbitrary metadata is dropped. These are integrity checks, not signatures: an owner can rewrite metadata and recompute hashes. Independent custody and provider authentication remain separate requirements.

The CLI prints a price-free diagnostic summary; it neither publishes data nor writes raw prices to Git. A failed partial write is not a usable registered snapshot; select a new destination for a retry. Keep private snapshots and chart screenshots out of public commits unless redistribution permission is separately established.

## Research interpretation and next evidence

The fixed EMA20/60 rule uses two-bar signal delay for close-to-close returns and charges turnover plus terminal exit. It has no parameter search. Current selected survivors, revised corporate-action adjustments, zero cash yield and nominal TRY accounting limit conclusions. Block-bootstrap intervals do not establish a tradable edge. The [protocol](BIST_RESEARCH_PROTOCOL.md) defines these assumptions and all cost settings.

The next empirical step is to obtain a documented entitled export, register each symbol separately, inspect full calendar/corporate-action coverage and execute the same frozen specification. Compare fold/year stability and costs without choosing a winner after inspection. Broader point-in-time universe data, an entitled market benchmark, TRY risk-free/inflation series and independently archived vintages require separate evidence. 2025 is still reserved; passing tests or seeing a favorable retrospective return cannot release it or the V4.1 time gate.

See [source policy](../research_workspace/bist_sources.json), [preparation audit](PREPARATION_AUDIT_2026_10_31.md) and [checkpoint evidence](../evidence/bist_preparation_audit_checks.json).
