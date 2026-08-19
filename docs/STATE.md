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

- **P0-RECOVERY** — **closed.** Task 160 Trades Stage-B and canonical Trades materialization are
  both `TERMINAL_SUCCESS_QUALITY_RESTRICTED` — see `## ACTIVE RUNTIME LANES`. Bounded; did not
  reopen general feature work.
- **P0-A** — qualified price basis + corporate-action + historical PIT authority.
  `A.1` OHLC raw-coverage completion (**complete** — 1,528/1,660 successful, 132 `PERMANENT`),
  `A.2` corporate-action evidence scale-out (**complete** — document-authority coverage and multi-event extraction integrated at commit `a7e4a1ce7e8df1c24587c25f669393a5f0265b5e`, `push = NO`),
  `A.3` market-wide PIT price reconstruction (**in progress** — `P0-A.3A` contract, `P0-A.3B` read-only architecture review, `P0-A.3C` evidence acquisition, and `P0-A.3D` governed shadow collector hardening complete locally; `P0-A.3E` Part A prospective multi-session collection is `COMPLETE_EVIDENCE_ACQUIRED` across Sessions 1–4 with no further acquisition required, while Part B event-window qualification remains `BLOCKED_PENDING_QUALIFIED_EX_DATE`), `A.4` scoped price-basis promotion. See `## CRITICAL PATH` — canonical universe
  boundary work (`P0-C.1`/`P0-C.2`) is integrated on local main before further P0-A expansion.
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

Side acquisition program: `ISOLATED_BULK_ACQUISITION_FRAMEWORK_V1 = COMPLETE_LOCAL` (branch `feature/isolated-bulk-acquisition-framework-v1`).
- Implementation PASS (9 new modules, crash-safe atomic retention, path-isolated landing under `data-landing/official-financial-filings-v1/`, 45 isolated tests passing).
- Bounded real HPG/VNM/VCB replay PASS (5 real official filings replayed from governed evidence corpus with exact SHA-256 preservation; 0 source mutations).
- Independent review PASS_WITH_MINOR with portable isolation test fixture corrective applied.
- Qualification remains strictly separate from acquisition (`qualification_state = "unknown"` unconditionally assigned).
- No production/runtime authority promotion; production DB/runtimes untouched. Active core product gate remains `P0-A.3E = ACTIVE_MULTI_SESSION_COLLECTION`.

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

`P0-A.3B` — **DNSE Prospective PIT Price Authority Architecture Review** is
**COMPLETE_READ_ONLY** with verdict **SOURCE_SEMANTICS_BLOCKED**. No current DNSE price source,
feed, or field is authoritative `RAW_AS_TRADED`; bounded REST OHLC remains
`ADJUSTED_RETROSPECTIVE`, other REST ticker/session basis remains `UNKNOWN` unless separately
qualified, and the WebSocket `ohlc_closed` shadow remains deferred, semantically unqualified, and
non-authoritative with zero real retained completed-event observations. Transport speed, first
receipt, append-only retention, and timestamp proximity do not establish price semantics.

`P0-A.3C` — **DNSE Prospective WebSocket Payload Semantic Evidence Acquisition** is
**COMPLETE_EVIDENCE_ACQUIRED**. Live evidence run
`C:\Projects\StockLookup\operations-review\p0-a3c-live-20260818-090834` retained genuine
HPG and VCB `ohlc_closed` `bc` payloads over WebSocket at resolution `1`, linked to their
collector execution IDs and verified by deterministic replay/readback. The first attempts
honestly remained `BLOCKED_NO_COMPLETED_EVENT`; no observations were fabricated. The real
payloads reconcile the documented required fields while `tradingDate` and `tradingSessionId`
remain optional/absent as observed. This is source/protocol evidence only: `RAW_AS_TRADED` and
all price-basis/PIT/registry authority remain **NOT PROMOTED**.

`P0-A.3D` — **Governed Prospective Collector Integration & Hardening** is
**COMPLETE_LOCAL_NO_PUSH** at commit `3291ed8afda3c6aba8100f77bf5c88a2915801fd`, with corrective
commit `ecb2c6c17039f123e7e8fe5b7dd53604c2893f58`. Routine `ping` keepalive previously exhausted
the semantic receive budget; the corrective fix keeps ping observable and answered but outside
semantic/content budgets, while the absolute session deadline remains bounded. Subsequent
governed A.3E capture live-validated this behavior. The tracked collector remains
`EXPERIMENT_SHADOW_ONLY`; it fails closed on requested
symbol/resolution/channel/`bc` correspondence, refuses pre-existing collector evidence output,
retains bounded non-secret control/ignored-message/timeout metadata, separates bounded control
and non-`bc` budgets, and applies a bounded total session timeout. It is not a daemon, raw lake,
provider registry, or production/PIT authority.

`P0-A.3E` — **Prospective Multi-Session / Event-Window Price-Basis Qualification** is
**PART_A_COMPLETE_EVIDENCE_ACQUIRED; PART_B_BLOCKED_PENDING_QUALIFIED_EX_DATE; NO_PRICE_BASIS_PROMOTION.**
Sessions 1 through 4 have acquired distinct, multi-session governed evidence for HPG and VCB across two distinct execution lineages (`70a7904` and `4150f02c`), retaining all sessions including partial sessions (`SESSION_PARTIAL`) where honest expected `BLOCKED_NO_COMPLETED_EVENT` outcomes occurred without transport or integrity regression. No additional prospective acquisition is required. `RAW_AS_TRADED` remains **NOT_PROMOTED**.

- **A. PROSPECTIVE_MULTI_SESSION_COLLECTION** — `COMPLETE_EVIDENCE_ACQUIRED`.
- **B. EVENT_WINDOW_PRICE_BASIS_QUALIFICATION** — `BLOCKED_PENDING_QUALIFIED_EX_DATE`.

No daemon/unattended collector, inferred ex-date, or fabricated event evidence is authorized.
`RAW_AS_TRADED_NOT_PROMOTED` and
`OFFICIAL_CLOSED_BAR_FINALITY_DOES_NOT_BY_ITSELF_PROVE_RAW_AS_TRADED` remain binding.
`NO_REVISION_OBSERVED != IMMUTABLE`; never infer an ex-date from a record date.

`P0-B.2A_B2B` — **DNSE Daily Volume Composition Reconciliation V1** is **BLOCKED** on C1–C4 candidates.
Terminal verification (1 day, 944 sessions): 60 discriminating sessions; 0 exact matches for all C1–C4
compositions; 60 `CONFLICTING`, 884 `INSUFFICIENT_DISCRIMINATION`, 0 `EXACT_RECONCILED`.
Full 40-session corpus (35,231 symbol-sessions): C1 exact=0/35231, C2 exact=2/35231, C3 exact=1/35231,
C4 exact=2/35231. Root cause: unit-scale mismatch (C1–C4 missing ×10 factor) plus composition mismatch
on C2–C4 (include boards contributing nothing to daily_v).

`P0-B.2B1` — **Scaled-G1 Candidate Validation + Residual Classification V1** is
**VALIDATED_SHADOW_SCALE_RELATION_WITH_UNRESOLVED_RESIDUALS**.
Full 40-session corpus (35,231 eligible symbol-sessions): C5 = 10 × board_G1 quantity matches
35,164/35,231 = **99.8098%** exactly. Determinism verified: two independent runs yield identical
content hash `ac5942913291c9ac8efb73d77a3b97dbb9068f111c8c6996422b66ef4e2b183d`.
Residuals (67/35,231 = 0.19%): 62 POSITIVE_DELTA_MULTIPLE_OF_100 (53 symbols), 5 NEGATIVE_DELTA_MINUS_4
(SHB, VIX only), 0 OTHER. Zero overlap with Task-160's 27 known REMAINING_FAILED units.
Scale recorded as `EMPIRICAL_CANDIDATE` only; `semantic_unit_interpretation = UNKNOWN`;
no semantic unit promotion. Canonical Trades source commit `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`
is `SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY` — provenance gap visible for promotion review.
**This does NOT equal QUALIFIED_VOLUME_COMPOSITION or QUALIFIED_LIQUIDITY_INPUTS.**
Volume authority promotion remains a separate P0-B.2D review. P0-B is NOT closed.
P0-B.2C (va/turnover) remains **DEFERRED / NOT_IMPLEMENTED**. `qualified_liquidity_inputs = False` unconditionally.

Precondition status:
- `P0-A.1` is **COMPLETE** (1,528 success + 132 `PERMANENT` = 1,660).
- `P0-A.2` is **COMPLETE** (commit `a7e4a1ce7e8df1c24587c25f669393a5f0265b5e`, `push = NO`).
- `P0-A.3A` is **COMPLETE** on local main at commit `e360adbbc801650e6ca4c7e324f9ffcf2f32f85b` (`push = NO`):
  - Deterministic PIT reconstruction contract (`pit_price_reconstruction_contract.py` + tests).
  - Mode isolation enforced: `PIT_AS_KNOWN` vs `RETROSPECTIVE_RESTATED` mechanically distinguished via explicit `pit_backtest_eligible` field; `RETROSPECTIVE_RESTATED` never achieves `pit_backtest_eligible = True`.
  - Positive existing `RAW_AS_TRADED` price-basis authority is required before any observation qualifies as `PIT_AS_KNOWN`.
  - Negative proof over real 1,660 universe: 132 `BLOCKED`, 1,528 `UNKNOWN`, 0 `pit_backtest_eligible` — zero false PIT qualification under current unpromoted DNSE price basis.
  - Cash dividend additive boundary fail-closed without fabricating share-count ledger linkage or factors.

## EXACT NEXT BOUNDED ACTION

`P0-A.3E` Part A (Prospective Multi-Session Collection) is complete (`COMPLETE_EVIDENCE_ACQUIRED`), no additional prospective acquisition is required, and Part B (`EVENT_WINDOW_PRICE_BASIS_QUALIFICATION`) remains fail-closed `BLOCKED_PENDING_QUALIFIED_EX_DATE`. `RAW_AS_TRADED` remains `NOT_PROMOTED`. `P0-B.2C` remains deferred. The exact next actionable roadmap gate is **`P0-C.3`** (field-level freshness/as-of retrofit).

## ACTIVE RUNTIME LANES

No runtime is currently active. Three PowerShell-owned, human-launched runtimes were tracked here;
all three reached terminal state on 2026-08-17 (historical, preserved below), each independently
verified read-only against its own output artifacts. None was Claude-Code-managed or re-launched.
A status below must not be trusted without checking it is still current if significant time has
passed.

- **Canonical Trades materialization / P0-RECOVERY** — `TERMINAL_SUCCESS_QUALITY_RESTRICTED` (was
  `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`; verified 2026-08-17 against
  `materialization_manifest.json` — its stored aggregate matches an independent re-sum from its
  own 40 per-session records exactly, and all 40 output Parquet files exist on disk with
  byte-exact matching sizes). Run ID `trades-canonical-materialization-v1-20260817`, source HEAD
  `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`, `rerun_behavior: MATERIALIZED`. 18,109,141 source
  records → 18,109,141 canonical rows (0 missing, 0 quarantined, 0 duplicate identities, 0
  invalid prices/quantities, 0 timestamp violations, 0 null key fields); 40 output files,
  823,751,112 bytes. The 27 Stage-B `REMAINING_FAILED` units remain structurally absent from this
  output — they were never present in the selected raw files this step consumed, not filtered at
  materialization time. One unknown board code retained across 38/40 sessions: `G3` — an
  unresolved downstream semantic restriction, not to be guessed, and not a reason to rerun
  materialization. `semantic_limitations: RAW_PRESERVING; DIRECTIONAL_SEMANTICS_NOT_CREATED;
  SHADOW_ONLY` — shadow/raw-preserving canonical authority only, no directional (buy/sell/side)
  semantics created. **P0-RECOVERY is closed.**
- **Task 160 / P0-RECOVERY Stage-B** — `TERMINAL_SUCCESS_QUALITY_RESTRICTED` (was
  `ACTIVE_RUNTIME_PENDING_TERMINAL_VALIDATION`; verified 2026-08-17 against
  `task160_run_status.json` and all four required Stage-B artifacts). Source HEAD
  `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`. 66,400 logical units reconciled: 66,373 successful,
  27 `REMAINING_FAILED` retained fail-closed (not silently success); all 40 sessions `CONSISTENT`
  (32 `QUALITY_HEALTHY`, 8 `QUALITY_DEGRADED_PROVIDER_FAILURES`); 209,193 selected-page/file
  references reconcile across artifacts; zero duplicate logical-unit IDs. The 27 retained failures
  match the prior, already owner-accepted disposition — downstream progression is allowed with
  this explicit quality restriction; do not reopen targeted repair merely to chase the 27.
  **Stage-B is closed.** Canonical Trades materialization (above) subsequently also closed
  terminal-success — **P0-RECOVERY as a whole is now closed.**
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
| Corporate-action foundation (`1183c72`→`d7b9bf3`) | `REJECT_AND_REIMPLEMENT` — reviewed 2026-08-17; reject duplicate/weaker prior-art pipeline; DO NOT rebuild current B3/B4; current-main `corporate_action_events.py` + `official_corporate_action_ledger.py` remain basis | P0-A.2 |
| Canonical instrument-master / universe-tiers (`b4e3c71`, `3d9a2ab`) | `PROMOTED_WITH_BOUNDED_PATCH` — foundation integrated to local main (commit `5ea3b6a85f734bc299c64464bf4d8452881c9116`, fast-forward, not pushed); security-group semantics subsequently qualified for ~99.6% of `UNKNOWN_SECURITY_GROUP` | P0-C.1 / P0-C.2 |
| Volume / turnover chain (`c05bec0`→`4480c3b`→`0d19e07`) | `HOLD_FOR_FUTURE_PHASE` | P0-B |
| Research Evidence / informal "C3" chain (`01941ca`→`fc22e58`→`0fe604e`→`5487e5e`) | `HOLD_FOR_FUTURE_PHASE` | P1 / legacy "Research Evidence Layer" |
| Pre-rebaseline OHLC/PIT stub chain (`504e718`, `cd05669`) | `SUPERSEDED` | — |
| OHLC bounded pilot executor (`aac16db`) | `PORT_SELECTED_PARTS` candidate | P0-A.1 / A.3 |

## P0-C.1/P0-C.2 CANONICAL UNIVERSE FOUNDATION (2026-08-17)

Prior art `b4e3c71`/`3d9a2ab` was reviewed (`P0C1_P0C2_READY_FOR_BOUNDED_PROMOTION_IMPLEMENTATION`)
and then promoted with its required bounded patch, on a dedicated worktree/branch off this file's
own prior HEAD `eebae8722793ee3a7c621d76c074af70492a1a12`: branch
`feature/canonical-universe-foundation-promotion-v1`, commit
`5ea3b6a85f734bc299c64464bf4d8452881c9116`. **This was subsequently integrated into local
`stock-core-private` main via fast-forward** (independent read-only audit result
`SAFE_TO_INTEGRATE_LOCALLY`) — `main` HEAD is `5ea3b6a85f734bc299c64464bf4d8452881c9116`. **Not
pushed to `origin`, not deployed.** Sole writing agent: Claude Code.

Ported: `canonical_instrument_reconciliation.py` (C.1), `canonical_universe_tiers.py` (C.2), both
contract docs, both existing test suites (28 tests, all still passing unmodified). Bounded patches
applied: C.1's `COMPANY_PROFILE` `instrument_class` extraction now reads from `qualified_fields`,
matching `name`/`exchange` in the same function (was previously reading an unrelated top-level
field; now covered by two direct tests). C.2's membership and ledger-event rows now carry
`instrument_class`/`exchange` as first-class fields, carried verbatim from C.1's own selected
values — no new normalization or inferred semantics. C.2's non-equity exclusion reasons are now
class-specific (`instrument_type_etf`/`_warrant`/`_right`/`_bond`/`_derivative`, aligned with
`dnse_instrument_universe.INSTRUMENT_CLASSES`) instead of one generic bucket; the `INDEX`/
`SYNTHETIC` branch is explicitly relabelled `index_or_synthetic_reserved_unqualified`
(`quality_status="unqualified"`) since no current classifier authority has ever emitted those
values. New no-network integration adapter
`tools/build_canonical_universe_from_retained_snapshot.py` wires an already-retained DNSE
security-master snapshot through C.1 then C.2, binding every output to that snapshot's own
path/`content_hash`/`snapshot_id`/`retrieved_at`; it never calls `discover_universe()`. 15 new
focused tests added (43 total); `py_compile` and `git diff --check` both clean.

**Verified against the real, already-retained 2026-08-12 DNSE security-master snapshot**
(`operations-review/dnse-market-data-lake-v2-20260812/data/market_raw_lake/universe/
5c61b853c6f806e7120c56646b2af64e241aa26e70cccd37b9ddf1288258c4d4.parquet`, manifest
`content_hash=965c4b30e003d5a1fa0f4963b102c605d8fc4485def3ccf98a153dec88a46af9`, no live DNSE call
this session):

- `MASTER_OBSERVED`: 3,250 total — exact match to this file's existing DNSE security-master fact.
- `LISTED_EQUITY_CANDIDATE`: 1,660 `INCLUDED` / 1,590 `UNKNOWN` (`instrument_type_unknown`) / 0
  `EXCLUDED` / 0 `NOT_APPLICABLE` — exact match to the existing `1,660`/`1,590` OHLC-eligible-scope
  and `UNKNOWN_SECURITY_GROUP` facts elsewhere in this file.
- `ACTIVE_UNIVERSE`: 0 `INCLUDED` / 3,250 `UNKNOWN` (1,660 `listing_status_unknown` + 1,590
  inherited `instrument_type_unknown`) / 0 `EXCLUDED`. **This is the expected, fail-closed result,
  not a defect** — no verified listing-status or exchange-label evidence source exists anywhere in
  this codebase yet (see remaining blockers below).
- Independent cross-check: this run's own C.1 artifact content-hash
  (`eb253a5a1a0601b90322265ee954bdb82f9751ab37994568c89d69a9ea16ba5d`) is byte-identical to a
  pre-existing dev-run artifact already retained at
  `operations-review/p0-c1-canonical-instrument-reconciliation-20260816/`, confirming the port
  preserved C.1's exact original behavior against the same real input.

**What this foundation does NOT establish** (explicit, not to be silently assumed later):

- `P0-C` is not complete. `P0-C.3` (field-level freshness/as-of retrofit) is not started.
- `ACTIVE_UNIVERSE` is not qualified for any instrument, including the 1,660 `EQUITY`-classified
  ones — no instrument currently has a usable listing-status or exchange-label observation
  anywhere in this codebase. This is a structural fact about available evidence, not something a
  code change alone can resolve.
- The 1,590 `UNKNOWN_SECURITY_GROUP` population remains fully unresolved and undifferentiated: no
  DNSE `securityGroupId` other than `"ST"` has ever been empirically mapped to `ETF`/`WARRANT`/
  `RIGHT`/`BOND`/`DERIVATIVE`. C.2's new class-specific reason codes exist for when that mapping is
  eventually made, not because any instrument uses them today.
- No P0-A or P0-B status changed. No ticker's research/analysis eligibility changed.
- Integrated into local main (commit `5ea3b6a85f734bc299c64464bf4d8452881c9116`, followed by semantic qualification `0f29019da83e83144f4f7f3832f054e04be66a97`, `push = NO`); this entry does not by itself authorize a push to `origin`.

**Remaining universe-semantic blockers, explicit and currently unscoped:** (1) exchange-label
mapping (DNSE `marketId` -> HOSE/HNX/UPCoM) remains unqualified market-wide — the same gap
`DECISIONS.md`'s 2026-08-11 entry already declined to guess from two data points; (2) listing/active
status has no qualified source anywhere in this codebase for any DNSE-only instrument; (3) the
1,590 `UNKNOWN_SECURITY_GROUP` population's finer classification is unresolved. None of the three
has a scoped milestone yet; each needs its own owner-authorized evidence-sourcing decision before
`ACTIVE_UNIVERSE`, `P0-C.3`, or a genuinely qualified research universe can advance. Do not treat
`P0-A.2`/`P0-B`/`P0-C.3` as automatically next merely because this foundation is implemented, and
do not treat this as authorization to source exchange-label or listing-status evidence without its
own owner decision.

## P0-C UNIVERSE SEMANTIC EVIDENCE QUALIFICATION (2026-08-17)

`P0-C_UNIVERSE_SEMANTIC_EVIDENCE_QUALIFICATION_V1` investigated the two semantic dimensions
blocking `ACTIVE_UNIVERSE` (exchange, listing/active status) plus a bounded, secondary
`UNKNOWN_SECURITY_GROUP` inventory, using only already-retained first-party DNSE evidence — no
live DNSE call this milestone. **Integrated into local `stock-core-private` main via fast-forward
(commit `0f29019da83e83144f4f7f3832f054e04be66a97`, `push = NO`).** Per-dimension result:

- **Exchange / market semantics: `UNKNOWN` (unqualified).** `marketId`/`productGrpId` were
  re-examined across three separate retained DNSE endpoints (`/market/instruments`,
  `/price/{symbol}/secdef`, `/market/trading-session` — the 2026-08-10 qualification pass,
  `operations-review/dnse-market-data-qualification-20260810/probe_results.json`). Every endpoint
  retains `marketId` as an opaque code (`STO`/`UPX`/`HCX`/`STX`/`DVX`) with no accompanying
  human-readable label anywhere. No first-party DNSE documentation or SDK spec is retained
  anywhere in this workspace. The only available corroboration remains 2-3 familiar tickers per
  code (e.g. `STO`↔HPG/VNM, `UPX`↔QNS) — explicitly insufficient under this project's own doctrine
  (a sample correlation is not a documented mapping; `DECISIONS.md`'s 2026-08-11 entry already
  declined this exact inference). **No mapping implemented.** `exchange` stays
  `provider_raw_only_mapping_unknown` for every marketId code, confirmed by direct test.
- **Listing / active-status semantics: `UNKNOWN` (unqualified), candidate fields identified.**
  `/price/{symbol}/secdef` (not currently integrated into any bulk pipeline) carries genuinely
  promising per-symbol fields — `finalTradeDate`, `symbolAdminStatusCode`,
  `symbolTradingMethodStatusCode`, `symbolTradingSanctionStatusCode`, `securityStatus` — but the
  only retained evidence (HPG/VNM/QNS, 2026-08-10) shows all three in an identical
  all-normal/all-null state (`symbolAdminStatusCode="NRM"`, `securityStatus="NO_HALT"`,
  `finalTradeDate=null`), with **zero contrasting (suspended/delisted) example** to confirm what
  those fields actually distinguish. A live probe was deliberately not attempted: no
  reliably-evidenced delisted/suspended DNSE symbol exists in this workspace to test against, and
  `security_definition` is a per-symbol endpoint — even a fully qualified semantic would still
  need its own market-wide bulk-ingestion milestone (1,660 individual calls) before it could
  populate `ACTIVE_UNIVERSE` at all, which is out of this milestone's bounded scope. **No mapping
  implemented.** `listing_status` stays `UNKNOWN` for every instrument.
- **`UNKNOWN_SECURITY_GROUP` (secondary, bounded inventory): `PARTIAL` — ~99.6% resolved.** The
  1,590-record population partitions exhaustively by raw `securityGroupId`: `EW`=1,346,
  `BS`=203, `EF`=21, `FU`=8, `MF`=6, and 6 with no code at all. Direct inspection of every
  populated `name` field (not sampled) found unanimous first-party evidence for four codes —
  `EW`→`WARRANT` (697/697 named records begin "Chứng quyền"), `BS`→`BOND` (~57/67 begin "Trái
  phiếu", remainder consistent), `EF`→`ETF` (20/21 explicitly contain "ETF"), `FU`→`DERIVATIVE`
  (8/8 begin "HĐTL", independently corroborated by `symbol_type_raw`) — plus all 6 no-code records
  individually confirmed `→INDEX` ("Chỉ số ..." matching known index names exactly). **`MF` (6
  records) was deliberately left `UNKNOWN`**: its own name evidence mixes a generic "Quỹ đầu tư"
  phrase with "Quỹ ETF" phrasing for what should be one consistent class — evidence against
  qualification, not for it. New module `dnse_security_group_semantics.py`
  (`dnse_security_group_semantics/v1`) implements this as a strictly additive refinement,
  never modifying `dnse_instrument_universe.py`'s own `"ST"`→`EQUITY` classification. See
  `docs/dnse_security_group_semantics_contract.md` for the full evidence record.

**Re-run against the same real 2026-08-12 snapshot** (`content_hash=965c4b30...`):

| Tier | Before (foundation only) | After (semantic qualification) |
| --- | --- | --- |
| `MASTER_OBSERVED` | 3,250 total | 3,250 total (unchanged) |
| `LISTED_EQUITY_CANDIDATE` | 1,660 INCLUDED / 1,590 UNKNOWN / 0 EXCLUDED / 0 NOT_APPLICABLE | 1,660 INCLUDED / 6 UNKNOWN / 1,578 EXCLUDED / 6 NOT_APPLICABLE |
| `ACTIVE_UNIVERSE` | 0 INCLUDED / 3,250 UNKNOWN / 0 EXCLUDED / 0 NOT_APPLICABLE | 0 INCLUDED / 1,666 UNKNOWN / 1,578 EXCLUDED / 6 NOT_APPLICABLE |

`ACTIVE_UNIVERSE.included` is unchanged at **0** — this is the correct, expected PASS condition,
not a shortfall: security-group evidence says nothing about listing/active status, and correctly
does not resolve it. The 1,660 `EQUITY`-classified instruments still show exactly
`listing_status_unknown` in `ACTIVE_UNIVERSE`, byte-identical to before this milestone; only the
population *below* `LISTED_EQUITY_CANDIDATE` changed (1,590 UNKNOWN narrowed to 1,578 EXCLUDED + 6
NOT_APPLICABLE + 6 still-UNKNOWN). One qualified dimension did not fabricate another, confirmed by
direct test (`test_qualified_instrument_class_never_fabricates_listing_status`).

**Remaining blockers, explicit and still unscoped:** exchange-label mapping (no path forward
without genuine DNSE documentation, which does not exist in this workspace); listing/active-status
evidence (candidate fields identified at `/price/{symbol}/secdef`, but unconfirmed without a
contrasting example, and would need its own market-wide bulk-ingestion milestone regardless); the
6 `MF`-coded records. None has a scoped milestone. Do not start P0-A.2, P0-B, HPG work, or P1 as a
consequence of this entry.

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

Task 160 Stage-B, P0-A.1, and canonical Trades materialization are all closed — P0-RECOVERY is
closed (see `## ACTIVE RUNTIME LANES`). Current execution policy remains
**market-wide/full-universe data foundation first**, not single-ticker artifact expansion.
Updated ordered chain:

1. `CANONICAL_TRADES_MATERIALIZATION` — closes P0-RECOVERY. **Complete**
   (`TERMINAL_SUCCESS_QUALITY_RESTRICTED`).
2. P0-RECOVERY close. **Complete.**
3. Establish/reconcile the canonical market-wide universe boundary: `P0-C.1` instrument-master
   reconciliation, `P0-C.2` universe-tier hierarchy/exclusion ledger. **Foundation integrated to
   local main, security-group semantics qualified (~99.6%), exchange and listing/active status
   investigated and found genuinely unqualified.** `ACTIVE_UNIVERSE` still not qualified for any
   instrument — see `## P0-C.1/P0-C.2 CANONICAL UNIVERSE FOUNDATION` and
   `## P0-C UNIVERSE SEMANTIC EVIDENCE QUALIFICATION` for exact scope and remaining blockers.
4. Continue market-wide data authority over that canonical universe: `P0-A.2` corporate-action
   evidence scale-out and `P0-A.3` market-wide PIT reconstruction. `P0-A.3B` is closed
   `SOURCE_SEMANTICS_BLOCKED`; `P0-A.3C` evidence acquisition and `P0-A.3D` governed shadow
   hardening are complete locally. `P0-A.3E` Part A is complete (`COMPLETE_EVIDENCE_ACQUIRED`, Sessions 1–4 retained, no more prospective acquisition required); Part B event-window qualification remains `BLOCKED_PENDING_QUALIFIED_EX_DATE`; `RAW_AS_TRADED` remains `NOT_PROMOTED`; `P0-A.4` scoped price-basis promotion remains deferred; `P0-B.2B1` shadow scale relation validated with unresolved residuals and B.2C deferred.
5. `P0-C.3` field-level freshness/as-of retrofit, as required for qualified market-wide
   consumption.
6. First market-wide deterministic analysis/research artifact, after the necessary P0-A/P0-B/P0-C
   gates above pass.

This numbered sequence is current execution *focus*, not a rewritten dependency graph: `P0-A`,
`P0-B`, and `P0-C` remain independent, parallelizable lanes by governance (see `## PROGRAM
PRIORITY ORDER`) once each is actually started. `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` is
withdrawn from this immediate chain — see `## BOUNDED ANALYSIS OUTPUT CANDIDATE`; it remains a
documented future validation candidate, not the next milestone, and is not started now. Do not
place P1 (including the Research Evidence Layer) or P3 ahead of this chain. Step 3 (P0-C.1/C.2
foundation + semantic-evidence qualification) is complete on local main, not pushed; opening step 4
or beyond, pushing to `origin`, or sourcing new exchange-label/listing-status evidence, each
requires its own explicit owner authorization — see `## P0-C.1/P0-C.2 CANONICAL UNIVERSE
FOUNDATION` and `## P0-C UNIVERSE SEMANTIC EVIDENCE QUALIFICATION`.

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
- Do not rebuild B3/B4 corporate-action contracts during P0-A.2 — prior art `1183c72`→`d7b9bf3` was rejected (`REJECT_AND_REIMPLEMENT`); current-main `corporate_action_events.py` and `official_corporate_action_ledger.py` remain the authoritative implementation basis.
- Do not treat `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` as the next milestone ahead of
  market-wide universe/data foundation (`P0-C.1`/`P0-C.2` review, `P0-A.2`-`P0-A.4`, `P0-B`).
- Do not push local main to `origin`, treat `ACTIVE_UNIVERSE` as qualified for any instrument, or
  treat exchange/listing-status as resolved, merely because P0-C.1/C.2 foundation and security-group
  semantic qualification are both implemented — exchange and listing/active status were
  specifically investigated and found genuinely unqualified, not merely unattempted. See
  `## P0-C.1/P0-C.2 CANONICAL UNIVERSE FOUNDATION` and
  `## P0-C UNIVERSE SEMANTIC EVIDENCE QUALIFICATION`.
- Do not source new exchange-label or listing-status evidence (including a live DNSE probe) or
  attempt to classify the remaining 6 `MF`-coded `UNKNOWN_SECURITY_GROUP` records without its own
  explicit owner-authorized scope.

## MINIMUM REQUIRED READING FOR NEXT AGENT

1. `AGENTS.md` and this file.
2. [`docs/ROADMAP.md#active-ordered-workstreams`](ROADMAP.md#active-ordered-workstreams).
3. [`docs/DECISIONS.md#2026-08-17---p0-a2-corporate-action-multi-event-extraction-integrated-to-local-main-p0-a2-complete`](DECISIONS.md#2026-08-17---p0-a2-corporate-action-multi-event-extraction-integrated-to-local-main-p0-a2-complete)
   (P0-A.2 complete — multi-event extraction integrated to local main),
   [`docs/DECISIONS.md#2026-08-17---p0-a2-corporate-action-document-authority-coverage-extension-integrated-to-local-main`](DECISIONS.md#2026-08-17---p0-a2-corporate-action-document-authority-coverage-extension-integrated-to-local-main)
   (P0-A.2 authority extension integrated to local main),
   [`docs/DECISIONS.md#2026-08-17---p0-a2-corporate-action-prior-art-review-reject_and_reimplement`](DECISIONS.md#2026-08-17---p0-a2-corporate-action-prior-art-review-reject_and_reimplement)
   (P0-A.2 prior art review: REJECT_AND_REIMPLEMENT, current-main B3/B4 basis),
   [`docs/DECISIONS.md#2026-08-17---p0-recovery-closed-canonical-trades-materialization-terminal-success`](DECISIONS.md#2026-08-17---p0-recovery-closed-canonical-trades-materialization-terminal-success)
   (P0-RECOVERY closed — canonical Trades materialization terminal result),
   [`docs/DECISIONS.md#2026-08-17---critical-path-revision-market-wide-universe-foundation-before-hpg`](DECISIONS.md#2026-08-17---critical-path-revision-market-wide-universe-foundation-before-hpg)
   (critical-path revision — market-wide foundation before HPG),
   [`docs/DECISIONS.md#2026-08-17---terminal-closure-task-160-stage-b-and-p0-a1-ohlc-coverage`](DECISIONS.md#2026-08-17---terminal-closure-task-160-stage-b-and-p0-a1-ohlc-coverage)
   (Task 160 Stage-B and P0-A.1 terminal results),
   [`docs/DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition`](DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition)
   (current priority order, prior-art disposition),
   [`docs/DECISIONS.md#2026-08-17---p0-c1-and-p0-c2-canonical-universe-foundation-implemented-local-worktree-only`](DECISIONS.md#2026-08-17---p0-c1-and-p0-c2-canonical-universe-foundation-implemented-local-worktree-only)
   (P0-C.1/P0-C.2 foundation implemented, verified reconciliation, remaining blockers),
   [`docs/DECISIONS.md#2026-08-17---p0-c-universe-semantic-evidence-qualification`](DECISIONS.md#2026-08-17---p0-c-universe-semantic-evidence-qualification)
   (security-group ~99.6% resolved; exchange and listing status investigated and found
   unqualified), and
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
