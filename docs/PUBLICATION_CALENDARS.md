# Reviewed publication references — 28 October 2026

This is a retrospective diagnostic reference, not a historical information vintage or trading calendar service. Reports make no network calls. Metadata has a SHA-256 pin in `publication_calendar.py`; altered bytes fail instead of silently changing expectations. The underlying downloaded XML hashes and URLs are retained in the metadata. Raw rate values are not redistributed here. Local hashes do not provide an independent signature.

## ECB

The [ECB reference-rate page](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) describes weekday publication excluding TARGET closing days and lists 29 currencies. The [2026 holiday page](https://www.ecb.europa.eu/ecb/contacts/working-hours/html/index.en.html) marks TARGET closures separately from office holidays. Only marked closures are excluded; Ascension Day, for example, is not a TARGET closure. The model uses dates, not a guaranteed publication-time deadline.

The reviewed official 90-day XML contains the same 29 series on 64 dates from 2026-07-30 through 2026-10-27. That bounded interval is the supported series-history scope. The 2026 TARGET holiday rules do not authorize extrapolating the series list into other periods. RUB is not expected. Unknown dates outside this interval remain explicitly outside the assessment.

## Treasury

The [official XML documentation](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed) identifies the yearly endpoint. Its reviewed 2025 response contains 249 publication dates and 14 canonical par-yield tenors. `BC_30YEARDISPLAY` is a display field rather than an additional maturity and is excluded. The [developer notice](https://home.treasury.gov/developer-notice-xml-changes) documents `BC_1_5MONTH` from 2025-02-18. The actual response has 218 non-null observations for that tenor from that date; the other 13 tenors occur on all 249 dates. No interior null exceptions occurred in this reviewed response.

Treasury describes daily business-day pricing, but the reviewed documentation does not establish a complete reusable holiday/exception calendar. Therefore Treasury uses the explicit **publisher-observed 2025 date list**, not an assumed US federal, stock-exchange or SIFMA calendar. This reference can identify locally missing publication dates, but cannot detect days omitted by Treasury itself or predict future dates. First and last observed series dates are reference bounds, not inferred lifetime boundaries.

## Comparison and findings

Each verified version is compared separately over the intersection of its observed date range and the reviewed reference range. Whole absent series and whole absent interior dates can now be detected. No coverage outside that intersection is certified, including missing leading/trailing dates beyond the snapshot's observed range. Extra series and observations outside the expected grid are reported without being silently discarded. Details are capped at 500 with exact totals.

On the original local snapshots, ECB has no missing expected cells within 2026-07-30–2026-10-26; the snapshot's 2026-07-29 date lies outside the review range. Treasury has 218 missing `BC_1_5MONTH` cells: the existing collector's integer-maturity pattern omits this field. This is a normalization coverage finding, not a provider outage. Hash verification can pass even when an adapter omits a field: byte integrity and semantic completeness are different checks.

The collector and historical manifests remain unchanged. Fixing normalization requires a separately reviewed collector change and newly collected versions; no migration, hash exception or silent data repair was added. V4.1 and its prospective gate remain untouched. No orders or evaluations are performed.
