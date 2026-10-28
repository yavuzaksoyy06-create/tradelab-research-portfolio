# Treasury normalization: a data completeness case study

## Problem

A hash-valid local 2025 Treasury snapshot contained 3,237 observations and 13 tenors.
The independent publication-reference comparison found 218 absent 1.5-month records.
Hash integrity alone did not establish semantic completeness.

## Investigation and root cause

The old parser selected fields with `BC_\d+(MONTH|YEAR)`. The official field
`BC_1_5MONTH` contains an underscore and therefore never matched. The raw XML had
the values; normalization dropped them. A deterministic all-tenor fixture reproduces
13 old rows versus 14 new rows. The Treasury developer notice establishes the
2025-02-18 activation date. `BC_30YEARDISPLAY` is not a separate maturity.

## Safe remediation

The old collector, verifier, XML, CSV, manifests and pins are unchanged. A separately
identified revision, `treasury-explicit-tenors-2`, uses an explicit 14-tenor mapping.
It rejects unknown BC fields, duplicate dates/tenors, nonfinite/negative values,
wrong years and pre-activation 1.5-month values. Publisher nulls and absent fields
are recorded separately; neither becomes zero or a filled observation.

Derivation first verifies the legacy parent. It writes a new Windows no-replace
version namespace with its own manifest/pin, original raw bytes, parent manifest,
registry, normalized observations and missingness ledger. Code hashes bind both
the v2 normalizer and legacy verifier. Read-only review rederives CSV and missingness
from checked raw bytes. New analytics are available no earlier than derivation;
original collection time is retained separately. No backdated historical vintage
is claimed. Old and new revisions remain separately reviewable.

## Validation

Ten deterministic tests cover omission, all mappings, activation, display exclusion,
null/absent distinction, duplicates, numeric/date errors, unknown tenors, immutable
parent lineage, availability, unit and code hashes. The real offline derivation
recovered all 218 rows: 3,455 total observations. The old version still verifies with
3,237. No network request was made in Stage 5; data values were not invented.

## Business significance

This demonstrates a practical analytics control: reconcile semantic coverage against
an independently reviewed contract, investigate discrepancies, and fix transformations
without destroying the evidence that explains earlier results. It does not establish
financial alpha, a deployed client solution or independent external audit.

## Interview explanation

“I found a parser that passed file hashes but silently missed an officially added
maturity. I reproduced the problem with a small fixture, replaced implicit field
recognition with an explicit versioned contract, and generated a new derivative
with parent lineage. This recovered 218 observations while preserving every old
snapshot. Then I used the verified data for clearly defined descriptive analytics.”
