# Market-data PIT program: Release A merged continuation

Disposition: CHECKPOINT_READY_FOR_CONTINUATION. Release A is fully released;
Release B/C remain required engineering, not external blockers or owner-review gates.
This is a context-capacity checkpoint at the owner-preferred Release A merge boundary.
Full technical/release authorization from the attached owner directive persists.

## Exact release coordinates

- Remote and synchronized local main: `45dfc94160de95b4a1c5c7c1c08f3a8ebbee84ae`.
- Release A PR: https://github.com/tungthanhnguyen2312-wq/stock-core-private/pull/38.
- Final candidate head: `1e787e6f75a60a12f13ae52400c67842846f4052`.
- Candidate CI run: `36952305683`; all four jobs SUCCESS.
- Main CI run: `36952580770`; all four jobs SUCCESS.
- Merge tree equals the tested final candidate tree; remote main was fetched and verified.
- New continuation branch: `feature/market-data-pit-foundation-20261002`.
- Operator worktree: `C:\Projects\StockLookup\worktrees\market-data-pit-foundation-20261002`.
- New worktree started clean at the exact main SHA above. This checkpoint changes
  only state/roadmap/handoff documentation; current documentation HEAD is recorded
  by Git on that branch. No Release B/C implementation commit or PR exists yet.
- Local Producer main retains its pre-existing untracked `data/`; no reset/clean,
  force push, worktree removal or reviewed-history rewrite was used.

## Release A result

One corporate rollforward follows a valid snapshot. Verified same-civil-date success
reuses retained bytes; missing materialization recovers offline; corrupt success
does not refetch. New optional event/universe inputs are captured immutably before
downstream work. Registration consumes the explicit mapping. Completed sessions
keep actual optional locks, including absence. Retrieval/publication timestamps,
not acquisition start or directory date, must satisfy the existing 15:00 Vietnam
decision cutoff. Exact current selection can enter a new market decision only when
already known by that cutoff; the final immutable result binds that frozen selection.

Current knowledge stays separate. Existing Corporate Intelligence/R4 explanations
use the exact current context and matching universe lineage, with independent latest
supplemental evidence disabled in canonical frozen corporate consumers. The current
dashboard workspace and separate current-knowledge brief explicitly consume the
overlay. Sealed source/decision/posture identities, original brief/packet bytes and
prospective cases are unchanged. Historical compatibility receives no current overlay.
Corporate outage remains local and the injected offline canonical Daily still completes.

Validation:

- Final post-close/rollforward/current-product/offline-Daily selection: 132 passed,
  9 retained/baseline cases deselected. The repaired test-root guard also passes.
- Producer CI-equivalent before the declaration fix: 1,421 passed, 16 skipped,
  11 deselected, 30 subtests; one root-declaration guard failed. The test call was
  fixed and the guard/final affected tests passed. Final exact-head and main CI
  subsequently both passed all four jobs.
- Actual retained enrichment ran under socket/HTTP/provider guards: every counter
  zero. PR #37's 31 capture hashes and 3,216,925 bytes are unchanged; exact current
  context remains `6bc4608b7d2b3f1d9a414ddeed383e56c658baec2d6400677a6de6a0cf23e5f8`.
  Coverage: 186 observations/174 names; R4: 160 qualified explanations/153 names.
- Six retained session-operation tests pass on exact pre-release main `c96c95c`.
  The isolated worktree's old unmarked retained-fixture failures are missing private
  inputs; unrelated code was not changed. The prior handoff records the separate
  working-dates failure reproduced on exact main.
- Compile, roadmap drift, diff and single-writer checks passed. The canonical Daily
  acceptance is a hermetic injected fixture, not a manufactured live trading session.

Portable acceptance: [Release A evidence](CORPORATE_DAILY_ROLLFORWARD_RELEASE_A_ACCEPTANCE.json).
Contract: [corporate Daily](../corporate_currency_daily_rollforward_contract.md).

## Exact next atomic capability: Release B prospective continuity

Do not repeat R1–R7, PR #37 or the corporate call-graph audit. Reuse
[R7 acceptance](R7_PORTFOLIO_PIT_EXECUTION_ACCEPTANCE.json) and
[R7 input manifest](R7_RETAINED_INPUT_MANIFEST.json) once for retained source scope.

The existing market contract is `prospective_market_snapshot_contract.py`:
`build_snapshot`, `build_session_manifest`, `revision_classification`, `allowed_uses`.
Canonical post-close already calls `build_session_manifest` inside the Integrated
Decision enrichment builder. That retention currently depends on other enrichment
inputs and writes a shared session manifest. Extend this existing path into automatic
immutable per-receipt/version continuity immediately after snapshot validation, so
market evidence survives independent corporate/fundamental/valuation outages.

Retain actual ticker/exchange/board/session/source/receipt hash and known-at, OHLC,
volume, final-state/basis/allowed-use semantics and revision lineage. Keep unknown
fields explicit. Do not change original knowledge times from a later rebuild. The
existing hash-kind explicitly distinguishes canonical retained observation bytes
from provider payload bytes; do not mislabel one as the other.

The current independent-series comparison uses `zip(official, O/H/L/C)`; validate
exact four-field completeness, finite values, units, exact session and admitted
source/exchange scope before any prospective RAW agreement can qualify. Preserve
HOSE-only retained authority; no HNX/UPCoM/provider-wide generalization.

Use exact newly retained official listing/universe source observations for prospective
membership. `current_official_universe_evidence_retention.py` and
`current_official_market_universe.py` are existing retention/verification boundaries.
Old current-universe presence is not proof of active historical membership. Do not
promote ACTIVE_UNIVERSE when source status/board/time proof is absent.

Release A's selected corporate result and verified acquisition provide current event
source identities/observation times. Retain versions and absent terms honestly.
Reuse `qualified_corporate_action_factor_chain.build_factor_chain_entry` (and the
canonical corporate-action ledger), never infer terms or factors from prices.
Index dates still do not prove executed lifecycle. Missing official terms/publication
or execution evidence keeps candidates NOT_QUALIFIED.

Integrate all prospective retention into ordinary Daily with component-local receipts,
idempotence/corruption/version tests and offline acceptance. Complete bounded historical
feasibility closure, then commit/push/PR/CI/merge/sync Release B before Release C.

## Retained baseline, not new findings or promotions

- Prospective as-known price evidence: 18,514 DNSE bars/21 sessions in the existing
  scoped acceptance. Scoped prospective RAW: 6,026 cross-source HOSE bars; not
  provider-documented raw basis. R7 also inventories three later Daily manifests.
- Universe/listing PIT: ACTIVE_UNIVERSE remains unknown in the R7 matrix; current
  1,683-name denominator is not historical membership.
- Corporate/factors: three retained real candidates remain NOT_QUALIFIED; stronger
  factor-chain authority remains zero. Current corporate explanations are non-voting.
- HOSE historical raw: retained empirical scoped agreement, source basis undocumented.
  Do not reopen broad crawling; close as EMPIRICALLY_UNADJUSTED_SCOPED /
  SOURCE_BASIS_UNDOCUMENTED unless new retained explicit documentation changes it.
- HNX/UPCoM historical bulk market series: retained governance requires external
  approval/data rights. This is distinct from already-admitted current listing/event
  routes. Preserve ENGINEERING_READY / EXTERNAL_DATA_RIGHTS_REQUIRED where applicable.
- No first market-only eligible window was computed in this continuation. Do not
  report zero or a usable window before the strategy-specific eligibility adapter
  and retained inventory actually establish it. No representative replay was run.

## Release C and strategic closure still required

Reuse `vnm_shadow_backtest.py`/existing replay machinery. Add strategy-specific
MARKET_ONLY_PIT_ELIGIBILITY_V1 requirements, exact exclusions and known-at/window
checks, not a global ticker-ready boolean or full Integrated Decision PIT prerequisite.
Report the actual first contiguous eligible region, even if empty. If usable, run an
existing deterministic technical signal without tuning. Gross research is allowed
only for qualified inputs; net/execution outcomes stay unavailable without real costs.

Add adversarial later-price/volume/universe/CA/ex-date/source-correction/survivorship
tests. Produce the requested twelve-capability feasibility dossier with engineering,
bounded acquisition, rights, unavailable data, future-time, governance and economic
classification. Full historical strategic disposition has not yet been formally
adopted; assess and document PROSPECTIVE_PIT_PRIMARY /
FULL_HISTORICAL_INTEGRATED_PIT_DEFERRED if retained evidence justifies it.

## Effects and outstanding release authority

This session's source acquisitions: zero. Network activity was Git/GitHub release
control only. Production Daily/publication/deployment/broker effects: none. Historical
registry/T0/packet mutations: none. Authority promotions: none. Future ordinary Daily
now executes the merged bounded corporate path; no hidden/background job was started.
Release B/C remain authorized and require no routine owner approval. No external
blocker prevents the next engineering step.
