# Equity Research Lab — first public slice

The new **Equity Research** page is an isolated, read-only extension of the public Research Workspace. It does not modify frozen V4/V4.1 research files, historical strategies, the prospective gate, or the Research Terminal.

## What currently works

- **SPY / MSFT / QQQ** selection, initially with 15-minute US equity candles.
- Deterministic **SYNTHETIC EDUCATIONAL DATA** usable without private caches or provider accounts. The prices are invented solely to exercise the interface; they are never presented as market observations.
- Local user-provided CSV inspection with a prominent **USER-SUPPLIED / PROVIDER NOT VERIFIED** status.
- Strict session coverage through the existing XNYS validator, including holidays, early closing times and UTC timestamps.
- OHLCV checks for missing values, duplicate and unordered bars, invalid candles and unfinished bars. Missing scheduled bars are rejected, never filled.
- Interactive candlestick and volume plots, replay slider, confirmed pivots, active support/resistance zones, ATR, and the existing research engine's signals.
- Every replay cursor recalculates V4 causal features **only from completed bars visible at that cursor**.

## CSV format

The input must contain **exactly** these columns in chronological order:

~~~csv
timestamp,open,high,low,close,volume
~~~

- UTC Z or an explicit timezone offset is required for every timestamp.
- Bars must be **start-labeled 15-minute OHLCV** for **complete consecutive XNYS regular sessions**; no extended-hours bars, gaps or partial first/last sessions.
- Maximum **5 MB and 5,000 bars**; only SPY, MSFT and QQQ are selectable in this stage.
- Uploaded bytes are read in memory and are **not saved**, sent to an API or distributed through GitHub. The SHA-256 fingerprint is displayed for traceability, not as proof of source authenticity.
- Valid structure does **not** verify origin, feed entitlements, exchange reporting accuracy, corporate actions, bid/ask spreads, a historical information vintage or redistribution permission.

## Limitations and next steps

This is **not a real-time stock-feed integration**, trade recommendation, execution or profitability backtest. A fresh public clone cannot reproduce frozen historical equity findings because the original private research cache and output files are intentionally excluded. CSVs of unknown source are not promoted to cryptographically verified market data. OHLCV alone cannot determine institutional positioning or prove order-book absorption.

Next steps are a separately reviewed verified equity provider adapter with feed entitlement/rights controls, immutable source manifests, and a proper display of V4.1's existing historical research results. An authorized BIST source will need a different session calendar and source contract. Neither prospective evaluation nor broker orders are enabled by this module.

Run the workspace using the [README](../README.md) and select **Equity Research**. The public test selection includes the new CSV and replay tests.
