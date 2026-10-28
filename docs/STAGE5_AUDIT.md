# Stage 5 follow-up audit — 28 October 2026

This is an internal implementation review, not an independent external audit.
Baseline: f4a718ea2b5acb6602db31cf76e0d7afceb9d16d. The working tree was clean;
a source SHA-256 checkpoint was saved outside the public tree before changes.

## Reproduced findings and fixes

1. Treasury differences could bridge an entirely absent known publication date.
   They now become missing for such intervals, while valid Friday/Monday intervals
   remain measurable. The previous date and calendar assessment accompany the CSV.
2. FX rolling volatility could include intervals outside reviewed calendar scope.
   It now requires consecutive reviewed reference observations for every return
   in the window. Outside-scope endpoint changes remain descriptive, visibly
   classified as unreviewed; they do not enter rolling volatility.
3. The calculation boundary accepted collection timestamps after availability.
   It now requires collection <= availability <= current time.
4. CSV provenance omitted the analytic implementation and reference-policy hashes.
   Both are now exported, along with the synthetic-data flag.
5. CSV formula guards only covered object columns, missing pandas string columns
   and leading-control-character cases. All textual cells are checked; formula
   prefixes and leading whitespace/control characters receive a literal prefix.

Eight new audit tests reproduced six failures and one missing-field error before
fixes; the valid weekend case passed. The initial restricted-environment attempt
also encountered Windows temporary-folder access errors and was rerun normally;
these are distinct from the reproduced implementation findings.

The complete fixed suite ran 387 tests: 386 passed, one existing Windows symlink
permission skip. Counts are from a single complete run, not sums of historical runs.
No frozen engine, prospective protocol, collector or Treasury v2 code was changed.
Existing data revisions retain their original code pins; no snapshot was migrated.

## Remaining limits

Calendar references remain bounded and retrospective. Unknown calendar scope is
not certified complete. Treasury intervals outside its reviewed scope remain
explicitly labeled observed intervals. No provider outage or point-in-time history
is inferred. Synthetic flags describe test fixtures, not a publisher certification.
Hash pins cannot defeat coordinated modification by a writer controlling all local
references. This audit does not claim every possible bug has been eliminated.
