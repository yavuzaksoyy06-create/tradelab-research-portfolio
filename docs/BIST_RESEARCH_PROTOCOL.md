# BIST daily research protocol v1

Registered on 31 October 2026 before importing any real BIST observations or examining BIST performance. This is a separate retrospective research lab; it changes no frozen V4/V4.1 experiment or Stage 7 US-equity protocol.

## Fixed scope and data contract

- Universe: THYAO, GARAN, ASELS, considered separately. This selected current-survivor sample is not a historical BIST index membership universe; survivorship and selection bias remain.
- Frequency: daily XIST session dates, nominal TRY. Required CSV columns: `date,open,high,low,close,volume,adjusted_close`. Full 2020-01-01 through 2024-12-31 calendar coverage, no duplicate/unsorted/missing sessions and no imputation. Partial trading days still have one daily observation. The pinned calendar is not exchange certification.
- Development/warm-up: 2020–2022. Fixed out-of-sample diagnostic interval: 2023–2024. Calendar 2025 is reserved and is neither requested, imported, charted nor scored. All dates on/after the existing 2026-10-26 sealed boundary remain prohibited. There is no unlock switch.
- Source registration: provider, HTTPS source reference without authentication/query parameters, license/entitlement reference, symbol, currency, exchange, frequency, adjustment declaration and exact CSV SHA-256. User-confirmed local research permission is a declaration, not independent source authentication. Replacing bytes creates a new input identity; it does not produce a new untouched period.
- Prices must come from an entitled local export or a documented permitted provider. No scraper, broker connection, automatic download, generated-price fallback or raw-price publication is provided. Source raw bytes and chart images remain local. An immutable private registration command writes only a new folder outside Git.

## Frozen strategy and accounting

One model: long/cash when adjusted-close EMA20 > EMA60 after warm-up. No tuning, optimization or ranking. A signal at close t can execute at close t+1; close-to-close return at row t uses signal[t-2]. The one-session execution delay prevents a decision from filling at the same close used to form it. This is a simplified close-execution assumption, not a fill simulator.

Primary cost: 25 basis points per unit of position turnover; sensitivity: 10 and 50 bps. Costs include entry, changes and terminal liquidation. Each evaluation interval starts in cash; no free inherited position. Buy-and-hold uses the same period and entry/liquidation costs. Cash yield is zero; borrowing, shorting and leverage are absent. Fractional exposure is an accounting abstraction; lot sizes, commissions, taxes, spread, impact and price limits are not modeled separately. Returns are nominal TRY, without inflation or FX adjustment.

Report validation-only cumulative net return, annualized daily volatility (252 sessions), peak-to-trough drawdown, exposure, turnover and transitions; compare buy-and-hold and cash. Paired daily net excess mean uses a moving 20-session block bootstrap, 500 replicates, seed 7, with a 95% percentile interval. That interval is descriptive, is sensitive to block choice and is not a significance or tradable-alpha claim. Multiple symbols/cost settings are disclosed comparisons, not a parameter search. No proper excess-return Sharpe is claimed without a justified TRY risk-free series.

Retrieved adjusted closes can incorporate later corporate actions and revised vintages; causal signal code does not establish point-in-time data availability. Raw OHLC candles are shown separately from adjusted-close features. No cross-sectional portfolio weights, capital allocation recommendation or predictive probabilities are produced.

## Source assessment and actual status

No licensed real BIST CSV was available at registration. Actual BIST backtest results and real BIST chart artifacts are **not run / unavailable** until an entitled file passes validation; synthetic tests exercise mechanics only.

Primary references inspected:

- [BIST market data](https://borsaistanbul.com/piyasa-verileri) and [DataStore](https://datastore.borsaistanbul.com/) for historical data access; fees and permissions require the applicable product agreement.
- [BIST official holidays](https://www.borsaistanbul.com/en/official-holidays); [XIST calendar implementation](https://github.com/gerrymanoim/exchange_calendars/blob/master/exchange_calendars/exchange_calendar_xist.py), including exceptional earthquake closures. This lab uses session dates, not intraday trading-hour certification.
- [İş Yatırım terms](https://www.isyatirim.com.tr/SiteAssets/pdf/Kullanim_Kosullari.pdf), section 4(iv), restrict automated access; its undocumented endpoints are not scraped.
- [Yahoo historical downloads](https://help.yahoo.com/kb/finance-for-web/SLN2311.html) require the applicable subscription and can be limited by instrument licensing. No paid access is bypassed.
- [Yahoo adjusted-close definition](https://help.yahoo.com/kb/SLN28256.html): corporate-action adjustments are a data-vintage limitation, not proof of historical availability.
