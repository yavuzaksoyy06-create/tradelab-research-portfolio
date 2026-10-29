# Stage 7 leakage and integrity audit — 29 October 2026

Audited base: 4d6f0c1f09c09022ec18724195dec14ea1b9a623 on feature/equity-lab-stage6-slice1. This is an offline code/data-flow audit, not a real-market performance study or independent security certification.

## Demonstrated findings and corrections

| Finding | Previous behavior | Correction |
|---|---|---|
| Reserved historical outcomes exposed outside the evaluator | evaluate_history withheld the last 20 sessions, but event_dataset calculated their labels and the chart allowed the cursor into them | A shared full-snapshot boundary caps chart/commentary/replay features and label construction; horizons crossing the boundary remain pending |
| Replay-dependent holdout | The UI passed a truncated frame to evaluation, recomputing the last 20 sessions at each cursor | Evaluation receives the full snapshot plus a separate visible count; the partition stays fixed and only completed visible validation folds are scored |
| No immutable partition binding | Replacing/truncating an input could silently move its reserved interval | New private snapshots include a canonical dataset fingerprint, bar count and holdout boundary; registered changes fail closed in validation, replay, storage and reload. Actual-history fitting requires registration |
| Negative positional index | A malformed outcome record with index -5 and horizon 4 selected the last row through pandas iloc[-1] | Explicit integer/range checks reject invalid observation/event indices and horizons |
| Unvalidated private writer | save_private could serialize sealed dates supplied directly by a caller | Timestamp boundary and full data validation now run before any destination directory is created |
| Arbitrary metadata copied to disk | An extra api_key field, or nested batch headers, could be copied verbatim to manifest.json | Only documented source fields and receipt fields are serialized; credential/header test sentinels are excluded |

Before fixes, the initial six new regression tests produced five assertion failures and one API-signature error (the separate replay cursor argument did not exist). The negative-index and private-writer tests use malformed inputs; they do not imply normal UI traffic had already exercised those paths. The chart reproduction exposed all 3,094 synthetic bars instead of stopping at the registered boundary, 2,574.

## Verification

Nine new audit tests cover: holdout/crossing-horizon labels; stable replay evaluation partition; negative indices; sealed writer rejection; metadata allowlisting; long-history chart cursor limit; registered snapshot replacement/truncation; refusal to fit unregistered actual history; canonical private CSV round-trip and nested-header exclusion.

Existing causal prefix, pivot, trendline, embargo, model, calibration, transport, scenario and UI tests remain in place. Tests use synthetic histories and temporary private directories; no account credentials, licensed price caches or actual prospective data are accessed.

Exact full-suite results, archived prior evidence, current source hashes and frozen-file comparison are recorded in evidence/stage7_audit_checks.json. The existing Windows symlink test can be skipped locally when the OS privilege is unavailable; GitHub checks report their own result.

## Limits and compatibility

- A code fix cannot make a previously viewed historical period unseen. Any snapshot inspected under the earlier UI must not be described as an untouched confirmatory holdout. Real predictive validation and scenario probabilities remain unavailable.
- Reservation applies to snapshots with at least 80 sessions. Short educational/inspection datasets do not qualify for validation and have no declared holdout. Reserved periods are hidden from the integrated equity page, not only the Stage 7 table.
- The same complete snapshot must be supplied across replay cursors. An immutable registration rejects changed bytes rather than silently updating the boundary. This is not a signature, authorization system or global registry preventing an owner from deliberately creating another experiment.
- Legacy manifests without a registration can still be structurally read; actual long-history model evaluation refuses them. No automatic migration, resaving or redownload of private data is performed.
- Whole-input structural validation and hashing still read the loaded historical frame; reserved values are not used in features, chart, training or outcome metrics. Frozen prospective caches remain unopened.
- The CSV writer uses 17 significant digits and round-trip parsing so canonical numeric fingerprints survive save/load. Dependencies remain pinned; the installed pandas emits a deprecation warning for float_precision, which does not invalidate the current tests.
- The original research protocol is retained, with this explicit enforcement addendum. No model, horizon, smoothing, trading strategy or minimum evidence threshold is tuned in this audit.
- V4/V4.1 and the January 21, 2027 21:15 UTC gate remain unchanged. Stage 7 still rejects all dates on/after October 26, 2026. No downloads or orders are issued.
