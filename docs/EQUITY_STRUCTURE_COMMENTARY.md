# Stage 6 — Causal technical overlays and Turkish chart commentary

**Scope:** descriptive inspection of completed 15-minute XNYS equity candles. This module does not predict returns, recommend orders, place orders, verify data authenticity, or change V4/V4.1 / the 21 January 2027 research gate.

## Confirmed swing market structure

We **reuse** the frozen V4 engine's causally confirmed pivot events; the original pivot rules and parameters are unchanged.

- **HH**: latest confirmed resistance pivot is higher than the preceding confirmed resistance pivot.
- **LH**: latest confirmed resistance pivot is lower than the preceding confirmed resistance pivot.
- **HL**: latest confirmed support pivot is higher than the preceding confirmed support pivot.
- **LL**: latest confirmed support pivot is lower than the preceding confirmed support pivot.
- **EH / EL**: approximately equal highs / lows under a tiny numerical tolerance (1e-8 times the preceding pivot's absolute price, floored at 1).
- **H0 / L0**: first confirmed high / low, with no same-kind predecessor.

The chart places a structure label at the **confirmation candle**, not at the earlier candidate pivot. A 'rising' structure requires latest **HH + HL**; a 'falling' structure requires **LH + LL**. Other comparable combinations are 'mixed'; a missing prior comparison is 'insufficient'. This is a mechanical comparison, **not** a statistical market-regime classifier.

## Confirmed mechanical trendlines

A support line uses the last two **confirmed support pivots**, and a resistance line uses the last two **confirmed resistance pivots**. For pivot prices `p1,p2` and original bar indices `i1,i2`, its slope per 15-minute bar is `(p2-p1)/(i2-i1)`. At completed bar index `t`, the line value is `p2 + slope*(t-i2)`. Importantly:

1. **Nothing** is drawn before the **second** pivot's confirmation bar.
2. Values are plotted only through the current replay bar, not beyond it.
3. A new confirmed pivot retires the previous pair's segment at the prior completed bar. Historical segments stay unchanged; they are not redrawn with newly discovered future pivots.
4. A trendline is a mechanical two-point extrapolation, **not** a prediction or tested support/resistance edge. Large slopes may extrapolate outside observed prices.

Time-axis gaps are visually compressed without changing the underlying candle timestamps or fabricating missing regular-session candles.

## Volume, EMA and RSI

- **RVOL(20)**: the current completed candle's volume divided by the mean of the **20 preceding** completed candles; the current bar is excluded from the denominator. A zero or unavailable denominator yields N/A. RVOL is **not** adjusted for time-of-day / intraday volume seasonality.
- **EMA 9/21/50/200**: 15-minute-bar recursive exponential averages, initially seeded from the first close, hidden until their own period's required history is present.
- **RSI(14)**: Wilder smoothing of 14 close differences, first available at the 15th completed close.
- **IEX vs SIP**: their volume coverage differs. No reliable inference about institutional participation, consolidated-volume percentiles or the full US market is drawn from IEX-only volume.

## Türkçe yorum paneli (deterministic rules)

`equity_commentary.commentary_report(prefix, features, metadata)` returns a structured report and explicit numerical evidence. It describes:

1. Timestamp and last **completed** candle close, with prior-bar—not daily—percent change where possible.
2. Last confirmed HH/HL/LH/LL comparisons and age in completed bars.
3. EMA9 vs EMA21 and last close vs EMA21, plus RSI value/reference band only after indicator warm-up.
4. RVOL vs the preceding 20-bar mean (1.50x and 0.75x are descriptive word-choice thresholds only; neither has been optimized or validated as a trading rule).
5. Nearest relevant **active** support and resistance zone in the final completed-bar snapshot, when available.
6. Latest mechanical confirmed-low/high trendline value and slope, when both pivots exist.
7. Declared data origin and feed, educational vs market-data label, lack of independent point-in-time verification, and non-advisory research scope.

The report is **not an LLM** and does not claim prediction, tested profitability, price targets, institutional buying/selling, or order execution. On short samples, missing values are explicitly marked unavailable. The panel can export a JSON report with the as-of timestamp, descriptive text and evidence values but **not price rows, API secrets or credentials**.

The chart's HH/HL labels and trendline segments, and commentary for a given replay position, use only confirmed events visible at that position. No hidden completed-bar data is backfilled into earlier as-of snapshots. The original V4.1 experiment remains frozen.

## Testing contract

Offline tests include: exact swing classification, pivot confirmation timing, trendline-segment start/stop and cursor clipping, prefix invariance, EMA/RSI/RVOL warm-up, empty data and feed provenance guards, deterministic evidence-backed commentary, and existing CSV / paper-safe UI tests. Network access and order endpoints are not used in the automated public test suite.

See [Equity Research Lab](EQUITY_RESEARCH_LAB.md) for data source and session coverage limitations.
