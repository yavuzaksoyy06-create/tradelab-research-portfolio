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

## 3. Use the local interface

Start `research_workspace/app.py` with `--server.address 127.0.0.1`, then choose **Equity Research → Stage 7 · Veri Hazırlığı**. Preparation is available even when no chart file or provider snapshot has been loaded.

- Open **Veri toplama planı / plan**, choose the independent symbol, feed and dates, then select **Planı hesapla**. The report contains the expected sessions, bars and batch ranges. It does not establish actual data availability or entitlement.
- Open **Yerel veri kaydını incele / review**, enter the absolute folder of an existing private snapshot and select **Kaydı salt okunur incele**. Structural success and diagnostic eligibility are shown separately. A report never automatically loads a chart, evaluates a model, changes a registration or releases a holdout.

Both forms run only on submission. Reports are displayed for that run and disappear on another rerun; submit again to inspect current inputs/files. No report is cached or exported by this panel. Review is disabled unless the server is explicitly bound to literal `127.0.0.1` or `::1`. This configuration check is not authentication: do not forward or publicly proxy the local workspace. The hosted public demo is separate and does not expose this panel.

The UI rejects relative paths, UNC shares, Windows mapped network drives and symlink/junction components, including the two input files. The check is a preflight, not a transactional filesystem guarantee; do not edit or replace a snapshot while it is being reviewed. Errors show controlled codes instead of raw exceptions or local paths. The entered folder itself remains visible in the local form.

## Evidence and limits

Eight added tests cover offline planning, date bounds, byte-preserving review, hash mismatch, legacy registration, sanitized failures, observed concurrent changes and CLI separation from evaluation. All fixtures are simulated; no real historical snapshot was collected or evaluated for this feature. [Recorded checks](../evidence/stage7_review_checks.json) preserve full regression results.

UI submission, stale-report clearing, loopback gating, path checks, sanitized failures and preparation without chart data are covered separately. [UI checkpoint checks](../evidence/stage7_preparation_ui_checks.json) record the regression scope; prior CLI evidence remains historical.

Hashes establish byte identity, not independent authenticity or point-in-time provenance. Review reads and validates historical bars but does not fit models, label outcomes or score the reserved holdout. Model evaluation remains a separate explicit action. V4/V4.1 and its 2027-01-21 21:15 UTC gate remain unchanged; Stage 7 has no release override.
