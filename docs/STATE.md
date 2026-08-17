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

- **P0-RECOVERY** — close the in-flight Task 160 Trades Stage-B recovery/materialization
  exception. Bounded; does not reopen general feature work.
- **P0-A** — qualified price basis + corporate-action + historical PIT authority.
  `A.1` OHLC raw-coverage completion, `A.2` corporate-action evidence scale-out, `A.3` market-wide
  PIT price reconstruction, `A.4` scoped price-basis promotion.
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

`UNIVERSAL_MARKET_DATA_LAKE_EXPANSION_V2 = COVERAGE_RECONCILED_PENDING_CLASSIFICATION` (supersedes
`PARTIAL_LIVE_BACKFILL`; tracked as P0-A.1 going forward, see `## PROGRAM PRIORITY ORDER`).

The dynamic DNSE security-master snapshot retains 3,250 distinct instruments from 3,252 declared
records. The OHLC adapter's eligible `ST/EQUITY` scope is 1,660; 1,590 `UNKNOWN_SECURITY_GROUP`
records remain retained separately and excluded without guessing. The annual 1D OHLC backfill is
now fully reconciled: **1,528 successful + 132 failed + 0 untouched = 1,660** — 0 untouched
supersedes the earlier 576-untouched figure. The 132 residual eligible failures were unclassified
(retryable vs. permanent vs. unclassified) because provider diagnostic detail had not been
retained; a bounded diagnostic-retention repair (commit
`c5f6752a6c7a3ca8d5f6d92985d583d6d6e72bb9`, "retain deterministic, bounded, redacted DNSE OHLC
failure diagnostics") landed 2026-08-17, validated by 52 relevant passing tests with no live
provider call during implementation. A separately-owned, PowerShell-launched diagnostic re-probe
(run ID `p0-a1-ohlc-v2-diagnostic-reprobe-20260817`, same source HEAD) is
`ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION` against the 132 residual failures — see
`## ACTIVE RUNTIME LANES`. This remains raw coverage/diagnostics only; it does not promote price,
volume, PIT, canonical, feature, or strategy authority.

Adjacent verified lane: `MARKET_WIDE_FOREIGN_TRADING_INGEST_V1 = COMPLETE` for one 2026-08-11
session across all 1,660 applicable instruments (1,657 success, three retained HTTP 500 failures,
zero untouched). `DNSE_INTRADAY_HISTORY_PAGINATION_CONTRACT_V1` has trades ready for one-session
market-wide raw acquisition after a source checkpoint; quotes remain `PARTIAL` pending a complete
continuation-to-terminal proof. These facts do not displace the active `P0-A.1_TERMINAL_CLASSIFICATION` gate.

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

1. OHLC V2 coverage is fully reconciled (0 untouched) but 132 retained provider failures are not
   yet classified retryable vs. permanent vs. unclassified; this is P0-A.1's current gate, pending
   the diagnostic re-probe's terminal result (see `## ACTIVE RUNTIME LANES`).
2. DNSE unknown security groups are retained but not eligible for the current `type=STOCK`
   contract; do not guess their classifications.
3. Trades has a bounded raw contract; quotes does not yet prove a full continuation-to-terminal
   chain. Neither has canonical board, quantity/volume, price-basis, or PIT authority.
4. Price basis, corporate-action semantics, session completeness, board semantics, and quantity
   units remain feature/dataset-specific semantic work, not ticker-wide acceptance gates.

## NEXT GATE

`P0-A.1_TERMINAL_CLASSIFICATION` (supersedes `MARKET_WIDE_DATA_COVERAGE_REVIEW`, which is
complete — see the reconciled 1,528/132/0 count above).

## EXACT NEXT BOUNDED ACTION

Wait for the P0-A.1 diagnostic re-probe's terminal result (do not inspect or poll it). On terminal
validation, classify the 132 residual failures retryable vs. permanent vs. unclassified from the
retained diagnostics, and close P0-A.1. Do not start P0-A.2/A.3/A.4, P0-B, or P0-C implementation
merely because A.1 is close to done — each requires its own gate check. See `## CRITICAL PATH`.

## ACTIVE RUNTIME LANES

Two PowerShell-owned, human-launched runtimes may be active. Neither is Claude-Code-managed. State
is recorded here only from repository evidence — do not treat either as terminal without a later
terminal-validation artifact, and do not inspect, poll, or interact with either runtime directly.

- **Task 160 / P0-RECOVERY** — `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`. Controlled rerun,
  source HEAD `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02` ("eliminate O(units x pages) rescan in
  Task 160 selected-page resolution"; validated pre-rerun by focused tests and a bounded
  before/after benchmark showing structural removal of the repeated-read pathology). Do not infer
  terminal success or rerun it.
- **P0-A.1 diagnostic re-probe** — `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`. Run ID
  `p0-a1-ohlc-v2-diagnostic-reprobe-20260817`, source HEAD
  `c5f6752a6c7a3ca8d5f6d92985d583d6d6e72bb9`. Purpose: capture bounded failure diagnostics for the
  132 residual eligible OHLC HTTP-400 failures. Do not treat the 132 as classified, or the run as
  succeeded, until a terminal-validation artifact says so.

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
before it is treated as supported.

## CRITICAL PATH

Ordered chain from now to the first market-wide-safe qualified analysis artifact:

1. Task 160 terminal validation / P0-RECOVERY close-out.
2. P0-A.1 terminal classification of the 132 residual OHLC failures / completion.
3. P0-A.2 corporate-action evidence scale-out (review the existing prior-art branch first).
4. P0-A.3 market-wide PIT price reconstruction.
5. P0-A.4 scoped price-basis promotion.
6. First market-wide-safe qualified analysis artifact.

P0-B and P0-C remain valid, independently-startable parallel lanes by governance (see `## PROGRAM
PRIORITY ORDER`), but execution focus stays critical-path-first (steps 1-6) unless the owner
explicitly authorizes an additional parallel lane. Do not place P1 (including the Research
Evidence Layer) or P3 ahead of this chain.

## DO NOT DO

- Do not re-open ticker-by-ticker qualification as the default workflow or open arbitrary cohorts.
- Do not require a ticker to qualify before raw ingestion.
- Do not infer missing semantic fields, units, price basis, ex-dates, or execution from labels,
  record dates, planned issuance, or plausibility.
- Do not start Strategy, Portfolio/Risk, Backtest, AI, or Dashboard expansion ahead of sufficient
  market-wide data and feature coverage.
- Do not add a provider or promote a shadow/experiment because code exists or tests pass.
- Do not automatically continue to the next milestone without owner authorization.

## MINIMUM REQUIRED READING FOR NEXT AGENT

1. `AGENTS.md` and this file.
2. [`docs/ROADMAP.md#active-ordered-workstreams`](ROADMAP.md#active-ordered-workstreams).
3. [`docs/DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition`](DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition)
   (current priority order, prior-art disposition) and
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
backlog reconciled above.
