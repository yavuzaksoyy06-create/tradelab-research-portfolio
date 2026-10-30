# Stage 7: offline planning and snapshot review

I separated dataset preparation from model evaluation so that coverage and integrity can be inspected before any outcome analysis. These commands do not download data, read credentials, send orders or modify a snapshot.

## 1. Plan expected coverage

```powershell
python -B tools/stage7_research.py plan --symbol SPY --feed sip --start 2025-01-02 --end 2025-06-25
```

The XNYS calendar supplies complete sessions and expected 15-minute bars, grouped into ten-session batches. Supported symbols are SPY, MSFT and QQQ; feeds must be explicitly IEX or SIP. Bounds remain 200 calendar days and 120 sessions. Dates on/after 2026-10-26 are rejected. Planning performs zero network requests and does not verify feed entitlement, price availability or licensing.

## 2. Review an existing private snapshot

```powershell
python -B tools/stage7_research.py review --snapshot C:\PrivateTradeLabData\spy_sip_stage7_001
```

Use a snapshot already created by the explicit collector described in [limitations](STAGE7_LIMITATIONS.md). Review never creates or migrates one. It checks bounded file sizes, the CSV hash, source schema, complete-session coverage, the sealed-period boundary and the registered research partition. It hashes both files before and after loading to detect observed changes during review; this is not a transactional filesystem snapshot or a defense against an adversarial concurrent writer.

Successful structural review returns `verified_structure`, file hashes, session/bar counts, partition registration and holdout metadata. Prices, volume, outcomes, arbitrary source metadata and local paths are omitted. `diagnostic_eligible` requires a registered partition and sufficient history to reserve the final 20 sessions. It does not certify calibration, provenance or predictive value. A legacy unregistered snapshot remains ineligible; review does not silently register it.

Exit code 0 means structural review succeeded, including structurally valid but diagnostically ineligible records. Consumers must inspect `diagnostic_eligible` and `eligibility_reason`. Exit code 1 means rejection. Controlled reasons include `HASH_MISMATCH`, `COVERAGE_MISMATCH`, `PARTITION_MISMATCH`, `SEALED_PERIOD`, `INPUT_TOO_LARGE`, `UNSUPPORTED_MANIFEST`, `MISSING_OR_UNREADABLE_FILES`, `SNAPSHOT_CHANGED` and fallback `INVALID_SNAPSHOT`. Provider bodies and raw exceptions are not printed.

## Evidence and limits

Eight added tests cover offline planning, date bounds, byte-preserving review, hash mismatch, legacy registration, sanitized failures, observed concurrent changes and CLI separation from evaluation. All fixtures are simulated; no real historical snapshot was collected or evaluated for this feature. [Recorded checks](../evidence/stage7_review_checks.json) preserve full regression results.

Hashes establish byte identity, not independent authenticity or point-in-time provenance. Review reads and validates historical bars but does not fit models, label outcomes or score the reserved holdout. Model evaluation remains a separate explicit action. V4/V4.1 and its 2027-01-21 21:15 UTC gate remain unchanged; Stage 7 has no release override.
