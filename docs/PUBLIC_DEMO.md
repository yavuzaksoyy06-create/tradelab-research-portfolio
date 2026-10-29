# TradeLab interactive portfolio demo

**Entry point:** [`demo_app.py`](../demo_app.py) · **data:** deterministic synthetic educational fixtures only.

## Purpose

A potential employer can inspect a real interactive Streamlit/Plotly interface, move the historical replay cursor, view causally confirmed support/resistance and indicators, read deterministic Turkish evidence commentary, inspect archived strategy research results, and experiment with theoretical expected value.

The interactive candles **are not SPY, MSFT or QQQ market prices**; each symbol label shares the same generated educational path. The old study figures and Treasury/ECB screenshots are separate archival outputs, not data being downloaded or newly evaluated by the public app.

## Privacy and research boundaries

- The demo has **no Alpaca API key, data collection, uploaded-user-file, brokerage-order or portfolio execution path**.
- No `secrets.toml`, private datasets, accounts, or licensed OHLCV snapshots are required or embedded.
- No live forecast probabilities, AI trading signals, investment advice or validated edge are published.
- This hosted demo is not a substitute for the original V4.1 historical backtest or any Stage 7 confirmatory evaluation.

## Run locally

From the root of this public repository, with Python 3.12:

```powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.\\.venv\\Scripts\\python.exe -B -m streamlit run demo_app.py
```

The public source test runner includes `test_public_demo.py`, a Streamlit AppTest and a static entrypoint check. The project's complete offline test contract is currently validated on Windows; the original immutable snapshot publisher is Windows-specific.

## Deploy to Streamlit Community Cloud

The repository is public. Log into [Streamlit Community Cloud](https://share.streamlit.io/) with GitHub, choose **Create app → I have an app**, then configure:

| Setting | Value |
|---|---|
| Repository | `yavuzaksoyy06-create/tradelab-research-portfolio` |
| Branch | `main` |
| Main file path | `demo_app.py` |
| Python | `3.12` if selectable |
| Secrets | **Leave empty** |

Select **Deploy**. Only the owner of the Streamlit Community Cloud account can authorize deployment and choose/confirm the public URL. A repository commit does **not** automatically create a hosted app URL.

When a public deployment exists, update the root README with its **verified** URL and test it in an unauthenticated browser. Do not guess a `streamlit.app` subdomain.

## Hosting note

The deployed runtime is Linux. The demo code itself is synthetic, read-only and uses no Windows-only publishing operation, but the full original project's test suite has documented Windows-specific publisher tests; cross-platform reliability of the hosted demo must be verified from its actual deployment logs rather than assumed.

[Main project](../README.md) · [Data source contracts](EQUITY_RESEARCH_LAB.md) · [Validation limitations](STAGE7_LIMITATIONS.md)
