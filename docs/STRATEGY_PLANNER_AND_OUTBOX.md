# Strategy planner and durable intent outbox

TradeLab can freeze a strategy hypothesis, replay it against completed bars, verify risk sizing and retain the resulting order drafts in a local queue. I separated the plan, rehearsal report and queue so each decision carries the evidence needed to reproduce it. Draft dispatch is disabled.

| Layer | Contract |
| --- | --- |
| Strategy plan | Strict, versioned JSON with one symbol, an allowlisted rule, integer risk limits and a SHA-256 digest. The plan status is `UNVALIDATED`. |
| Rehearsal | The existing event engine binds the plan digest to its policy and journal. Signal decisions use completed closes and size at a later simulated opening. |
| Stress | Four fixed cost and latency cases use the same frozen plan. The verifier checks each case against its expected plan policy. |
| Draft | A journal-linked simulated signal fill yields a broker-neutral MARKET/DAY draft with quantity, both timestamps and plan/source/report digests. |
| Outbox | A local SQLite journal atomically stages, cancels or halts drafts. Reopening reconstructs state and checks the event chain. |

## Planning rules and risk

Choose **Strateji Planlayıcı** in the localhost research workspace. Select SPY, MSFT or QQQ, set the rule and risk limits, and freeze the plan. Download the plan for later reproduction. The separate preview action uses the synthetic fixture and can export the verified rehearsal and its drafts. Editing clears the frozen plan and preview.

- **EMA trend.** Enter while the fast EMA exceeds the slow EMA after warmup. Exit a held position when the relationship reverses or ties.
- **Channel breakout.** Enter when the completed close exceeds the highest of the previous entry-window closes. Exit a held position below the lowest of the previous exit-window closes. Both comparisons exclude the current close from their reference range.

Risk inputs use integer basis points. The engine allows one whole-share long position, with an entry allocation ceiling of 10% of equity and planned stop risk up to 0.5% of equity. The session loss threshold is at most 2%, and positions last at most four bars. The plan can tighten these limits and set bounded stop and target distances. A halt stays active for the rest of that replay. Gap losses can exceed planned stop risk.

Plan-defined rehearsals reuse Stage 7's completed-session checks, snapshot holdout and 26 October 2026 cutoff. They take no Istanbul index-return observations. The 108 reserved rows, the 2025 BIST holdout, V4.1 and its 21 January 2027 at 21:15 UTC time gate retain their existing protections.

## Draft identity and durable state

Only an intent linked to a verified simulated fill has a sized draft. Pending or cancelled intents have no filled size. Stop, target, time, session and halt exits remain visible in the execution journal. They are outside the signal-draft queue.

The client intent ID hashes the plan, full source fingerprint, signal index and time, symbol and side. A retry of the same report inserts no duplicate. If another report supplies different content for the same identity, the entire batch is rejected. Separately versioned snapshots produce different identities even when dates overlap. This identity scope covers offline rehearsal of a specific snapshot.

Queue operations use SQLite transactions and an append-only event log. Staging records are immutable. Cancellation and halt add events. Halt cancels all staged drafts atomically and latches across process restarts. Providing an independently retained `--expected-head` makes the operation conditional on the store still having that exact journal head, including for writes. Use `recover` after an interrupted SQLite write to roll back uncommitted changes and audit the last committed journal. Recovery adds no draft or state event.

Database files must be in an existing absolute local directory outside a Git checkout. The CLI rejects network locations and redirected paths. Record hashes detect inconsistent state and an expected head can detect a restored older copy. The hashes provide integrity checks and leave publisher authentication to a separate system.

## Reproduce locally

Save the plan JSON from the planner as `strategy-plan.json` in a private directory. Each report path must be new.

```powershell
$demoDir = 'C:\PrivateTradeLabData'
python -B tools/bot_rehearsal.py rehearsal --plan "$demoDir\strategy-plan.json" --output "$demoDir\plan-replay.json"
python -B tools/bot_rehearsal.py stress --plan "$demoDir\strategy-plan.json" --output "$demoDir\plan-stress.json"
python -B tools/bot_rehearsal.py outbox init --db "$demoDir\intents.sqlite3"
python -B tools/bot_rehearsal.py outbox stage --db "$demoDir\intents.sqlite3" --plan "$demoDir\strategy-plan.json" --report "$demoDir\plan-replay.json"
python -B tools/bot_rehearsal.py outbox inspect --db "$demoDir\intents.sqlite3"
python -B tools/bot_rehearsal.py outbox halt --db "$demoDir\intents.sqlite3"
```

Rehearsal and stress use synthetic data by default. A permitted local CSV with complete 15-minute sessions can be supplied with `--csv`. The recorded source fingerprint binds the normalized snapshot. Provider entitlement, data vintage and real-market performance require separate evidence.

## Verification

The 260-bar synthetic QQQ demonstration produced 14 drafts. The first stage inserted all 14. The retry inserted zero and counted 14 duplicates. Halt cancelled all 14, and recovery reproduced the 15-event journal head. The same frozen plan passed all four execution scenarios and the accompanying causality and accounting diagnostics.

The checkpoint adds 42 tests. The local public regression ran 685 tests with 684 passing and one existing Windows symlink-privilege skip. The crash test exits a subprocess after uncommitted SQLite pages reach disk and verifies that recovery restores the last committed head. A concurrent-write test accepts exactly one writer for a shared expected head. [Machine-readable evidence](../evidence/strategy_planner_checks.json)

The delivered system covers repeatable strategy planning, offline execution diagnostics and durable local intent handling. Broker dispatch, live account reconciliation and independent strategy qualification remain separate release stages. The reused v2 ML validation does not establish an edge and stays outside this pipeline.
