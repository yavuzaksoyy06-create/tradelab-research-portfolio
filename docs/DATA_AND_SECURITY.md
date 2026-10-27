# Data, security and publication boundaries

## Included

- Reviewed first-party research source and test fixtures.
- Frozen protocol definitions, source digests and explanatory documentation.
- Selected application screenshots with no credentials or account details.
- Public-package test results distinct from historical workstation evidence.

## Excluded

`.env`, credentials, API tokens, brokerage/account configuration, root trading bot and connection scripts, original Git history, unknown untracked files, raw public-source downloads, licensed Alpaca/SIP price caches, trade/output datasets, private checkpoint copies, logs with workstation paths, Graphify full-repository output and vendored third-party libraries.

Historical numerical results documented in the archived report are hypothetical research summaries, not account statements. Raw provider data is not necessary to inspect the method and is not redistributed.

## Source review

- [ECB reference-rate documentation](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html): informational daily EUR-base reference rates.
- [ECB copyright conditions](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html): attribution and accurate reproduction; transformations must be disclosed.
- [Treasury XML feed documentation](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed): public official daily rate endpoints and year/month query structure.

Collectors use fixed HTTPS URLs, certificate validation through the existing certifi trust bundle, no redirects, a 30-second timeout and a 4 MB limit. No authentication, paid subscription or external upload is required for these two feeds. Commercial redistribution rights are not inferred from public accessibility.

## Meaning of hashes

A digest proves equality relative to the reference being trusted. It does not independently establish publisher identity, data accuracy, license rights or publication vintage. An attacker who changes code, data and pins together can defeat local checks. Independent custody of release pins is a separate operational requirement.

## Frozen gate

The original V4.1 future window ends no earlier than 21 January 2027 at 21:15 UTC. The public workspace has no prospective evaluator. A passing clock alone is insufficient, and missing excluded evidence is never substituted with mock approval.

## Reporting problems

Do not post credentials, account data or private provider files in issues. Report reproducible problems with synthetic fixtures and the relevant source/version hashes.
