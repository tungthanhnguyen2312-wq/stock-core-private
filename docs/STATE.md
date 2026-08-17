# Stock Lookup — operational state

> **Current operational entrypoint.** Read this file in full before a normal bounded milestone.
> It is a compact cached truth, not a run log. Historical evidence, handoffs, and superseded
> milestones remain preserved in `docs/ROADMAP.md`, `docs/DECISIONS.md`, ADRs, and
> `operations-review/`; they are reference-only unless this file directs otherwise.

## CURRENT PROGRAM

**UNIVERSAL MARKET DATA & FEATURE FOUNDATION V1**

Target architecture:

`DYNAMIC MARKET UNIVERSE → MARKET-WIDE RAW INGESTION → QUALITY / CANONICALIZATION / SEMANTICS / PIT → VECTORIZED FEATURE STORE → FEATURE-LEVEL ELIGIBILITY → POLYMORPHIC STRATEGY ENGINES → PORTFOLIO / RISK / LEVERAGE → AI RESEARCH → DASHBOARD / HUMAN DECISION`

## PROGRAM PRIORITY ORDER (2026-08-17 rebaseline)

Binding execution sequence:

`P0-RECOVERY → P0-A → P0-B → P0-C → P1 → P2 → P3`

- **P0-RECOVERY** — Task 160 Trades Stage-B recovery is closed
  (`TERMINAL_SUCCESS_QUALITY_RESTRICTED`); the remaining, still-open step is canonical Trades
  materialization. Bounded; does not reopen general feature work.
- **P0-A** — qualified price basis + corporate-action + historical PIT authority.
  `A.1` OHLC raw-coverage completion (**complete** — 1,528/1,660 successful, 132 `PERMANENT`),
  `A.2` corporate-action evidence scale-out (not started), `A.3` market-wide PIT price
  reconstruction, `A.4` scoped price-basis promotion. See `## CRITICAL PATH` — canonical universe
  boundary work (`P0-C.1`/`P0-C.2`) is reviewed before further P0-A expansion.
- **P0-B** — qualified volume/liquidity basis + market-wide turnover.
- **P0-C** — canonical market universe + exclusion ledger + freshness semantics. `C.1`
  instrument-master reconciliation, `C.2` universe-tier hierarchy/exclusion ledger, `C.3`
  field-level freshness/as-of retrofit.
- **P1** — DNSE foreign-flow value scale-out; universal feature-authority/store normalization; the
  *Research Evidence Layer* (see `## CANONICAL ROADMAP IDS`); market-internals/regime.
- **P2** — sector normalization; factor attribution; official multi-period fundamental/valuation
  foundation; operational robustness.
- **P3** — return/risk, calibrated scenarios, portfolio sizing, historical backtest/alpha
  validation. Fail-closed until P0-A and P0-B pass.

`P0-A`, `P0-B`, and `P0-C` are independent, parallelizable lanes once each is actually started —
none sit idle behind Task 160 or behind each other. **This is not authorization to start all of
them at once — execution focus stays critical-path-first** (see `## CRITICAL PATH`); parallel-safe
is not the same as "start now."

This order supersedes `MARKET-WIDE DATA EXPANSION` (below) as the **program-sequencing** frame
only. That section's technical facts (DNSE security-master snapshot, OHLC checkpoint mechanism,
foreign-trading V1 completion) remain valid and now feed specific P0-A/B/C sub-milestones; they
are not discarded. Full rationale: `docs/DECISIONS.md` (2026-08-17 entry).

## CURRENT DEVELOPMENT PRIORITY

**MARKET-WIDE DATA EXPANSION.** Optimize **coverage × provenance × restartability × reusable
dataset contracts**, not the number of individually qualified securities. DNSE/Livespeed is the
current market-data direction. Do not add EODHD, FiinGroup, FiinRep, or another provider without
an explicit owner decision; EODHD remains `REJECTED_BY_OWNER`.

## ACTIVE LANE / MILESTONE

`UNIVERSAL_MARKET_DATA_LAKE_EXPANSION_V2 = P0-A.1_COMPLETE` (supersedes
`COVERAGE_RECONCILED_PENDING_CLASSIFICATION` and `PARTIAL_LIVE_BACKFILL`; P0-A.1 is closed, see
`## PROGRAM PRIORITY ORDER`).

The dynamic DNSE security-master snapshot retains 3,250 distinct instruments from 3,252 declared
records. The OHLC adapter's eligible `ST/EQUITY` scope is 1,660; 1,590 `UNKNOWN_SECURITY_GROUP`
records remain retained separately and excluded without guessing. The annual 1D OHLC backfill is
fully reconciled and classified: **1,528 successful + 132 `PERMANENT` + 0 retryable + 0
unclassified + 0 untouched = 1,660** (92.05% successful coverage). All 132 residual eligible
failures carry the same structured DNSE provider diagnostic — HTTP 400,
`diagnostic_source=json_body`, `provider_error_code=BAD_REQUEST`,
`provider_error_message="invalid symbol"` — reproduced identically across 3-4 attempts per unit
over 2026-08-12 through 2026-08-17. This is retained diagnostic evidence, not an inference from a
bare HTTP 400: it supports `PERMANENT` (the exact current request/symbol combination should not be
blindly retried), not any broader claim about why DNSE considers the symbols invalid, and does not
reclassify them into `UNKNOWN_SECURITY_GROUP`. Diagnostic-retention source commit
`c5f6752a6c7a3ca8d5f6d92985d583d6d6e72bb9` ("retain deterministic, bounded, redacted DNSE OHLC
failure diagnostics"); the terminal diagnostic re-probe (run ID
`p0-a1-ohlc-v2-diagnostic-reprobe-20260817`, same source HEAD) reached terminal state on
2026-08-17 with the classification above. **P0-A.1 is closed.** Do not blindly reprobe the 132
again absent new evidence or a changed provider contract/request basis. This remains raw
coverage/diagnostics only; it does not promote price, volume, PIT, canonical, feature, or strategy
authority.

Adjacent verified lane: `MARKET_WIDE_FOREIGN_TRADING_INGEST_V1 = COMPLETE` for one 2026-08-11
session across all 1,660 applicable instruments (1,657 success, three retained HTTP 500 failures,
zero untouched). `DNSE_INTRADAY_HISTORY_PAGINATION_CONTRACT_V1` has trades ready for one-session
market-wide raw acquisition after a source checkpoint; quotes remain `PARTIAL` pending a complete
continuation-to-terminal proof.

## CURRENT VERIFIED STATE

- Raw ingestion is ingestion-first: immutable payload, request identity, source/provider,
  retrieval timestamp, hash, schema/version, pagination metadata, checkpoint, manifest, and
  replay/audit lineage are required.
- `UNKNOWN ≠ REJECTED`: retain raw data and provenance; mark unknown/unqualified semantics; fail
  closed only for the dependent feature or use.
- DNSE daily OHLC price basis is `UNKNOWN` outside two narrow historical regression windows. Do
  not infer a provider-wide, exchange-wide, ticker-history-wide, or action-type verdict.
- The historical fixed ticker cohorts (including HPG/VCB/VNM) are golden/regression and bounded
  provider-behavior evidence, not the production universe or default work queue.
- Generic valuation, raw/PIT returns, backtesting, sizing, execution, and portfolio use remain
  fail-closed where their required semantics are not qualified.

## CURRENT BLOCKERS

1. OHLC V2 coverage is fully reconciled and classified (1,528 success + 132 `PERMANENT` + 0
   untouched = 1,660; 92.05% successful). The 132 `PERMANENT` failures are a closed, accepted
   coverage ceiling for this universe/date-range as currently requested, not a pending
   classification gate — do not blindly reprobe them without new evidence.
2. DNSE unknown security groups are retained but not eligible for the current `type=STOCK`
   contract; do not guess their classifications.
3. Trades has a bounded raw contract; quotes does not yet prove a full continuation-to-terminal
   chain. Neither has canonical board, quantity/volume, price-basis, or PIT authority.
4. Price basis, corporate-action semantics, session completeness, board semantics, and quantity
   units remain feature/dataset-specific semantic work, not ticker-wide acceptance gates.

## NEXT GATE

`CANONICAL_TRADES_MATERIALIZATION` (P0-RECOVERY's remaining step; supersedes
`P0-A.1_TERMINAL_CLASSIFICATION`, which is complete — see `## ACTIVE LANE / MILESTONE`). P0-A.1 is
closed; it is not the active gate.

## EXACT NEXT BOUNDED ACTION

P0-A.1 is closed (see `## ACTIVE LANE / MILESTONE`). Task 160 Stage-B is terminal-validated and
closed (`TERMINAL_SUCCESS_QUALITY_RESTRICTED`; see `## ACTIVE RUNTIME LANES`); the remaining
P0-RECOVERY gate is `CANONICAL_TRADES_MATERIALIZATION`, owner-gated like any authority-affecting
action. Do not start P0-A.2/A.3/A.4, P0-B, or P0-C implementation, and do not start
`HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION`, merely because P0-A.1 is done or P0-RECOVERY is close
— each requires its own gate check and, for materialization, explicit owner authorization. See
`## CRITICAL PATH`.

## ACTIVE RUNTIME LANES

Two PowerShell-owned, human-launched runtimes were tracked here. Neither was Claude-Code-managed
or re-launched. Both reached a terminal state on 2026-08-17, independently verified read-only
against their own output artifacts — a status below must not be trusted without checking it is
still current if significant time has passed.

- **Task 160 / P0-RECOVERY Stage-B** — `TERMINAL_SUCCESS_QUALITY_RESTRICTED` (was
  `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`; verified 2026-08-17 against
  `task160_run_status.json` and all four required Stage-B artifacts). Source HEAD
  `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`. 66,400 logical units reconciled: 66,373 successful,
  27 `REMAINING_FAILED` retained fail-closed (not silently success); all 40 sessions `CONSISTENT`
  (32 `QUALITY_HEALTHY`, 8 `QUALITY_DEGRADED_PROVIDER_FAILURES`); 209,193 selected-page/file
  references reconcile across artifacts; zero duplicate logical-unit IDs. The 27 retained failures
  match the prior, already owner-accepted disposition — downstream progression is allowed with
  this explicit quality restriction; do not reopen targeted repair merely to chase the 27.
  **Stage-B is closed.** P0-RECOVERY as a whole remains open pending
  `CANONICAL_TRADES_MATERIALIZATION` (see `## NEXT GATE`) — do not treat P0-RECOVERY itself as
  complete.
- **P0-A.1 diagnostic re-probe** — `P0_A1_COMPLETE` (was `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`;
  verified 2026-08-17 against the manifest, checkpoint, and coverage-report artifacts). Run ID
  `p0-a1-ohlc-v2-diagnostic-reprobe-20260817`, source HEAD
  `c5f6752a6c7a3ca8d5f6d92985d583d6d6e72bb9`. All 132 residual eligible OHLC failures are
  explicitly classified `PERMANENT` from retained diagnostic evidence (see
  `## ACTIVE LANE / MILESTONE`); 0 retryable, 0 unclassified, 0 untouched. Further blind reprobes
  of these 132 are not authorized absent new evidence or a changed provider contract/request
  basis.

**Executor boundary:** Claude Code performs architecture/correctness/documentation review; Codex
performs bounded implementation, tests, and local code changes; long-running compute and any live
DNSE acquisition is PowerShell/human-launched only — no AI agent owns a live runtime. After a
runtime reaches a terminal state, AI's role is read-only validation, forensic analysis, and
next-step preparation, not re-launching.

## CANONICAL ROADMAP IDS

Canonical current IDs: `P0-RECOVERY`; `P0-A` (`A.1`-`A.4`); `P0-B`; `P0-C` (`C.1`-`C.3`); `P1`;
`P2`; `P3` — see `## PROGRAM PRIORITY ORDER` above and `docs/ROADMAP.md` for full detail.

`docs/ROADMAP.md` separately retains an older, pre-P0 lettered narrative ("A. Market Data
Foundation", "B. Universal Feature Foundation", "C. Research Evidence Layer") for historical
continuity. Its **"C" is not `P0-C`** — that legacy section is P1-scoped research-packet-
generation work; `P0-C` is canonical-universe/freshness work, an unrelated scope.

Informal labels `C3C1`, `C3C2`, `C3C2H`, `C3C3`, `C3C4` seen in local branch/worktree names refer
to the **legacy "C. Research Evidence Layer"**, not `P0-C`. They are **not canonical roadmap IDs**
and must not be used in new work — use the IDs above.

## PRIOR-ART BRANCHES (2026-08-17 audit)

Real, tested code exists in several isolated, un-merged, un-pushed local worktrees, built after
the 2026-08-16 rebaseline but never reconciled back into authority docs before this entry. None of
these is current architecture authority; each requires its own review before promotion, merge,
cherry-pick, or extension. Full rationale: `docs/DECISIONS.md` (2026-08-17 entry).

| Branch family | Disposition | Roadmap relevance |
| --- | --- | --- |
| Corporate-action foundation (`1183c72`→`d7b9bf3`) | `PRIOR_ART_REVIEWABLE` / `REVIEW_FOR_PROMOTION` | P0-A.2 |
| Canonical instrument-master / universe-tiers (`b4e3c71`, `3d9a2ab`) | `PRIOR_ART_REVIEWABLE` / `REVIEW_FOR_PROMOTION` | P0-C.1 / P0-C.2 |
| Volume / turnover chain (`c05bec0`→`4480c3b`→`0d19e07`) | `HOLD_FOR_FUTURE_PHASE` | P0-B |
| Research Evidence / informal "C3" chain (`01941ca`→`fc22e58`→`0fe604e`→`5487e5e`) | `HOLD_FOR_FUTURE_PHASE` | P1 / legacy "Research Evidence Layer" |
| Pre-rebaseline OHLC/PIT stub chain (`504e718`, `cd05669`) | `SUPERSEDED` | — |
| OHLC bounded pilot executor (`aac16db`) | `PORT_SELECTED_PARTS` candidate | P0-A.1 / A.3 |

## BOUNDED ANALYSIS OUTPUT CANDIDATE

A bounded, HPG-only research artifact appears possible today from already-qualified, current-
session/non-PIT inputs (OHLC price-basis regression proof, current-state price/risk analytics,
current-state beta/correlation, Pillar-B official corporate-action evidence, combined with the
existing deterministic `analysis_lane_eligibility.py` gate). This is a
`BOUNDED_ANALYSIS_OUTPUT_CANDIDATE`, not a current supported output: it has not been separately
verified end-to-end, must use only already-qualified HPG-scoped inputs, and must not imply
market-wide or historical-PIT authority. A separate bounded verification milestone is required
before it is treated as supported. **It is a deferred future validation candidate, not on the
current critical path** (see `## CRITICAL PATH`) — market-wide/full-universe data foundation is
the current priority ahead of any single-ticker artifact.

## CRITICAL PATH

Task 160 Stage-B and P0-A.1 are both closed (see `## ACTIVE RUNTIME LANES`). Current execution
policy is **market-wide/full-universe data foundation first**, not single-ticker artifact
expansion. Updated ordered chain:

1. `CANONICAL_TRADES_MATERIALIZATION` — closes P0-RECOVERY. Owner-gated; not started.
2. P0-RECOVERY close.
3. Establish/reconcile the canonical market-wide universe boundary: `P0-C.1` instrument-master
   reconciliation, `P0-C.2` universe-tier hierarchy/exclusion ledger. Reviewable prior art exists
   (`b4e3c71`, `3d9a2ab`, both `PRIOR_ART_REVIEWABLE`/`REVIEW_FOR_PROMOTION` — see
   `## PRIOR-ART BRANCHES`); this is the next bounded implementation decision after P0-RECOVERY
   closes, not an authorization to promote it now.
4. Continue market-wide data authority over that canonical universe: `P0-A.2` corporate-action
   evidence scale-out, `P0-A.3` market-wide PIT price reconstruction, `P0-A.4` scoped price-basis
   promotion, `P0-B` qualified volume/liquidity/turnover basis.
5. `P0-C.3` field-level freshness/as-of retrofit, as required for qualified market-wide
   consumption.
6. First market-wide deterministic analysis/research artifact, after the necessary P0-A/P0-B/P0-C
   gates above pass.

This numbered sequence is current execution *focus*, not a rewritten dependency graph: `P0-A`,
`P0-B`, and `P0-C` remain independent, parallelizable lanes by governance (see `## PROGRAM
PRIORITY ORDER`) once each is actually started. `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` is
withdrawn from this immediate chain — see `## BOUNDED ANALYSIS OUTPUT CANDIDATE`; it remains a
documented future validation candidate, not the next milestone, and is not started now. Do not
place P1 (including the Research Evidence Layer) or P3 ahead of this chain. Opening any step
beyond materialization requires its own explicit owner authorization.

## DO NOT DO

- Do not re-open ticker-by-ticker qualification as the default workflow or open arbitrary cohorts.
- Do not require a ticker to qualify before raw ingestion.
- Do not infer missing semantic fields, units, price basis, ex-dates, or execution from labels,
  record dates, planned issuance, or plausibility.
- Do not start Strategy, Portfolio/Risk, Backtest, AI, or Dashboard expansion ahead of sufficient
  market-wide data and feature coverage.
- Do not add a provider or promote a shadow/experiment because code exists or tests pass.
- Do not automatically continue to the next milestone without owner authorization.
- Do not blindly reprobe the 132 `PERMANENT` P0-A.1 OHLC failures without new evidence or a
  changed provider contract/request basis.
- Do not start P0-A.2 while P0-RECOVERY's canonical Trades materialization remains outstanding.
- Do not treat `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` as the next milestone ahead of
  market-wide universe/data foundation (`P0-C.1`/`P0-C.2` review, `P0-A.2`-`P0-A.4`, `P0-B`).

## MINIMUM REQUIRED READING FOR NEXT AGENT

1. `AGENTS.md` and this file.
2. [`docs/ROADMAP.md#active-ordered-workstreams`](ROADMAP.md#active-ordered-workstreams).
3. [`docs/DECISIONS.md#2026-08-17---critical-path-revision-market-wide-universe-foundation-before-hpg`](DECISIONS.md#2026-08-17---critical-path-revision-market-wide-universe-foundation-before-hpg)
   (critical-path revision — market-wide foundation before HPG),
   [`docs/DECISIONS.md#2026-08-17---terminal-closure-task-160-stage-b-and-p0-a1-ohlc-coverage`](DECISIONS.md#2026-08-17---terminal-closure-task-160-stage-b-and-p0-a1-ohlc-coverage)
   (Task 160 Stage-B and P0-A.1 terminal results),
   [`docs/DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition`](DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition)
   (current priority order, prior-art disposition), and
   [`docs/DECISIONS.md#2026-08-12---one-time-governance-rebaseline`](DECISIONS.md#2026-08-12---one-time-governance-rebaseline)
   (retained technical facts).
4. Directly relevant raw-lake contracts, collector code, tests, manifests, and checkpoints for
   the named milestone.

Read [`docs/AI_RULES.md`](AI_RULES.md) in full only when the milestone changes AI authority,
feature eligibility, semantic/PIT policy, or a source/capability authority. Read the full
authority set only when an `AGENTS.md` full-refresh trigger applies.

## Current authority boundaries

- Feature eligibility replaces global ticker qualification. A feature must carry its value,
  status, method, quality, provenance, freshness, PIT status, price basis, blockers, and lineage.
  A strategy declares required features and accepted statuses, then fails closed per dependency.
- Raw lake and analytical core are distinct. The analytical target is canonical columnar
  Parquet/Arrow-compatible data and vectorized Polars-oriented computation; do not make
  ticker-by-ticker loops the production computation architecture where vectorization is viable.
- AI may research, extract candidate facts, explain deterministic results, and provide a
  counter-thesis. It may not invent facts, convert `UNKNOWN` to qualified, fabricate target
  prices/probabilities, or override deterministic risk gates.

## Authority lifecycle

`IDEA / PROPOSAL → EXPERIMENT / SHADOW → VALIDATED → PROMOTION REVIEW → AUTHORITATIVE`

Other terminal/intermediate states: `BLOCKED`, `DEFERRED`, `REJECTED`, `SUPERSEDED`.
Code, tests, commits, pushes, and agent recommendations are not authority by themselves; owner
approval is required for an authority promotion. A milestone that changes architecture, roadmap
state, or authority is not closed merely because its code/tests/commit exist — closure requires
the corresponding `STATE.md`/`ROADMAP.md`/`DECISIONS.md` update, in the same session or an
explicit dedicated follow-up. Unenforced, this is exactly what produced the 2026-08-17 prior-art
backlog reconciled above. **Operating lifecycle per milestone:** document current gate → execute
→ terminal validate → update authority/state → local commit → next milestone. Do not let
implementation outrun this file.
