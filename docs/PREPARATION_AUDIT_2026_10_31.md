# Preparation integrity audit — 31 October 2026

Base: `a19305a`. The plan/review audit used simulated snapshots and temporary directories, without opening private market caches. Four adversarial tests reproduced five assertion failures before fixes. These were integrity defects, not automated approval rejections.

| Reproduced condition | Previous behavior | Fix |
| --- | --- | --- |
| Snapshot A hashed, valid B consumed, A restored before final hash | B metadata could be reported with A hashes | Bind the actual loaded manifest/CSV bytes to the initial digests before interpretation |
| File grows after a small stat result | Loader could consume more than its size bound | Read at most the limit plus one byte and reject overflow |
| Manifest byte count differs from actual CSV | Count was ignored | Require an exact integer byte count; return `MANIFEST_MISMATCH` |
| Optional session or missing-bar count contradicts validated frame | Counters were ignored | Check all supplied counters against actual coverage, including exact integer types |

The targeted Stage 7 review, preparation UI, historical research and audit regressions passed (56 tests). Full public regression evidence for this development phase is recorded separately. Offline plan bounds, the sealed cutoff, source registration and replay/holdout algorithms are unchanged.

The review still validates all historical bars structurally; it does not fit models, construct outcomes or score the reserved holdout. Before/after checks and byte binding establish content consistency, not independent provider authenticity, source licensing or an atomic filesystem transaction. Owner-controlled manifests can be rewritten; changing records does not create new unseen evidence. Local-path and loopback restrictions remain in the UI. No orders were sent.
