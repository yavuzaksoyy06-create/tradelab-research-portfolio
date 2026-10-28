# Equity Research Lab — first public slice

The new **Equity Research** page is an isolated, read-only extension of the public Research Workspace. It does not modify frozen V4/V4.1 research files, historical strategies, the prospective gate, or the Research Terminal.

## What currently works

- **SPY / MSFT / QQQ** selection, initially with 15-minute US equity candles.
- Deterministic **SYNTHETIC EDUCATIONAL DATA** usable without private caches or provider accounts. The prices are invented solely to exercise the interface; they are never presented as market observations.
- Local user-provided CSV inspection with a prominent **USER-SUPPLIED / PROVIDER NOT VERIFIED** status.
- Optional, **user-initiated** historical Alpaca Market Data GET reader for SPY/MSFT/QQQ, 15-minute US equity OHLCV, IEX or entitled SIP feed, with no trading SDK, no orders and no disk cache. Data is only requested when the user clicks Load.
- Strict session coverage through the existing XNYS validator, including holidays, early closing times and UTC timestamps.
- OHLCV checks for missing values, duplicate and unordered bars, invalid candles and unfinished bars. Missing scheduled bars are rejected, never filled.
- Interactive candlestick and volume plots, replay slider, confirmed pivots, active support/resistance zones, ATR, and the existing research engine's signals.
- Trading-session-compressed x-axis: bars and volume remain in the same chronological order with no blank overnight/weekend/holiday slots. New York local timestamps are visible; this is display-only and never fills missing scheduled candles.
- Every replay cursor recalculates V4 causal features **only from completed bars visible at that cursor**.
- Optional **EMA 9/21/50/200** overlays and a Wilder **RSI(14)** panel are descriptive only. All are calculated from the replay prefix, with explicit lookback warm-up (no artificial earlier values). EMA periods refer to **15-minute bars**, not daily candles; RSI first appears after 14 completed price changes. They do not modify the V4/V4.1 S/R engine, its protocol or its prospective gate.
- Downloadable JSON **replay provenance manifest** includes the visible bar interval, SHA-256 content fingerprint, source status, and explicit non-verification safeguards. It never includes price rows and is not an authentication certificate.

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

## Optional historical Alpaca reader

The **Alpaca historical (read-only)** source is isolated from the frozen V4.1 experiment and from broker execution. By default it makes **no network calls**. To use it locally, provide credentials in the app process environment via `ALPACA_API_KEY` / `ALPACA_SECRET_KEY`, or `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`. Never commit keys or enter them in a public Streamlit deployment. A local `.env` is not automatically loaded by this reader.

Choose an explicit **IEX** feed (one exchange, potentially sparser bars) or **SIP** (consolidated feed; your Alpaca account may need the relevant entitlement), a bounded historical date interval and click **Load historical candles (read-only GET)**. No automatic retries, background polling, order requests or persistence is performed. At most 10 complete XNYS sessions are accepted. Off-session API bars are excluded with a disclosed count; missing, duplicated, out-of-order, invalid or future regular-session candles are rejected rather than filled. Provider pagination is bounded and checked.

An HTTPS API response is evidence of its retrieval route, **not** independent verification of the market data, licensing, exchange accuracy, corporate-action adjustments, availability at historical points in time or suitability for live trading. Split-adjusted 15-minute prices are descriptive only. Returned rows stay in Streamlit session memory (never published in the repository). The downloadable replay manifest contains hashes and source labels, not price rows.

Provider reference: https://docs.alpaca.markets/us/reference/stockbars and https://docs.alpaca.markets/us/docs/about-market-data-api.

## Limitations and next steps

This is **not a real-time stock-feed integration**, trade recommendation, execution or profitability backtest. A fresh public clone cannot reproduce frozen historical equity findings because the original private research cache and output files are intentionally excluded. CSVs of unknown source are not promoted to cryptographically verified market data. OHLCV alone cannot determine institutional positioning or prove order-book absorption.

Next steps include independent entitlement/rights review and an immutable source-vintage audit workflow (the optional API response alone is not that), plus a proper display of V4.1's existing historical research results. An authorized BIST source will need a different session calendar and source contract. Neither prospective evaluation nor broker orders are enabled by this module.

Run the workspace using the [README](../README.md) and select **Equity Research**. The public test selection includes the new CSV and replay tests.
