# Istanbul index machine learning protocol v1

Registered before downloading or evaluating the real observations, 31 October 2026. This is an independent historical index-return exercise, not the THYAO/GARAN/ASELS 2020–2024 study. Frozen V4/V4.1 and all existing holdout/time gates remain unchanged.

## Data and fixed partition

Use only [UCI Istanbul Stock Exchange, dataset 247](https://archive.ics.uci.edu/dataset/247/istanbul+stock+exchange), Oguz Akbilgic (2013), DOI [10.24432/C54P4J](https://doi.org/10.24432/C54P4J), under CC BY 4.0. Preserve source attribution and exact source/normalized byte hashes. Expected 536 chronologically ordered observations with two Istanbul and seven foreign-index return columns. Original column labels must be checked before mapping. No OHLC, volume, price levels or individual-stock data are implied.

The first 321 rows form development history, the next 107 rows (indices 321–427) are fixed validation, and the final 108 rows (428–535) remain reserved, never modeled, scored or charted. Validation may be inspected chronologically through a cursor capped at 428. Changing the input creates a new identity, not new unseen evidence. Dates must remain in 2009–2011 and strictly outside every existing sealed period. The UCI page's June 2009 start conflicts with the original paper's January 2009 start; file dates are authoritative for this snapshot and the discrepancy must be disclosed.

The original paper reports forward filling missing foreign-index observations. This supplied preprocessing is retained and disclosed, not described as pristine synchronized market data. Data are retrospective and lack independently archived publication vintages. The available documentation does not establish simple versus log-return semantics: do not compound these columns into a price, tradable P&L or a transaction-cost result.

## One fixed model and baselines

Predict the first Istanbul return column using all nine return columns at lags two and three, plus five- and twenty-observation mean and population standard deviation of that target ending two rows earlier. No same-day or next-day foreign-market predictor is allowed. Conservative row lags reduce close-time leakage but do not certify point-in-time availability.

Model: ridge linear regression, fixed L2 penalty 10 on standardized coefficients, unpenalized intercept. Standardization is fitted on each training window only. Refit every 20 validation observations with expanding history; exclude the two most recent rows before each block start from training. No hyperparameter search or model selection. Warm-up rows with incomplete lagged features are unavailable, never backfilled.

Baselines: zero prediction, training-only mean, target persistence at lag two. Report RMSE, MAE, directional accuracy and balanced accuracy where both classes exist. Compare paired squared errors with training-mean baseline using a moving 20-row block bootstrap, 500 replicates, seed 7, and a 95% percentile interval. These dependent small-sample diagnostics are not a significant-alpha declaration. No calibrated probabilities are produced.

## Research signals and explanations

At each eligible validation observation: LONG if predicted source-unit return exceeds 0.005, WATCH if positive but no greater than 0.005, CASH otherwise. This fixed threshold is a source-unit heuristic, not a verified 50-bp cost threshold. Signal inputs end at least two observed rows before the target date. Show target date, feature cutoff, training cutoff and the largest signed linear feature contributions. Coefficient contributions are model arithmetic, not causal economic explanations.

This lab emits historical research labels, not executable broker instructions, investment recommendations, live forecasts or proven profits. Graphs show observed returns, predictions/errors and historical signal annotations. No candlesticks or synthetic price index may be invented from this return-only source.

## Required validation before reporting

Tests must cover train-only scaling, independently calculated ridge predictions, prefix/suffix invariance, reserved-row isolation, metadata binding, invalid/nonfinite input rejection, deterministic resampling and UI replay bounds. Actual validation metrics may be reported only after source hashes and protocol implementation are recorded. Poor or null results remain visible; no post-result threshold/model/period edits. Any further research specification requires a separate registered version.
