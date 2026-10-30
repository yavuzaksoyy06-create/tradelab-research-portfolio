# Stage 7 limitations and release boundary

- No real Stage 7 historical experiment ran during implementation. Synthetic diagnostics validate software mechanics only.
- Scenario probabilities are always suppressed in this slice. Passing minimum diagnostic thresholds does not unlock them. No calibrated bullish/bearish probability, price target, or tradable edge is claimed.
- Final historical holdout (last 20 complete sessions of a fixed input snapshot) is never labeled/scored. A snapshot is an immutable experiment input; appending/replacing it is a new research registration, not permission to recycle its holdout into training. The audited UI now binds evaluation to the full snapshot and caps chart/replay before that boundary. Real evaluation requires an immutable partition registration. Already inspected data cannot retroactively become unseen; see STAGE7_AUDIT.md.
- Stage 7 rejects all dates on/after 2026-10-26. There is no automatic release after the original 2027-01-21 21:15 UTC V4.1 gate. Frozen protocols and results are separate.
- The bounded collector permits at most 120 sessions and 200 calendar days, in batches of ten sessions. At that maximum only roughly 60 OOS sessions remain after training/holdout, so minimum diagnostic thresholds may still fail. This does not provide broad regime coverage.
- IEX and SIP are never mixed or automatically substituted. Entitlement/fees must be checked in the user's account. Missing full-session bars reject the dataset; an alternative sparse-IEX eligibility policy has **not** been approved.
- HTTP retrieval, hashes and local manifests establish transport/byte lineage, not an independent source signature, exchange certification, point-in-time vintage or redistribution permission. A manifest can be edited by its owner; hashes are not digital signatures.
- Split adjustment can revise historical values as later corporate actions occur. Independently archived vintages are not available. Dividends, costs, spread, slippage, position sizing and execution are outside this study.
- RVOL is not time-of-day adjusted. RSI is recorded but not separately tuned. The model uses fixed structure/EMA/RVOL buckets; sparse cells fall back to train frequency.
- Only the most recent confirmed S/R break is eligible for a 16-bar retest. Geometry is frozen at the pre-crossing observation; ambiguity is conservatively excluded from directional S/R path conclusions. OHLC cannot resolve intrabar order.
- Session block bootstrap is approximate and does not remove all cross-session dependence. Confidence intervals are diagnostic, not evidence of profitability. Multiple comparisons are disclosed, not converted into unadjusted significance claims.
- Default Stage 7 exports omit prices/returns. Existing Stage 6 explicit commentary exports retain their documented numeric content. Private collection CLI only writes new folders outside Git and never overwrites prior snapshots.
- Offline tests use an existing Windows Python 3.12 environment. GitHub Actions separately tests the pinned dependency installation. No user account/API entitlement was probed; no downloads or broker orders were sent.

## Safe local research commands (optional, separate from installation)

Start with the offline `plan` and read-only `review` commands in [snapshot preparation](STAGE7_DATA_REVIEW.md). They neither collect data nor evaluate a model. A successful structural review is not independent provenance verification or permission to release the holdout.

Run from the portfolio clone, with its Python environment activated. Supply credentials through the local process environment; never put their values in commands committed to Git or in a shared Streamlit server. These commands are examples and were **not executed against Alpaca**.

```powershell
python -B tools/stage7_research.py collect --symbol SPY --feed sip --start 2025-01-02 --end 2025-06-25 --output C:\PrivateTradeLabData\spy_sip_stage7_001 --allow-download
python -B tools/stage7_research.py evaluate --snapshot C:\PrivateTradeLabData\spy_sip_stage7_001
```

The collection date range must be <=120 XNYS sessions. The pinned calendar was checked offline: this example has 119 sessions and 3,094 scheduled bars. Use a new destination name for every retrieval; do not overwrite or pool snapshots/feeds. Review the printed diagnostic report locally. If download or coverage fails, no usable partial snapshot is returned. Rate-limit/entitlement failures stop with sanitized text; retry manually after checking entitlement. No trading endpoints are implemented.
