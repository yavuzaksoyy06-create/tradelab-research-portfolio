# Statistical methodology and interpretation

## Experimental question

Do predetermined, causally available support/resistance rules produce economically useful outcomes under explicit execution costs and shared-capital constraints? The current evidence does not establish a robust advantage.

## Chronology and contamination

The original historical sample covered 142 sessions, split into 70 training-diagnostic, 30 validation-diagnostic and 42 observed-replay sessions. These periods have now all been inspected. Reusing them cannot create new untouched out-of-sample evidence. Future changes need a new pre-registered protocol and a genuinely subsequent sample.

## Comparisons

V4.1 compares candidate opportunities against deterministic, same-symbol/session/hour-bucket timing controls. Anchor geometry is translated to later completed closes; future realized exits are not used to force equal exposure. Multiple seeds are retained, not selected for a favorable result. Seeds are alternative simulations on the same market, not independent market observations.

This is a conditional timing comparison, not identification of the causal benefit of support/resistance detection. Realized allocation, exposure and holding duration may still differ.

## Uncertainty

The implementation uses paired portfolio-session observations and circular five-session blocks to retain within-session cross-symbol dependence. Historical settings used 1,000 resamples, minimum session/active-session requirements and separate eligibility thresholds for Sharpe-like metrics. Small samples yield unavailable statistics instead of persuasive-looking numbers.

The 42-session replay touch comparison had a descriptive interval spanning zero. Other candidate comparisons were too sparse for interval estimation. No multiple-testing-adjusted statistical significance, ML generalization score or causal alpha is asserted.

## Costs and accounting

Spread/slippage assumptions are explicit per-side basis points; they are not measured execution costs. Stops are not guaranteed fill prices during gaps. If a bar touches both stop and target with unknown ordering, the simulator uses a conservative documented policy and records ambiguity. Whole-bar excursions cannot always be interpreted as position-valid MFE/MAE.

Shared-cash experiments reconcile cash, marked equity and realized P&L; concurrent symbol orders cannot independently spend the same cash. Risk thresholds are observed rules, not guarantees of a hard maximum loss.

## Public reference data

ECB daily rates and Treasury par yields are suitable here for descriptive source inspection. They cannot substitute for intraday OHLCV, volume, spread observations or point-in-time release archives. A historical date in a file fetched today does not prove what was published on that date.

## Business-facing interpretation

The defensible recommendation from an inconclusive experiment is to withhold deployment, document the limitation and design the next test. In an analytics consultancy, that discipline transfers to avoiding leakage, misleading lift, cherry-picked segments and unjustified confidence in predictive models. This project itself does not claim a deployed customer predictive model.
