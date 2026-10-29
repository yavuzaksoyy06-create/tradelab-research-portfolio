# Public demonstration — historical AAPL daily example

The default TradeLab demo uses an **offline, bundled, real historical daily OHLCV example**, not the former synthetic illustration.

## Source and redistribution

- Upstream file: [Plotly datasets / finance-charts-apple.csv](https://github.com/plotly/datasets/blob/master/finance-charts-apple.csv)
- Upstream repository: [Plotly datasets](https://github.com/plotly/datasets) (MIT license; see upstream LICENSE)
- Bundled selection: [demo_data/aapl_daily_2015_2017.csv](../demo_data/aapl_daily_2015_2017.csv)
- Stock: Apple Inc. (AAPL); **506 DAILY candles, 2015-02-17 through 2017-02-16**.
- Preserved fields: date, open, high, low, close, volume (the upstream extra bands/direction columns were excluded).
- All demo chart data is read from the bundled CSV without making external HTTP requests. The example is historical; NOT live market data.

**Limits:** Plotly's sample repository is MIT-licensed, but the original quote vendor, corporate-action adjustment conventions and point-in-time fidelity are not independently established by TradeLab. These columns are not treated as certified exchange records or a basis for trading signals. The chart cannot be used to reproduce V4.1's separate 15-minute research.

## Observable-only features

- The replay slider advances **one observed daily row at a time**; the visible price prefix is the only input to indicators, pivot detection and English commentary.
- EMA 20/50/200 use daily closes with warm-up; Wilder RSI(14) has warm-up; RVOL divides current daily volume by the mean of the **20 preceding daily volumes**.
- Confirmed pivots use 2 completed days before and 2 completed days after the candidate; the label is plotted at **the confirmation date** and the level starts no earlier than that date. No retrospective backdated labels.
- The price viewport shows the most recent 110 visible daily observations for readability; indicators use the entire visible replay prefix.
- The narrative is deterministic descriptive English, not an AI-generated forecast, alpha claim, or buy/sell advice.

The original SPY/MSFT/QQQ 15-minute code, frozen V4.1 research and Stage 7 holdout safeguards remain independent and unchanged.

## Deployment

Install from root `requirements.txt`, then run `streamlit run demo_app.py`. For Streamlit Community Cloud select repository `yavuzaksoyy06-create/tradelab-research-portfolio`, branch `main`, entrypoint `demo_app.py`, Python 3.12, and **no secrets**.

The app is not hosted merely because the code is in GitHub. The owner must authorize deployment; do not claim or guess a public `streamlit.app` URL before verification.

[Demo technical entrypoint](../demo_app.py) · [README](../README.md) · [Historical research evidence](SR_RESEARCH_EVIDENCE.md).
