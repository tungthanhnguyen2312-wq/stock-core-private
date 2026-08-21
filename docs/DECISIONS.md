# Decisions & Architectural Decision Records

> **Authoritative Decision Surface.**
> This document maintains active and recent architectural decisions.
> Historical decisions are preserved in:
> - [`docs/archive/decisions/decisions-2026-08-01-to-2026-08-16.md`](archive/decisions/decisions-2026-08-01-to-2026-08-16.md) (August 1–16, 2026: P0 recovery, corporate actions, data lake v2)
> - [`docs/archive/decisions/decisions-2026-07-historical.md`](archive/decisions/decisions-2026-07-historical.md) (July – early August 2026: initial foundations, entity taxonomy, EODHD closure)

---

## Active & Recent Decision Records (2026-08-20 to Present)

## 2026-08-21 - Prospective Research Cohort Diagnostics V1

`PROSPECTIVE_RESEARCH_COHORT_DIAGNOSTICS_V1 = READY_LOCAL` (`prospective_research_cohort_diagnostics.py`, `run_prospective_research_cohort_diagnostics.py`, `tests/test_prospective_research_cohort_diagnostics.py`, `push = NO`).

1. The first deterministic cohort diagnostics engine over the prospective learning ledger maps 1,047 prospective observations across two retained research sessions (2026-08-20 and 2026-08-21) to 87 versioned cohort summaries across 10 discovered descriptor dimensions (overall, attention_descriptor, setup_classification, queue_membership, downside_context, price_structure_context, market_regime, relative_classification_authority, evidence_authority, thesis_continuity) and 3 horizons (H1, H3, H5).
2. The real single observed H1 transition (2026-08-20 → 2026-08-21: 521 observed, 2 missing) is explicitly classified as `OBSERVED_IMMATURE_SAMPLE` and supports descriptive statistics only (mean, median, min, max, positive/negative/zero counts, quartiles). Missing observations (BRS, CCS) remain explicitly missing and are never replaced with zero or imputed.
3. Horizons H3 and H5, along with the 2026-08-21 T-state H1, are 100% `PENDING_OUTCOMES` because insufficient subsequent exact-session observations exist. The engine emits structured data accumulation needs highlighting low-sample descriptors (n < 30) and pending horizon requirements.
4. Strictly preserves negative boundaries: no backtest, no alpha/Sharpe/significance/p-values, no hit-rate skill, no recommendation authority, no sizing/liquidity authority, and zero promotion of RAW_AS_TRADED or historical PIT price basis.

## 2026-08-21 - Prospective Daily Rollforward & Learning Ledger V1

`PROSPECTIVE_DAILY_ROLLFORWARD_V1 = READY_LOCAL` (`prospective_daily_rollforward.py`, `run_prospective_daily_rollforward.py`, `push = NO`).

1. The completed 2026-08-20 → 2026-08-21 attribution remains immutable and is linked as the sole observed H1 ledger row. It is descriptive prospective research evidence, not a backtest, alpha, significance, edge, or recommendation claim.
2. The retained 2026-08-21 exact session seals an independent 524-member shadow T-state before any later retained exact session. It records 3 entrants (HMS, VPS, VTC), 2 exits (BRS, CCS), and a 521-member intersection with the frozen 2026-08-20 cohort; these are coverage changes, not ACTIVE_UNIVERSE claims.
3. Setup, price structure, market/relative/downside context, queue, dossier/task/scenario/owner/AI, and same-session fundamental authority are explicitly unavailable for the new T-state because no 2026-08-21 artifacts exist under those contracts. No 2026-08-20 analytical state is relabelled or rolled forward silently.
4. The append-only ledger counts genuine retained future sessions for H1/H3/H5. H3/H5 and the new T-state H1 remain pending; its maturity state is `FIRST_OBSERVATION_ONLY`. Historical PIT and RAW_AS_TRADED remain unresolved and unpromoted.

## 2026-08-21 - Downside Semantic Version Repair & Prospective Extension Successor

`DOWNSIDE_SEMANTIC_VERSION_REPAIR = READY_LOCAL` (`downside_uncertainty_research_context.py`, `prospective_research_context_extension.py`, `push = NO`).

1. The legacy current path had incorporated price-structure predicates into Downside V1, changing the core technical cohort from 378 to 382. The exact added tickers are AAN, MIG, TCW, and TRA; each is `NEAR_RECENT_SUPPORT` but satisfies none of V1's four original technical predicates. This is a semantic-versioning defect, not a data-state change.
2. Restored V1 is immutable from price structure and retains the 378-member four-predicate core. V2 expresses breakdown/near-support only in `PRICE_STRUCTURE_DOWNSIDE_CONTEXT`; it cannot alter V1 membership. The legacy 382 artifact `downside_uncertainty_research_context:da28e80273f2aaf488fbd9060b3a908584202ed030b2e5314c2d81e77933dfef` remains historical evidence, never overwritten.
3. Legacy extension `prospective_research_context_extension:1248d909c9ffd204d9bbcfbf3c886a4621e690c6739b5c8736fcab3bf7f58339` remains byte-stable but is `SUPERSEDED_FOR_FUTURE_ATTRIBUTION`. The corrected successor retains explicit predecessor/supersession lineage and exposes separate `downside:*_V1` and `price_structure:*` cohort keys; the prospective adapter rejects every non-successor extension.
4. The repair ran only after confirming that no accepted exact session is later than 2026-08-20. It performs no attribution and promotes no PIT, price, liquidity, sizing, valuation, share, or recommendation authority.

## 2026-08-20 - Evidence-Aware Research Screener V1

`EVIDENCE_AWARE_RESEARCH_SCREENER_V1 = READY_LOCAL` (`evidence_aware_research_screener.py`, `run_evidence_aware_research_screener.py`, `tests/test_evidence_aware_research_screener.py`, `push = NO`).

1. The deterministic screener consumes the existing 523-record empirical-active shadow cohort and unmodified eligibility verdicts. Its constrained field/lens/relative predicates compose only through explicit AND/OR/NOT nodes; unsupported fields, operators, lenses, and missing values fail closed rather than executing arbitrary code or coercing a match.
2. Real transparent preset coverage: positive trend 193, weak trend 320, retained fundamental context 523, higher-authority fundamentals 11, qualified relative context 27, partial scenario cohort 25, and researchable-but-execution-blocked 523. These are discovery filters, not rankings or investment conclusions.
3. Every matching row retains deterministic values, lens state, authority, warnings, dossier identity, matched predicate explanation and source artifact identities. The Review Pack overlay attaches only matched preset/query identities to its existing 25 names; it does not mutate queue membership, owner state, dossiers, tasks, scenarios, or authority.
4. The shadow cohort remains neither a market-wide nor executable universe. No signal, recommendation, target, probability, expected return, portfolio action, PIT, liquidity/sizing, valuation, share, provider-semantic, official-acquisition, or authority promotion occurs.

## 2026-08-20 - Strategy Research Eligibility Engine V1

`STRATEGY_RESEARCH_ELIGIBILITY_V1 = READY_LOCAL` (`strategy_research_eligibility.py`, `run_strategy_research_eligibility.py`, `tests/test_strategy_research_eligibility.py`, `push = NO`).

1. A versioned nine-lens registry now deterministically maps retained feature/evidence status to research eligibility. Eligibility is use-case sufficiency only, never signal quality, attractiveness, expected return, recommendation, trading safety, sizing, or historical performance.
2. The full 523-record pilot shows isolation: trend/momentum is eligible for 523; descriptive fundamentals are 11 eligible / 512 lower-authority eligible; official fundamentals are 11 eligible; relative technical is 27 eligible; scenario research is 25 partial. Every record has usable current research despite unrelated blocked dependent lenses.
3. Catalyst research is unavailable for all because no evidence-backed catalyst is retained. Liquidity-sensitive, valuation, and historical PIT research are blocked for all by their existing independent authorities. No provider descriptive state becomes official, and no comparison cohort is fabricated.
4. A compact Review Pack overlay provides usable, partial, and materially blocked lenses with reason codes for all 25 existing review names. No ranking, signal, target, probability, portfolio action, source acquisition, or authority promotion occurs.

## 2026-08-20 - Evidence-Bound Expectations & Scenario Research V1

`EXPECTATIONS_SCENARIO_RESEARCH_V1 = READY_LOCAL` (`expectations_scenario_research.py`, `run_expectations_scenario_research.py`, `tests/test_expectations_scenario_research.py`, `push = NO`).

1. The scenario contract is a deterministic research overlay over the 25-name owner-review cohort. Each immutable scenario version binds the existing dossier, thesis/counter-thesis, task, evidence authority, current observable state, and supported relative-context identity to three labelled Bear/Base/Bull lanes. It makes no forecast or recommendation.
2. All 25 cases are `PARTIAL_EVIDENCE_BOUND_SCENARIO`: drivers retain only `FACT`, `INFERENCE`, or `DATA_GAP` classification with source references. `probability_status=UNQUALIFIED`; explicit external expectations, market-implied expectations, and variant hypotheses are `UNAVAILABLE` rather than asserted. No catalyst has qualified retained evidence, so every lane reports `NO_EVIDENCE_BACKED_CATALYST`.
3. The invalidation contract only signals human review: 17 cases have a conditional `STATE_DETERIORATION` condition from an above-MA20 state; the other eight are `UNRESOLVED`. Every case also records a future-only `QUESTION_RESOLVED_AGAINST_THESIS` condition tied to its existing open task. No thesis can be automatically marked broken.
4. Relative context enters only 6/25 cases under its existing qualified-archetype contract. No probability, target, intrinsic value, expected return, consensus, market-pricing claim, ranking, portfolio action, alpha, causal attribution, PIT, liquidity/sizing, share, valuation, provider-semantic, official-acquisition, or authority promotion occurs.

## 2026-08-20 - Sector-Relative Research Context V1

`SECTOR_RELATIVE_RESEARCH_CONTEXT_V1 = READY_LOCAL` (`sector_relative_research_context.py`, `run_sector_relative_research_context.py`, `tests/test_sector_relative_research_context.py`, `push = NO`).

1. The relative-comparison contract is restricted to the same 2026-08-20 empirical-active shadow cohort and existing qualified entity-class archetypes. It does not infer broad sector/industry membership: 33/523 have qualified classification, with only corporate (n=21) and bank (n=6) satisfying the minimum five-member comparison cohort.
2. The pilot emits labelled relative facts for 20-day momentum, volatility, provider-scoped relative volume, and trend-state distribution across 27 records (108 metric contexts). Each result retains session, cohort identity/members, subject field/value, peer statistic/bucket, authority tier, and source lineage. Provider relative volume remains `DERIVED_PROXY`; technical context remains `SHADOW_ONLY`.
3. The separate Review Pack overlay preserves the base Review Pack identity and adds relative context for 6/25 review names. The other 19 receive explicit missing/small-cohort reasons. Fundamental relative context remains unavailable for all 523 because the daily product has no individual like-for-like retained financial metric values; no provider cross-metric calculation is introduced.
4. No authoritative active-universe, ranking, recommendation, valuation, target, expected return, alpha, causal, PIT, liquidity/sizing, share, provider-semantic, official-acquisition, or sector-membership authority is promoted.

## 2026-08-20 - Owner Research Journal & Human Feedback Overlay V1

`OWNER_RESEARCH_JOURNAL_V1 = READY_LOCAL` (`owner_research_journal.py`, `run_owner_research_journal.py`, `tests/test_owner_research_journal.py`, `push = NO`).

1. System research remains immutable: the journal is a separate append-only owner-event layer keyed to a specific review-pack identity, dossier identity, linked task identities, and reviewed research session. The latest-state projection is a view, not a mutation of the system pack, dossiers, tasks, or prospective snapshot.
2. The 2026-08-20 baseline maps all 25 deterministic review names with `UNREVIEWED` owner workflow state and no fabricated owner note, evidence request, follow-up, or priority override. It preserves current system task status and authority tiers solely as references.
3. A submitted owner edit creates a new hash-identified immutable event with prior-annotation lineage. Duplicate event bytes are idempotent; conflicting bytes fail closed. `HIGH`/`NORMAL`/`LOW` priority override affects only owner-view ordering, never deterministic AI queue membership or rank.
4. Owner statuses and notes are workflow-only. They cannot confirm/break a thesis, establish evidence, resolve/open a task, retry a deferred lane, authorize acquisition, promote authority, recommend an action, create a target/probability, or participate in performance scoring. Future prospective review may compare owner state separately from frozen system state and later observations.

## 2026-08-20 - Human Research Review Pack V1

`HUMAN_RESEARCH_REVIEW_PACK_V1 = READY_LOCAL` (`human_research_review_pack.py`, `run_human_research_review_pack.py`, `tests/test_human_research_review_pack.py`, `push = NO`).

1. The owner-facing review pack is a deterministic consumer of daily research, immutable dossiers, tasks, and prospective state. It provides a machine-readable identity-bound artifact plus a concise human rendering; no source dossier, task, or prospective artifact is changed by rendering.
2. The retained 2026-08-20 pack reconciles 523 dossiers, 1,046 tasks, and all 25 deterministic review names. Each review entry keeps direct dossier/task/evidence lineage and separately displays `FACT`, `INFERENCE`, `DATA_GAP`, and `QUESTION_TO_VERIFY`; the prospective status remains `PENDING_FUTURE_OBSERVATION`.
3. The 523 identical liquidity tasks are compressed into one deferred-blocker group with the exact affected population and per-task identities retained in the structured artifact. The 25 owner annotation schemas are deliberately unpopulated and separate from immutable research state.
4. No AI, renderer, or owner-annotation contract may change deterministic queue membership, task status, factual authority, warnings, thesis/counter-thesis history, or create a recommendation, target, probability, execution, PIT, liquidity/sizing, share, valuation, provider-semantic, or official-source promotion.

## 2026-08-20 - Research Question Resolution & Evidence Tasking V1

`RESEARCH_QUESTION_TASKING_V1 = READY_LOCAL` (`research_question_tasking.py`, `run_research_question_tasking.py`, `tests/test_research_question_tasking.py`, `push = NO`).

1. Each retained dossier question and data gap now creates a stable, immutable research task keyed by ticker, task kind, and question semantics. Task versions retain originating/current dossier identity, session semantics, thesis/counter-thesis hashes, evidence paths, authority tier, status lineage, and an explicit expected-evidence/reopen contract.
2. The real 2026-08-20 baseline has 1,046 tasks from all 523 dossiers: 523 `OPEN` issuer-context questions and 523 `DEFERRED_NO_CURRENT_EVIDENCE_ROUTE` liquidity tasks. The latter are deferred under `QUALIFIED_LIQUIDITY_INPUTS_NOT_AVAILABLE` and reopen only with qualified market-wide volume/traded-value composition evidence; no daily retry loop is created.
3. Only an explicit existing-contract check can move a task to `RESOLVED_BY_QUALIFIED_EVIDENCE`; permitted lower-authority evidence can only become `RESOLVED_DESCRIPTIVELY`. Conflicts remain open, and a changed question creates a successor while the historical task becomes `SUPERSEDED_BY_NEW_QUESTION`. AI has no task-resolution authority.
4. The deterministic 25-name AI research queue is preserved as 25 transparent human research tasks. No web/provider acquisition, historical PIT, share, liquidity/sizing, valuation, recommendation, target, probability, provider-semantic, or official-source authority was opened or promoted.

## 2026-08-20 - Persistent Research Dossier & Thesis Change Detection V1

`PERSISTENT_RESEARCH_DOSSIER_V1 = READY_LOCAL` (`persistent_research_dossier.py`, `run_persistent_research_dossier.py`, `tests/test_persistent_research_dossier.py`, `push = NO`).

1. The daily research product is now retained as immutable, per-ticker dossier versions. Each version binds the deterministic research state and source artifact identities to attention descriptors, authority tiers, thesis/counter-thesis hashes, open questions, data gaps, warnings, and evidence-field paths.
2. Initial retained 2026-08-20 state is honestly `NEW_RESEARCH_STATE` for all 523 empirical-active records. The 25-name deterministic AI research queue is preserved as a human follow-up queue, with explicit queue-membership reason and no Buy/Sell interpretation.
3. Comparing identical daily input to the retained versions yields 523 `NO_MATERIAL_CHANGE` outcomes. A changed future state can emit only named deterministic categories (`DETERMINISTIC_EVIDENCE_CHANGED`, attention, authority, data-gap, thesis, counter-thesis, question, and `HUMAN_REVIEW_REQUIRED`); this does not let AI rewrite past dossiers, decide authority, or judge a thesis true/false.
4. No historical PIT/backtest, RAW_AS_TRADED, liquidity/sizing, current-share, valuation, recommendation, target, probability, or provider/official semantic authority was promoted. The next product prerequisite is a genuinely later exact-session daily observation, which may then be compared prospectively without fabricating history.

## 2026-08-20 - P3-F14 Generic Official Financial Source Discovery & Registry Expansion

`P3F14_OFFICIAL_SOURCE_DISCOVERY = PARTIAL_LOCAL` (`official_financial_source_discovery.py`, `p3f14_official_financial_source_discovery.py`, `push = NO`).

1. The target cohort is derived solely from P3-F13 `NO_APPROVED_ROUTE_FOUND` dispositions: 510 issuers, each receiving exactly one closed-world discovery disposition.
2. Existing retained inputs have no issuer-domain ownership or official exchange-detail signal for the target cohort. Discovery therefore produces zero authority recommendations and no registry mutation; candidate discovery remains distinct from approval.
3. Next blocker is retained issuer-domain ownership or exchange-profile evidence. No filing acquisition, source promotion, or P3-G work occurred.

## 2026-08-20 - P3-F13 Generic Official Financial Evidence Operational Scale-Out

`P3F13_OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT = COMPLETE_LOCAL` (`p3f13_official_financial_evidence_scaleout.py`, `tools/run_p3f13_official_financial_evidence_scaleout.py`, `tests/test_p3f13_official_financial_evidence_scaleout.py`, `operations-review/p3f13-official-financial-evidence-scaleout-20260820/p3f13_official_financial_evidence_scaleout_artifact.json`, `push = NO`).

1. **Target Cohort & Approved Route Execution**:
   - Programmatically derived target cohort: 512 blocked instruments from the 523-member empirical-active research cohort.
   - Evaluated discovery and acquisition through approved official source routes (HOSE, HNX, VSDC, approved issuer IR).
   - Zero unattempted candidates (`UNATTEMPTED_WITHOUT_DISPOSITION = 0`). 2 issuers with retained filings (PNJ, FPT) resolved `FILING_ALREADY_RETAINED`; 510 issuers without approved routes in registry resolved `NO_APPROVED_ROUTE_FOUND`.

2. **Metadata & Value Qualification**:
   - P3-F11 metadata qualification verified explicit hash-bound spans for PNJ (FY2024 consolidated annual) and FPT (FY2025 consolidated annual).
   - P3-F12 value reconciliation exactly matched 8 new canonical facts (`total_assets`, `total_liabilities`, `shareholders_equity`, `cash_and_equivalents`) against provider observations with zero fuzzy matching or tolerance.
   - Duration statements for FPT/PNJ failed closed on `PERIOD_MISMATCH` / `PROVIDER_OBSERVATION_MISSING` preserving integrity.

3. **Readiness & Gate Evolution**:
   - Qualified financial cohort expanded 11→13 issuers; qualified facts expanded 130→138.
   - P3-B fundamental research readiness expanded from 11 to 13 `PARTIAL` issuers (510 `BLOCKED`).
   - Scaleout gate: `OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_PARTIAL`.
   - Preserved all fail-closed boundaries: zero production database mutations, zero new providers, zero unpromoted source authority, zero ticker-specific production branches.
   - Next recommended gate: **P3-F14: Generic Issuer IR and Exchange Disclosure Source Registry Expansion**.

## 2026-08-20 - P3-F12 Generic Value-Level Financial Evidence Qualification Foundation

`P3F12_VALUE_LEVEL_FINANCIAL_EVIDENCE = COMPLETE_LOCAL` (`official_financial_value_evidence.py`, `p3f12_value_level_financial_evidence.py`, `push = NO`).

1. The read-only engine requires exact hash-bound official spans, canonical metric identity, documented period/scope/currency/scale, and integer-only normalization. It permits no tolerance, fuzzy magnitude match, generic absolute value, or scope inference.
2. Retained HPG, VCB, and SSI total-assets proof records reconcile exactly to retained provider observations. The established FY/Q4 balance-sheet alias is the only period bridge; VCB's match records its explicitly declared million-VND filing scale. A malformed numeric span blocks.
3. The output is an ephemeral canonical qualification projection: no canonical store, database, source/provider authority, or document inventory changed. P3-B readiness is unchanged because those facts were already represented in the qualified cohort.
4. Next exact gate: P3-F13 Generic Official Financial Evidence Operational Scale-Out. It is not started.

## 2026-08-20 - P3-F11 Generic Official Financial Filing Evidence & Statement-Metadata Qualification Foundation

`P3F11_FINANCIAL_EVIDENCE_FOUNDATION = PARTIAL_LOCAL` (`official_financial_filing_evidence.py`, `p3f11_official_financial_filing_evidence.py`, `tools/run_p3f11_official_financial_filing_evidence.py`, `push = NO`).

1. **Fail-closed evidence envelope:** Required filing metadata—period, periodicity, consolidated/separate scope, currency, and unit scale—now needs an explicit hash-bound source span and a SHA-256 match to retained bytes. Audit/review and publication date remain optional metadata and are recorded only where evidenced.
2. **Representative retained pilot:** One corporate, one bank, and one securities filing qualify document metadata generically; a P3-F10 `SOURCE_MISSING` case stays blocked. The selection is data-driven by existing retained evidence and entity metadata, without ticker-specific production branches, source/provider changes, document acquisition, PDF value extraction, or runtime mutation.
3. **No fact promotion by metadata alone:** The envelope creates zero provider observations and cannot satisfy canonical-fact qualification on its own. Existing exact official value-level citation and exact provider-match requirements remain unchanged; P3-B readiness and all 523 cohort dispositions are unchanged.
4. **Next exact gate:** `VALUE_LEVEL_FINANCIAL_EVIDENCE_QUALIFICATION_FOUNDATION`. P3-G is not started.

## 2026-08-20 - P3-F10 Generic Fundamental Evidence Scale-Out

`P3F10_GENERIC_FUNDAMENTAL_EVIDENCE_SCALEOUT = PARTIAL_LOCAL` (`p3f10_fundamental_evidence_scaleout.py`, `tools/run_p3f10_generic_fundamental_evidence_scaleout.py`, `push = NO`).

1. **Generic retained-data coverage:** The current `COHORT_EMPIRICALLY_ACTIVE` is read from the P3-F9B bundle, not hardcoded: 523 members at 2026-08-20. Existing generic stores provide raw observation retention and canonical mappings for 520 members; three have an explicit `SOURCE_MISSING` disposition.
2. **Qualification boundary preserved:** Provider VCI/KBS observations remain `RAW_OBSERVED`/`RETAINED`/`SEMANTICALLY_MAPPED` only. 509 mapped members are explicitly `STATEMENT_SCOPE_UNKNOWN` because scope, currency, and scale lack independent evidence. They are not promoted or discarded. The existing P3-E official-evidence panel remains 11 issuers / 130 qualified facts; rerunning P3-B confirms 94 exact-qualified metrics, 22 proxies, and 11 `PARTIAL` readiness results.
3. **Sector boundary preserved:** Banks and securities retain their P3-B sector mappings and industrial FCFF/EV gates remain `NOT_APPLICABLE`; unknown, insurance, and finance-company records fail closed absent a real-data supported contract. A missing fact blocks only its dependent metric.
4. **No authority expansion:** No provider, source registry, official-document acquisition, runtime database, price/share authority, liquidity lane, or P3-G scope changed. The highest-value next fundamental capability is generic approved evidence acquisition that preserves publication identity, period, statement scope, currency, and unit scale.

## 2026-08-20 - P3-F9B Market-Wide Exact-Session Snapshot Scale-Out Complete

`P3F9B_MARKET_WIDE_EXACT_SESSION_SCALEOUT = COMPLETE_LOCAL` (`mva_exact_session_snapshot.py`, `tools/run_p3f9b_market_wide_exact_session_scaleout.py`, `tests/test_p3f9b_market_wide_exact_session_scaleout.py`, `operations-review/p3f9b-market-wide-exact-session-scaleout-20260820/p3f9b_market_wide_exact_session_scaleout_artifact.json`, `push = NO`).

1. **Market-Wide Exact-Session Materialization & Coverage**:
   - Scaled generic DNSE exact-session materialization across all 1,683 canonical candidates for completed session `2026-08-20`.
   - Exact session equality confirmed: `resolved_completed_session == retained_snapshot_session == MVA_bundle_session == 2026-08-20`.
   - Full candidate disposition reconciliation: 843 `EXACT_SESSION_RETAINED` (50.09%), 667 `SESSION_MISSING` (39.63%), 173 `PROVIDER_REJECTED` (10.28%), 0 `MALFORMED`, 0 `TRANSPORT_FAILED`, 0 unattempted without explicit disposition.

2. **Refreshed 20-Session Empirical Active Cohort & Breadth**:
   - Refreshed `COHORT_EMPIRICALLY_ACTIVE`: 523 members with complete 20-session observations (`2026-07-24` to `2026-08-20`); 1,160 excluded candidates fail closed for incomplete/missing observation coverage.
   - Exact breadth reconciliation over the 523 denominator: 223 advancing, 187 declining, 113 unchanged, 0 missing (advance ratio 0.4264).
   - Full technical features (close, 1d return, 20d momentum, 3/5/20 MA, 20d volatility, provider-scoped relative volume) available across 100% of empirical cohort.

3. **Freshness Gate & Authority Boundaries**:
   - `MVA_POST_CLOSE_MARKET_WIDE_SESSION_READY = YES`.
   - Preserved strict fail-closed boundaries: `price_basis = CURRENT_MARKET` (descriptive use only), `RAW_AS_TRADED = NOT_PROMOTED`, `HISTORICAL_PIT = BLOCKED`, zero dashboard/runtime DB mutations, zero ticker-specific branches.
   - Next operational gate: **P3-F10: Generic Fundamental Evidence Scale-Out**.

## 2026-08-20 - P3-B Sector-Aware Fundamental Quality & Research Readiness Complete

`P3B_FUNDAMENTAL_RESEARCH_ENGINE = COMPLETE_LOCAL` (`fundamental_research_readiness.py`, `tools/run_p3b_fundamental_research_readiness.py`, `operations-review/p3b-fundamental-research-readiness-20260820/p3b_fundamental_research_readiness_artifact.json`, `push = NO`).

1. **Activated Fundamental-Only Capability**:
   - Consumes only the already-authoritative P2 financial-panel cohort (9 corporate issuers, VCB bank, SSI securities); no evidence acquisition, production database/runtime mutation, or market-data dependency.
   - Emits deterministic per-metric values/methods, blocked reasons, input fact IDs, citation/document lineage, statement scope, currency, periods, and PIT eligibility.
   - Calculates only sector-compatible metrics: corporate growth/margins/ROA-ROE/debt/cash-flow; bank ROA-ROE, loan-to-deposit, and credit cost; securities ROA-ROE, FVTPL-assets, and margin-loans. Average balances are exact derivations; ending balances are explicit `DERIVED_PROXY` values.

2. **Preserved Fail-Closed Boundaries**:
   - Conflicting, missing, non-positive-authority, non-PIT, scope-mismatched, currency-mismatched, and scale-mismatched inputs cannot feed a positive metric.
   - Corporate debt/cash-flow semantics remain `NOT_APPLICABLE` for banks and securities; insurance, finance-company, unknown, and unpromoted classes fail closed.
   - The artifact has no universal score, ranking, recommendation, valuation/DCF/target price, price/liquidity dependency, sizing, execution, or backtest authority.

3. **Independent P3-A Status and Next Fundamental Gate**:
   - `P3-A` remains terminal-blocked pending qualified explicit ex-date evidence; P3-B does not reopen, bypass, or alter it.
   - The produced data-gap matrix identifies the next large fundamental gate: owner-authorized comparative financial evidence scale-out for multi-period bank/securities coverage and missing corporate income/balance identities. It is not started by this decision.

## 2026-08-20 - Phase 3-A Bounded Price Adjustment & Dividend Ex-Date Event Window Qualification (Terminal Blocker)

`P3A_PRICE_ADJUSTMENT_EVENT_WINDOW_QUALIFICATION = BLOCKED_PENDING_QUALIFIED_EX_DATE` (`docs/STATE.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, `push = NO`).

1. **Gate 1 Evaluation — Qualified Ex-Date Evidence Audit**:
   - Comprehensive audit of all retained corporate action evidence, registries, manifests, citations, and official documents in the repository:
     - `HPG`: HOSE notice `1475/TB-SGDHCM` (PDF: `8bbae21fbb3e6c11f925385ac35b290e86e3db8753188131acbbba3bad5b29b2.pdf`) and issuer IR notice (HTML: `cb41c96ef78bed7654030e55bb06dea22d051b1c9fcf1a6cf024e9f964563c1c.html`) state `shares_issued: 767,498,665`, `shares_after: 8,442,964,520`, and `trading_date: 2026-07-16`; `ex_date` is **absent** (`adjustment_factor_status = not_ready`).
     - `SSI`: VSDC notice 198728 (HTML: `bd7d4054613ae6f9c5ee1ddc6b787bf706ac6a18f551aff3c9683a85bcc06dad.html`) states `record_date: 2026-08-18`, `cash_amount: 1,000 VND`, `stock_ratio: 0.2`; `ex_date` is **absent** (`ex_date_absent`), issuance is planned/unexecuted (`shares_after` absent).
     - `VNM`: VSD notice 177392 (HTML: `vsdc-record-date-notice.html`) and Vinamilk 2024 Annual Report state `record_date: 2024-12-27`, `payment_date: 2025-02-28`, `cash_amount: 500 VND`; `ex_dividend_date` is explicitly omitted ("no direct official source ties 2024-12-26 to this event").
     - `VCB`: VSDC listing change notice states share count transition; `ex_date` is **absent**.
     - Vendor feeds in `corporate_event_records` (`vn_stock.db`) are third-party partial observations (`qualification = partial`, `citation_reason = partial_observation_no_qualified_citation`, `adjustment_provenance = not_generated`).

2. **Mandatory Fail-Closed Enforcement**:
   - Repository invariant strictly prohibits inferring ex-dates from record dates, payment dates, announcement dates, T+ settlement conventions, or price movements.
   - Zero source-code authority changed; zero network evidence acquired; zero assumptions made.
   - Gate 2 is **NOT REACHED**.
   - Terminal verdict: `P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE`.

3. **Preserved Upstream Blockers**:
   - `RAW_AS_TRADED = NOT_PROMOTED`
   - `QUALIFIED_LIQUIDITY_INPUTS = NO`
   - `POSITION_SIZING_IS_SAFE = NO`
   - Valuation multiples and cross-sectional strategy ranking remain prohibited.

## 2026-08-20 - Phase 2 Closeout & Market-Wide Financial Fact Panel Integration Complete

`P2_CLOSEOUT_MARKET_WIDE_FINANCIAL_FACT_PANEL_INTEGRATION = COMPLETE_LOCAL` (`multi_period_financial_panel.py`, `tools/run_p2_closeout_financial_panel.py`, `tests/test_multi_period_financial_panel.py`, `operations-review/p2-closeout-financial-fact-panel-20260820/p2_closeout_financial_panel_artifact.json`, `push = NO`).

1. **Unified Authoritative Fact Panel Integration**:
   - Integrated all already-authoritative / already-promoted Phase 2 financial fact scopes into the unified `multi_period_financial_panel.py` contract:
     - Governed Corporate Facts: `HPG`, `VNM`, `PAN`, `PVD`, `NVL`, `POW`, `QNS` (baseline citations) + `GAS`, `VRE` (P2-D / P2-C2C governed citations).
     - Promoted Bank Scope: `VCB` FY2024 consolidated (15 facts, Circular 49/2014/TT-NHNN).
     - Promoted Securities Scope: `SSI` FY2024 consolidated (16 facts, Circular 334/2016/TT-BTC).
     - Layered Entity Classification: Integrated Topology B resolution (20 seed + 20 promoted = 40 positive current-state, 1,620 unpromoted fail-closed as UNKNOWN).
   - Produced deterministic closeout artifact: `p2_closeout_financial_panel:46335e0b527ed39cbbcc8082508c85e86892f83137bf205f416e9d0bbbbc8eed` (11 proof issuers, 102 qualified facts, 0 synthetic observations).

2. **Strict Sector Boundaries & Invariant Enforcement**:
   - Intermediary debt ratios (`debt_to_equity`, `net_debt`, `total_interest_bearing_debt`), EBITDA, and working capital fail closed as `NOT_APPLICABLE` for `bank` and `securities`.
   - `ENDING_EQUITY_ROE_PROXY` normalized across Corporate (`net_income / shareholders_equity`), Bank (`net_profit_parent / total_equity`), and Securities (`profit_after_tax_parent / total_equity`).
   - Generic-vs-specialized disagreement fails closed as `CONFLICT` (positive authority denied, fact value suppressed).
   - Zero silent forward-fill (unobserved periods remain `MISSING` with null values); zero statement scope mixing (`consolidated` vs `separate`); zero currency mixing (`VND` vs `USD`); zero lookahead.

3. **Phase 3 Readiness & Independent Gate Review**:
   - Fundamental accounting panel status: `PHASE2_COMPLETE`.
   - Phase 3 strategy/backtesting entry status: `PHASE3_ENTRY_READY_FOR_BOUNDED_REVIEW`.
   - Explicitly records negative gates:
     - `RAW_AS_TRADED = NOT_PROMOTED` (P0-A.3E Part B blocked fail-closed pending qualified ex-dates).
     - `QUALIFIED_LIQUIDITY_INPUTS = NO` (P0-B negative proof).
     - `POSITION_SIZING_IS_SAFE = NO` (P0-B negative proof).
     - `VALUATION_MULTIPLES_PERMITTED = NO`.
     - `STRATEGY_RANKING_PERMITTED = NO`.
   - Next critical path gate: **P3-A (Bounded Price Adjustment & Dividend Ex-Date Event Window Qualification)**.

## 2026-08-20 - Phase 2-F3 Bounded Generic Sector Extraction Authority Promotion Complete

`P2F3_BOUNDED_GENERIC_SECTOR_EXTRACTION_PROMOTION = COMPLETE_LOCAL` (`config/promoted_sector_extractions.json`, `sector_financial_taxonomy.py`, `generic_financial_canonicalizer.py`, `tools/run_p2f3_sector_extraction_promotion.py`, `tests/test_sector_extraction_promotion.py`, `push = NO`).

1. **Owner-Authorized Bounded Promotion**:
   - Promoted the generic sector taxonomy extraction path strictly for the proven real-data scopes:
     - **BANK**: Bounded strictly to VCB FY2024 consolidated audited statements (`9deccc3518e23302d00353b4d371a9dd251b67b12f9fe58a4da4ad3c727e99f8`), Circular 49/2014/TT-NHNN, 15 authoritative facts.
     - **SECURITIES**: Bounded strictly to SSI FY2024 consolidated audited statements (`38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74`), Circular 334/2016/TT-BTC, 16 authoritative facts.
   - Declarative registry persisted in `config/promoted_sector_extractions.json` (`p2f3_sector_extraction_promotion:1b0a94b7f0c0e9ea00948b3f3f6370152d7681535d64f3069099cf26fa1f2eff`).

2. **Explicit Layered Precedence & Reconciliation Contract**:
   - Precedence: `GENERIC_QUALIFIED_SECTOR_FACT` > `SPECIALIZED_LEGACY_RECORD` > `UNKNOWN`.
   - Legacy specialized implementations (`test_vcb_banking_identity_qualification.py`, `ssi_official_financial_materialization.py`) preserved as reference corroboration and regression authority.
   - `generic_financial_canonicalizer.py` updated: `ssi_official_financial_materialization.py` transitioned to role `GENERICALLY_SUPERSEDED` and status `SUPERSEDED_BY_GENERIC_SECTOR_TAXONOMY_RETAINED_FOR_REFERENCE`.
   - Disagreement between generic and specialized evidence fails closed as `CONFLICT` (positive authority denied, value suppressed).

3. **Strict Boundary Gating**:
   - Insurance (`BVH`) and Finance Company (`EVF`) extraction attempts fail closed as `UNPROMOTED_SECTOR` (`SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED`).
   - Additional bank tickers (`ABB`, `ACB`) and securities tickers (`AAS`, `ABW`) fail closed as `UNPROMOTED_ISSUER`.
   - Unclassified listed equities (1,620 tickers) fail closed as `UNRESOLVED_ENTITY_CLASS`.
   - Historical PIT entity-classification authority remains `NOT_ESTABLISHED`.
   - `config/ticker_entity_profiles.csv` (20 seed records) and `config/promoted_entity_classifications.json` (20 promoted records) remain 100% unmutated.
   - `TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0`.

## 2026-08-19 - Phase 2-F1 Sector Financial Taxonomy & Disclosure Parsing Foundation Complete

`P2F1_SECTOR_FINANCIAL_TAXONOMY_FOUNDATION = COMPLETE_LOCAL` (`sector_financial_taxonomy.py`, `financial_disclosure_recognizer.py`, `tools/run_p2f1_sector_financial_taxonomy.py`, `tests/test_sector_financial_taxonomy.py`, `push = NO`).

1. **Deterministic Sector Financial Taxonomy Contract**:
   - Implemented `sector_financial_taxonomy.py` declaring `StatementFormFamily`, `SectorProofStatus`, `MetricApplicabilityState`, and `MetricDefinition` specifications for `bank`, `securities`, `corporate`, `insurance`, and `finance_company`.
   - Mapped sector primary statement forms (`SECTOR_PRIMARY_STATEMENT_FORMS`) and explicit corporate metric inapplicabilities (`SECTOR_INAPPLICABLE_CORPORATE_METRICS`).
   - Implemented `evaluate_metric_sector_applicability()` with strict fail-closed semantics across ordinary corporate vs intermediary semantics.

2. **Generic Financial Disclosure & Note Recognition Engine**:
   - Implemented `financial_disclosure_recognizer.py` supporting authoritative entity-class gating (`resolve_layered_entity_classification`), primary statement vs note section recognition, Vietnamese statutory form code detection (`B 02/TCTD-HN`, `B 01-CTCK/HN`, `B 09-CTCK`, etc.), note heading and cross-reference extraction, unit/scale discovery, and deterministic citation generation (`compute_sector_citation_id`).
   - Enforced `TICKER_SPECIFIC_SECTOR_EXTRACTION_BRANCH_COUNT = 0`.

3. **Real Proof Corpus vs Schema-Only Separation**:
   - Real-data validated sectors: `bank` (VCB FY2024 consolidated, Circular 49/2014/TT-NHNN, 15 extracted facts) and `securities` (SSI FY2024 consolidated, Circular 334/2016/TT-BTC, 16 extracted facts).
   - Schema-supported only sectors: `insurance` (Circular 199/2014/TT-BTC) and `finance_company` (Circular 49/2014/TT-NHNN) — extraction fails closed with `SCHEMA_SUPPORTED_BUT_NOT_REAL_DATA_VALIDATED` pending verified retained proof filings. Zero synthetic observations generated.
   - Unclassified listed equities (1,620 issuers) fail closed with `ENTITY_CLASS_UNRESOLVED`.

4. **Regression & Exact Semantic Matches**:
   - VCB FY2024 extracted facts: Interest Income (`93,654,841,000,000` VND, Note 23), Interest Expense (`38,249,106,000,000` VND, Note 24), Net Interest Income (`55,405,735,000,000` VND), Profit Before Tax (`42,236,135,000,000` VND), Net Profit Parent (`33,831,386,000,000` VND), Total Assets (`2,085,873,522,000,000` VND), Customer Deposits (`1,514,664,850,000,000` VND), Customer Loans Net (`1,418,015,724,000,000` VND), Total Equity (`196,209,168,000,000` VND) — all classified `EXACT_SEMANTIC_MATCH`.
   - SSI FY2024 extracted facts: Financial Assets FVTPL (`42,438,121,481,401` VND), Loans Balance (`21,998,601,885,375` VND), Total Assets (`73,507,302,559,722` VND), Current Liabilities (`46,599,438,522,989` VND), Short-Term Borrowings (`45,501,969,699,137` VND, Note 21), Total Equity (`26,826,650,611,768` VND, Note 29), Total Operating Revenue (`8,529,279,575,474` VND), Brokerage Revenue (`1,667,430,605,344` VND), FVTPL Gain (`4,021,594,603,243` VND), FVTPL Loss (`1,458,465,074,277` VND), Borrowing Costs (`1,505,764,783,295` VND), Profit After Tax Parent (`2,835,023,120,364` VND), Basic EPS (`1,554` VND), Ordinary Shares (`1,961,872,450`) — all classified `EXACT_SEMANTIC_MATCH`.

5. **Authority Status & Process History**:
   - Authority status: `PROMOTION_REVIEW_READY` (`operations-review/p2f1-sector-financial-taxonomy-foundation-20260819/p2f1_sector_financial_taxonomy_artifact.json`).
   - Process History Correction: `PROCESS_VIOLATION_CURRENT_P2E3 = YES` recorded due to background `manage_task` usage during that milestone. P2-F1 was conducted with 100% synchronous terminal execution, no background tasks, and full invariant compliance.

## 2026-08-19 - Phase 2-E3 Bounded Current-State Entity Classification Authority Promotion Complete

`P2E3_BOUNDED_ENTITY_CLASSIFICATION_PROMOTION = COMPLETE_LOCAL` (`config/promoted_entity_classifications.json`, `entity_classification_contract.py`, `financial_entity_applicability.py`, `financial_mapping.py`, `tools/run_p2e3_entity_classification_promotion.py`, `tests/test_layered_entity_classification.py`, `push = NO`).

1. **Owner-Authorized Bounded Promotion**:
   - Authorized promotion strictly bounded to the exact 20 reviewed P2-E validation records from artifact `p2e_entity_classification:41594ec20971d7a01b6b8f9c993062f1b87f38938ed58005a42ea128dbdea66f`.
   - Stored in a separate, deterministic, provenance-preserving manifest: `config/promoted_entity_classifications.json` (`p2e3_entity_classification_promotion:f47d56819fc6c1668614338efc103c7eed1508159c8bae5f66f9a09f459680a9`).
   - Baseline seed authority `config/ticker_entity_profiles.csv` remains 100% unmutated (`SEED_PROFILE_FILE_MODIFIED = NO`).

2. **Layered Authority Topology B Adopted**:
   - Precedence: `CURATED_SEED_AUTHORITY` > `APPROVED_QUALIFIED_CLASSIFICATION_RECORD` > `UNKNOWN`.
   - Disagreement across seed and promoted records fails closed as `CONFLICT` (no positive authority).
   - Promoted records with `AMBIGUOUS` or `CONFLICT` status never supply positive classification.
   - Anti-Automatic Promotion Gate: Future classifier runs producing `status == QUALIFIED` do NOT confer authority without explicit owner promotion manifest update.

3. **Authority Scope & Temporal Safety**:
   - Promotion establishes `CURRENT_STATE_ONLY` entity classification authority.
   - Historical PIT requests fail closed as `HISTORICAL_PIT_NOT_ESTABLISHED` (`HISTORICAL_PIT_PROMOTED = NO`).

4. **Scale & Authority Census**:
   - `CURATED_SEED_AUTHORITY_RECORDS = 20`
   - `NEW_PROMOTED_RECORDS = 20` (15 corporate, 2 bank `ABB`/`ACB`, 2 securities `AAS`/`ABW`, 1 insurance `ABI`)
   - `TOTAL_POSITIVE_CURRENT_STATE_RECORDS = 40`
   - `REMAINING_UNKNOWN_LISTED_EQUITIES = 1,620` (out of 1,660 listed equities, 3,250 total candidates).

5. **Downstream Applicability Integration**:
   - Validated across `financial_entity_applicability.py`, `multi_period_financial_panel.py`, `financial_mapping.py`, `market_wide_financial_coverage.py`, and `export_ai_bundle.py`.
   - Banks, securities companies, and insurers fail closed on corporate debt/EBITDA models.

## 2026-08-19 - Phase 2-E Evidence-Backed Entity Classification Scale-Out Foundation Complete

`P2E_ENTITY_CLASSIFICATION_FOUNDATION = COMPLETE_LOCAL` (`entity_classification_contract.py`, `evidence_backed_entity_classifier.py`, `tools/run_p2e_entity_classification_foundation.py`, `tests/test_evidence_backed_entity_classifier.py`, `push = NO`).

1. **Canonical Classification Schema & Contract**:
   - Defined `entity_classification_contract.py` declaring `EntityClass` (`corporate`, `bank`, `securities`, `insurance`, `finance_company`, `unknown`), `ClassificationStatus` (`QUALIFIED`, `UNKNOWN`, `AMBIGUOUS`, `NOT_APPLICABLE`, `CONFLICT`), and `EvidenceTier` (`documented_verified`, `exchange_security_master`, `statement_template`, `curated_seed_authority`).
   - Immutable, provenance-bound `EntityClassificationRecord` containers bound with deterministic SHA-256 evidence payload hash (`compute_classification_evidence_id`).
   - Preserves temporal semantics (`effective_from`, `knowledge_available_at`, `verified_at`).

2. **Generic Evidence-Backed Classifier Engine**:
   - Implemented `evidence_backed_entity_classifier.py` with multi-evidence positive authority fusion across:
     - Legal charter & registered name descriptors (`ngan hang tmcp`, `ctcp chung khoan`, `ctcp bao hiem`, `ctcp tai chinh`, `ctcp / cong ty co phan`).
     - Statement form codes (`B 01-DN`, `B 01-NH`, `B 01-CK`, `B 01-BH`).
     - Exclusive line-item financial markers (Balance sheet and Income statement marker sets).
     - Curated seed authority baseline (`config/ticker_entity_profiles.csv`).
   - Zero hardcoded symbol logic in production classification rules (`TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT = 0`).
   - Strict fail-closed semantics: absence of evidence remains `UNKNOWN_ENTITY_CLASS` (`ClassificationStatus.UNKNOWN`), never a silent default to corporate.
   - Contradictory evidence across authoritative sources produces `ClassificationStatus.CONFLICT`.

3. **Validation Corpus & Scale Denominators**:
   - Evaluated 40 issuers:
     - Part A: 20 existing known seed profiles (`PAN`, `HPG`, `FPT`, `PNJ`, `PVD`, `POW`, `QNS`, `NVL`, `VNM`, `MWG`, `GAS`, `VIC`, `VRE`, `SSI`, `VCB`, `BID`, `MBB`, `TCB`, `BVH`, `EVF`) — 100% verified consistent.
     - Part B: 20 deterministically selected previously-UNKNOWN listed equities (`A32`, `AAA`, `AAH`, `AAM`, `AAN`, `AAS`, `AAT`, `AAV`, `ABB`, `ABC`, `ABI`, `ABR`, `ABS`, `ABT`, `ABW`, `ACB`, `ACC`, `ACE`, `ACG`, `ACL`) — correctly classified into 15 corporate, 2 bank (`ABB`, `ACB`), 2 securities (`AAS`, `ABW`), 1 insurance (`ABI`).
   - Scale denominators tracked:
     - `TOTAL_CANONICAL_CANDIDATES = 3,250`
     - `LISTED_EQUITY_CANDIDATES = 1,660`
     - `PREVIOUSLY_POSITIVELY_CLASSIFIED = 20`
     - `PREVIOUSLY_UNKNOWN = 1,640`
     - `VALIDATION_UNKNOWN_COHORT = 20`
     - `NEWLY_QUALIFIED = 20`
     - `REMAINING_MARKET_UNKNOWN = 1,620`
     - `AMBIGUOUS_COUNT = 0`
     - `CONFLICT_COUNT = 0`

4. **Downstream Applicability Integration**:
   - Validated against `financial_entity_applicability.py` and `multi_period_financial_panel.py`.
   - Verified that banks, securities, and insurers fail closed on corporate debt / EBITDA metrics (`not_applicable` / `NOT_APPLICABLE`), while corporates retain standard debt-to-equity and net debt eligibility subject to inputs.

5. **Governance & Authority Promotion Safety**:
   - Output emitted to `operations-review/p2e-evidence-backed-entity-classification-20260819/` (`p2e_entity_classification_artifact.json`, `READINESS_REPORT.md`).
   - Authority status marked as **`PROMOTION_REVIEW_READY`**. Baseline `config/ticker_entity_profiles.csv` remains un-overwritten pending owner promotion authorization.

## 2026-08-19 - Phase 2-D Generic Financial Statement Template Recognition and Extraction Complete

`P2D_GENERIC_FINANCIAL_EXTRACTION = COMPLETE_LOCAL` (`financial_statement_template_recognizer.py`, `governed_financial_evidence_extraction.py`, `tools/run_p2c2_corporate_evidence_onboarding.py`, `tests/test_financial_statement_template_recognizer.py`, `push = NO`).

1. **Generic Template Recognition Engine**:
   - Implemented `financial_statement_template_recognizer.py` establishing pure, data-driven financial statement template recognition.
   - Zero hardcoded issuer/ticker rules (`TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT = 0`).
   - Automatically parses statement type (`BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`) and accounts for continuation pages.
   - Dynamically determines reporting unit and scale (`VND`, `triệu VND`, `tỷ VND`) and fails closed with `UNIT_SCALE_AMBIGUOUS` if absent.
   - Discovers period-column semantic orientation (`Số cuối năm` / `Năm nay` vs `Số đầu năm` / `Năm trước`) and fails closed with `PERIOD_COLUMN_AMBIGUOUS` if ambiguous.

2. **Net Income Semantic Contract & Mismatch Correction**:
   - Strictly established `CANONICAL_NET_INCOME_SEMANTIC = "net_income_attributable_to_parent"` (Form B 02-DN Line Code 61).
   - Distinguished Line 60 (`net_profit_after_tax_total`, consolidated total profit including non-controlling interest) from Line 61 (`net_income_attributable_to_parent`, equity holders of parent).
   - Reconciled prior P2-C2C semantic mismatch: GAS FY2025 net income correctly extracted as Line 61 (`11,414,339,911,686` VND) instead of Line 60 (`11,571,631,226,008` VND).
   - VRE FY2025 net income confirmed as Line 61 (`6,445,924` triệu VND = `6,445,924,000,000` VND).

3. **Interest-Bearing Debt Component Aggregation**:
   - Dynamically aggregates short-term borrowings (Line 320) + long-term borrowings (Line 338) into `total_interest_bearing_debt`.
   - Fails closed with `DEBT_COMPONENT_MISSING` if either balance sheet component is missing.

4. **Integration & Production Runner Generalization**:
   - Refactored `governed_financial_evidence_extraction.py` and `tools/run_p2c2_corporate_evidence_onboarding.py` to remove issuer-specific extraction recipes (`EXTRACTION_ORCHESTRATION_SPECS`).
   - All 16 facts (8 GAS + 8 VRE) extracted and canonicalized generically with 100% verified citation lineage.
   - Emitted deterministic artifact to `operations-review/p2d-generic-financial-template-onboarding-20260819/`.

## 2026-08-19 - Phase 2-C2C Governed Evidence Lineage Correction (GAS + VRE) Complete

`P2C2C_GOVERNED_EVIDENCE_LINEAGE_CORRECTION = COMPLETE_LOCAL` (`official_document_acquisition.py`, `official_document_qualification.py`, `governed_financial_evidence_extraction.py`, `tools/run_p2c2_corporate_evidence_onboarding.py`, `push = NO`).

1. **Defect Remediation & Governed Lineage Architecture**:
   - P2-C2 audit established `PRODUCTION_FACT_SOURCE = MANUALLY_EMBEDDED_FACTS` with 0/16 persisted citation lineage.
   - P2-C2C established full governed pipeline: `admitted official route -> official_document_acquisition -> governed retained document -> persisted document qualification -> governed OCR sidecar -> persisted citation observations -> generic_financial_canonicalizer -> multi_period_financial_panel -> deterministic corrected P2-C2C artifact`.
   - Replaced all manual fact embedding with dynamic verification and line-item extraction against persisted OCR sidecars (`derived/annual_financial_ocr_materialization_v1/`).

2. **Generic PDF MIME Sniffing**:
   - Added generic `%PDF` magic bytes sniffing to `official_document_acquisition.py` for `application/octet-stream` responses.
   - Preserves `reported_content_type` and enforces strict registry, size, and hash validation gates without ticker-specific branches.

3. **Standalone Persisted Document Qualification & Dynamic Extraction**:
   - Created `official_document_qualification.py` establishing `DocumentQualificationRecord` and `QUALIFIED_RETAINED_FINANCIAL_STATEMENT`.
   - Created `governed_financial_evidence_extraction.py` to scan OCR text, locate accounting line items, and run verified extraction without hardcoded production numbers.
   - Added AST-based anti-regression test ensuring zero prohibited financial literals in `run_p2c2_corporate_evidence_onboarding.py`.

4. **Multi-Period Panel & Semantic Labeling**:
   - Re-verified multi-period panel integration for GAS and VRE. Explicitly labeled 2025 ROE derived proxy metric as `ENDING_EQUITY_ROE_PROXY` to distinguish from average-equity ROE.
   - Historical commit `273445c5f4ed219ba4167c115b641006f18c2ab1` and old artifact `c8457f81fe104bb4` preserved as historical audit evidence and marked `SUPERSEDED_NONAUTHORITATIVE_MANUAL_LINEAGE_ARTIFACT`.
   - Emitted deterministic corrected artifact to `operations-review/p2c2-governed-financial-evidence-onboarding-20260819/`.

## 2026-08-19 - Phase 2-C2 Bounded Financial Evidence Onboarding (GAS + VRE) [SUPERSEDED BY P2-C2C]

`P2C2_GAS_VRE_ONBOARDING = COMPLETE_LOCAL` (`tools/run_p2c2_corporate_evidence_onboarding.py`, `push = NO`).

1. **Bounded Corporate Evidence Onboarding (GAS & VRE)**:
   - Onboarded FY2025 audited consolidated annual financial statements for `GAS` (`www.pvgas.com.vn`, SHA-256 `b1cfb676...`) and `VRE` (`ir.vincom.com.vn`, SHA-256 `85b250e9...`).
   - Sourced strictly via newly promoted and host-narrowed official-source routes under `issuer_ir`.
   - Verified 100% document qualification (`QUALIFIED_RETAINED_FINANCIAL_STATEMENT`), audited by Deloitte Vietnam.

2. **Zero Ticker-Specific Materializer Invariant**:
   - `NEW_TICKER_SPECIFIC_MATERIALIZER_COUNT = 0`.
   - Extracted 16 canonical facts (8 per issuer) using existing OCR sidecar primitives (`annual_financial_ocr_materialization.py`).
   - Canonicalized 100% through generic dictionary pipeline (`generic_financial_canonicalizer.py`).
   - Multi-period panel integration verified (`multi_period_financial_panel.py`) with complete derived financial ratios (ROE, Net Debt, Debt-to-Equity, Cash Flow/Net Income).

3. **Preservation of Historical Negative Proof & Unpromoted Cohort**:
   - Historical negative proof in `operations-review/p2c-financial-evidence-scale-out-20260819/` preserved intact.
   - P2-C2 evidence and readiness report emitted to `operations-review/p2c2-financial-evidence-onboarding-20260819/` (`p2c2_gas_vre_onboarding:c8457f81fe104bb4d0fd198a21c73be6dfd17f35f18880074cdb264621328088`).
   - `MWG` (`NOT_READY_REDIRECT_CHAIN`) and `VIC` (`NOT_READY_REPRODUCIBILITY`) remain fail-closed and unpromoted.


## 2026-08-19 - Phase 2-D2C Generic Per-Host Document Authority Scope Correction Complete

`P2D2C_AUTHORITY_SCOPE_CORRECTION = COMPLETE_LOCAL` (`official_source_registry.py`, `config/official_source_registry.json`, `push = NO`).

1. **Defect & Generic Correction**:
   - P2-D2 verification discovered that the shared `issuer_ir` source model broadened document authority across all 8 declared `issuer_ir` document types for newly added hosts.
   - P2-D2C implemented generic, data-driven per-host document narrowing via `host_document_types` in `official_source_registry.py`.
   - Constrained `www.pvgas.com.vn` (GAS) and `ir.vincom.com.vn` (VRE) strictly to `audited_annual_financial_statements` only. All other `issuer_ir` document classes are refused with `document_type_not_allowed_for_host`.

2. **Backward Compatibility & Invariants**:
   - Existing unconstrained `issuer_ir` hosts without `host_document_types` entries preserve exact source-level behavior.
   - `MWG` (`NOT_READY_REDIRECT_CHAIN`) and `VIC` (`NOT_READY_REPRODUCIBILITY`) remain unpromoted / refused.
   - P2-C corporate evidence acquisition wave is not resumed; no financial PDFs retained, extracted, or canonicalized.

## 2026-08-19 - Phase 2-D2 Bounded Official Source Registry Promotion (GAS + VRE) Complete

`P2D2_BOUNDED_OFFICIAL_SOURCE_REGISTRY_PROMOTION = COMPLETE_LOCAL` (`config/official_source_registry.json`, `push = NO`).

1. **Exact-Host Promotion (GAS & VRE)**:
   - Promoted `www.pvgas.com.vn` (PV GAS) and `ir.vincom.com.vn` (Vincom Retail) to `issuer_ir.allowed_hosts` in `config/official_source_registry.json`.
   - Permitted document class scoped strictly to `audited_annual_financial_statements`.
   - Provenance recorded in `host_admission_rule` from first-party IR disclosure routes evaluated in P2-D1C.

2. **Unpromoted Cohort Preserved**:
   - `MWG`: Preserved as `NOT_READY_REDIRECT_CHAIN` (document delivery JS-rendered; PDF storage host unknown).
   - `VIC`: Preserved as `NOT_READY_REPRODUCIBILITY` (HTTP 403 access denial on primary IR listing page).

3. **Authority & Lifecycle Invariant**:
   - Establishes official source route authority only; does not retain documents, extract facts, or canonicalize financial evidence.
   - P2-C corporate evidence acquisition wave is not resumed.

## 2026-08-19 - Phase 2-C Official Financial Evidence Scale-Out / First Corporate Acquisition Wave Complete

`P2C_OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT = COMPLETE_LOCAL` (`tools/run_p2c_corporate_evidence_scale_out.py`, `push = NO`).

1. **Positive Entity Classification Enforcement**:
   - Strictly enforced positive entity classification authority (`config/ticker_entity_profiles.csv`) per `financial_entity_applicability.py` and `docs/AI_RULES.md`.
   - Out of 1,660 listed equity candidates in C.1, exactly 13 are positively profiled as `corporate`.
   - Excluded 9 already-covered issuers in P2-A/P2-B (`FPT`, `HPG`, `NVL`, `PAN`, `PNJ`, `POW`, `PVD`, `QNS`, `VNM`) and 7 financial intermediaries (`BID`, `MBB`, `TCB`, `VCB`, `SSI`, `BVH`, `EVF`).
   - Yielded an authority-safe uncovered cohort of 4 ordinary corporates: `GAS`, `MWG`, `VIC`, `VRE`.
   - Quantified `COHORT_SHORTFALL_DUE_TO_ENTITY_CLASSIFICATION = 16` against the requested 20-issuer target. Preserved 1,640 `UNKNOWN_ENTITY_CLASS` listed equities as a future classification-coverage gap.

2. **Governed Sourcing & Failure Taxonomy**:
   - Evaluated official disclosure routes across official exchange and official IR sources for all 4 cohort issuers.
   - Enforced closed-world registry gate (`official_source_registry.py`), classifying unadmitted IR hosts fail-closed under `SOURCE_DISCOVERY` blocker (`OFFICIAL_LOCATOR_NOT_FOUND`).

3. **Zero Ticker-Specific Production Code Invariant**:
   - `NEW_TICKER_SPECIFIC_MATERIALIZER_COUNT = 0`.
   - Zero per-ticker Python materializers added to the repository.

4. **Validation Artifact & Metrics**:
   - Emitted deterministic artifact with content hash `f9ab8e98d2e691d80615990deba1e93272d351984a27f3eed5a6e67518db2c71` and `READINESS_REPORT.md` under `operations-review/p2c-financial-evidence-scale-out-20260819/`.
   - All tests passing (`tests/test_p2c_financial_evidence_scale_out.py` 5/5, full bounded regression suite 131/131).

5. **Next Roadmap Milestone**:
   - **Phase 2-D BCTC Template Recognition & Governed Official Document Expansion**.

## 2026-08-19 - Phase 2-B Generic Financial Statement Canonicalization & Retained-Evidence Scale-Out Complete

`P2B_GENERIC_FINANCIAL_CANONICALIZATION = COMPLETE_LOCAL` (`generic_financial_canonicalizer.py`, `push = NO`).

1. **Ticker-Agnostic Canonicalization Engine**:
   - Implemented `generic_financial_canonicalizer.py` and CLI generator `tools/generate_generic_canonicalization_artifact.py`.
   - Replaces hardcoded per-ticker branching with dictionary-driven taxonomy normalization over Vietnamese VAS/IFRS circular 200 accounting line items.
   - Emits canonical financial facts with immutable `TemporalField` envelopes, source document SHA-256, citation ID, and evidence ID.

2. **Classification & Audit of Retained Document Corpus**:
   - Inspected 21 retained official documents across all manifests.
   - Categorized candidates: 13 `GENERICALLY_CANONICALIZABLE`, 3 `SECTOR_SPECIALIZED` (bank/securities statements), 3 `INSUFFICIENT_EVIDENCE` (AGM non-financial documents, incomplete annual report package), 2 `INSUFFICIENT_MAPPING` (PNJ debt note under review), 0 `TICKER_SPECIFIC_ONLY`.
   - Achieved `GENERIC_CANONICALIZATION_RATE = 100.00%` (60/60 qualified facts across 8 corporate issuers).

3. **Legacy Materializer Role Audit & Migration**:
   - Formally audited historical per-ticker materializers:
     - `fpt_fy2025_official_financial_materialization.py`: `GENERICALLY_SUPERSEDED`
     - `qns_pow_official_financial_materialization.py`: `GENERICALLY_SUPERSEDED`
     - `targeted_multi_period_official_financial_evidence.py`: `GENERICALLY_SUPERSEDED`
     - `legacy_qualified_cohort_recovery.py`: `HISTORICAL_LEGACY`
     - `ssi_official_financial_materialization.py`: `SECTOR_SPECIALIZED`
     - `annual_financial_ocr_materialization.py`: `GEN_EXTRACTION_ENGINE`
   - Retained backward compatibility and regression correctness without parallel authority paths.

4. **Validation & Retained Artifact**:
   - Emitted validation artifact with deterministic content hash `256f374c08df327b3759d027022ec2cefd40a4c8b8f82d2c33122c34b29e94bf` under `operations-review/p2b-generic-financial-canonicalization-20260819/`.
   - Preserved 100% equivalence on regression cohort (HPG, PVD, VNM, FPT, QNS, POW, PAN, NVL, SSI, VCB).
   - Test suite `tests/test_generic_financial_canonicalizer.py` (5/5 passed, bounded suite 130/130 passed).

5. **Next Roadmap Gate**:
   - Financial statement canonicalization engine verified as `READY_FOR_FINANCIAL_EVIDENCE_SCALE_OUT`.
   - Recommended next milestone: **Phase 2-C Full Financial Evidence Corpus Scale-Out & BCTC Template Parser**.

## 2026-08-19 - Phase 2-A Multi-Period Financial Fact Panel & Sector Applicability Contract Complete

`P2A_MULTI_PERIOD_FINANCIAL_FACT_PANEL = COMPLETE_LOCAL` (`multi_period_financial_panel.py`, `push = NO`).

1. **Dimensional Provenance & Period Distinction**:
   - Implemented `multi_period_financial_panel.py` and CLI generator `tools/generate_multi_period_financial_panel_artifact.py`.
   - Distinctly models `instant` (balance sheet) vs `duration` (income statement, cash flow) facts and `annual` vs `quarterly` reporting frequencies.
   - Preserves currency (`VND`, `USD`) and statement scope (`consolidated`, `separate`) without silent conversion or mixing.

2. **Deterministic Sector Applicability Matrix**:
   - Formalized entity archetypes: `corporate`, `bank`, `securities`, `insurance`, `finance_company`, `unknown`.
   - Strictly blocks financial intermediaries (`bank`, `securities`) from inappropriate corporate debt ratios (`debt_to_equity`, `net_debt`) and EBITDA concepts (`NOT_APPLICABLE`).
   - Integrates fail-closed Altman Z'-score applicability for manufacturing vs non-manufacturing corporates.

3. **Bounded Derived Accounting Relationships**:
   - Computes bounded accounting metrics (YoY Net Income and OCF growth, cash flow coverage of net income, debt/equity and net debt for corporates).
   - Preserves strict fail-closed governance: missing inputs isolate to dependent metrics; valuation multiples, intrinsic value models, price targets, and strategy rankings remain strictly blocked.

4. **Multi-Period Validation Artifact**:
   - Composed 60 qualified facts across 10 representative issuers (`HPG`, `VNM`, `PVD`, `POW`, `FPT`, `NVL`, `PAN`, `QNS`, `SSI`, `VCB`) with content hash `33cfa0a4e5ee114e31b1a381aa63cd7e4d3943fd969ff6449596173271678aba`.
   - Validation report retained in `operations-review/p2-multi-period-financial-panel-20260819/READINESS_REPORT.md`.
   - Test suite `tests/test_multi_period_financial_panel.py` (12/12 passed).

5. **Next Roadmap Gate**:
   - Multi-period fundamental research panel verified as `READY_FOR_MULTI_PERIOD_FUNDAMENTAL_RESEARCH`.
   - Recommended next milestone: **Phase 2-B Financial Statement Scale-Out & BCTC Canonicalization**.

## 2026-08-19 - Phase 1 Feature Store Normalization & Multi-Session Cross-Sectional Export Contract Complete

`P1_MULTI_SESSION_CROSS_SECTIONAL_EXPORT = COMPLETE_LOCAL` (`cross_sectional_export.py`, `push = NO`).

1. **Semantic Feature Taxonomy Normalization**:
   - Resolved the foreign flow taxonomy defect by strictly isolating `dnse.foreign_buy_value`, `dnse.foreign_sell_value`, and `dnse.foreign_net_value` under `foreign_flow_features` rather than misrepresenting them as financial statement features.
   - Formalized semantic domains: `market_features`, `foreign_flow_features`, `financial_statement_features`, `corporate_action_features`, and `qualification_and_capabilities`.
   - Maintained immutable field-level `TemporalField` envelopes attached to every feature record.

2. **Deterministic Cross-Sectional & Multi-Session Export Contract**:
   - Implemented pure, vectorized session and multi-session export builders (`build_cross_sectional_session_export`, `build_multi_session_cross_sectional_export`).
   - Enforced zero lookahead and zero silent forward-fill: missing observations remain missing.
   - Evaluated 3,250 canonical candidates across 10 retained market sessions (2026-07-29 to 2026-08-11), emitting 8,931 normalized observations with content hash `bb0cafa4417471b0c1657eebd3e9c6b16ce20be601aa00b7d9a64cfc3f499256`.

3. **Strict Invariant Governance**:
   - Preserved `RAW_AS_TRADED = NOT_PROMOTED`, `ACTIVE_UNIVERSE = UNKNOWN`, `QUALIFIED_LIQUIDITY_INPUTS = NO`, and `POSITION_SIZING_IS_SAFE = NO`.
   - Verified that one unavailable feature isolates to `FreshnessState.MISSING` without corrupting candidate records or unrelated features.

4. **Next Roadmap Gate**:
   - Multi-session cross-sectional research dataset verified as `READY_FOR_SHADOW_CROSS_SECTIONAL_RESEARCH`.
   - Recommended next milestone: **Phase 2 — Multi-Period Fundamentals & Sector Normalization**.

## 2026-08-19 - First Market-Wide Deterministic Analysis / Research Artifact V1 complete

`FIRST_MARKET_WIDE_DETERMINISTIC_ANALYSIS_ARTIFACT = COMPLETE_LOCAL` (`market_analysis_artifact.py`, `push = NO`).

1. **Artifact Foundation & Composition**:
   - Implemented `market_analysis_artifact.py` and CLI generator `tools/generate_first_market_wide_research_artifact.py`.
   - Composed the full C.1 candidate universe (3,250 candidates: 1,660 listed equity candidates, 1,590 unclassified security groups) with vectorized technical indicators (`market.close`, `market.return_1d`, `market.ma_3/5/20`, `market.volatility_3/20`, `market.volume_ratio`, `legacy.rel_vol`) and foreign flows (`dnse.foreign_net_value`).
   - Bound field-level `TemporalField` envelopes across all 39,000 field instances.

2. **Explicit Universe & Authority Invariants**:
   - Emits for `CANONICAL_CANDIDATE_UNIVERSE` without falsely asserting `ACTIVE_UNIVERSE` authority (`ACTIVE_UNIVERSE = UNKNOWN` fail-closed across 100% of candidates).
   - Price basis remains `RAW_AS_TRADED_NOT_PROMOTED`; unpromoted price fields fail closed as `pit_eligible=False` (`UNQUALIFIED_PRICE_BASIS`).
   - Liquidity and sizing remain strictly blocked: `QUALIFIED_LIQUIDITY_INPUTS = NO`, `POSITION_SIZING_IS_SAFE = NO`, `market_liquidity_eligible = False`, `execution_sizing_eligible = False`.
   - One missing field (e.g. unobserved market rows or missing foreign flow) isolates to `FreshnessState.MISSING` without invalidating the instrument candidate record or other features.

3. **Deterministic Verification & Validation Report**:
   - Artifact generated and validated with byte-stable SHA-256 content hash `09c662b20944d25e77671a2972e5d515345310f17b585c6fa293241db5eb995d`.
   - Validation report retained in `operations-review/p1-first-market-wide-deterministic-analysis-artifact-20260819.md`.
   - Test suite `tests/test_market_analysis_artifact.py` (7/7 passed).

4. **Next Roadmap Gate**:
   - With the first deterministic market-wide research artifact established, Phase 0 is complete and Phase 1 (Research Evidence Layer & Feature Store Normalization) is unlocked.
   - Recommended next milestone: **Phase 1 Feature Store Normalization & Multi-Session Cross-Sectional Export Contract**.

## 2026-08-19 - P0-B.2D Scoped Promotion Review & P0-B Terminal Closeout

`P0-B = TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION` (`push = NO`).

1. **Promotion Review Verdict: NO_AUTHORITY_PROMOTION**:
   - The complete retained volume, value, board composition, and reconciliation evidence corpus across all candidate definitions ($C_1$–$C_5$), empirical scale relations, residual classes, and downstream use cases was evaluated.
   - No daily volume or traded-value field qualifies for promotion to market-wide turnover, market liquidity, or execution/position sizing authority.

2. **Explicit Fail-Closed Negative Proofs**:
   - `QUALIFIED_LIQUIDITY_INPUTS = NO` (unconditionally assigned across all records).
   - `POSITION_SIZING_IS_SAFE = NO` (unconditionally assigned across all records).
   - $C_5 = 10 \times G_1$ remains strictly `ScaleStatus.EMPIRICAL_CANDIDATE` with `semantic_unit_interpretation = UNKNOWN`. The $\times 10$ factor is discovered from data clustering and is NOT authoritative provider or exchange specification. Correlation is not semantic authority.
   - 67 residuals (62 positive multiples of 100, 5 negative deltas of -4) remain unresolved and prohibit mathematical equality certification.
   - Daily traded value remains unevidenced and unpromoted (`OBSERVED_ABSENT` from DNSE daily OHLC 7-key shape). Missing independent measurement cannot be turned into evidence.

3. **Preservation of Shadow / Descriptive Uses**:
   - Within-series relative volume (`legacy.rel_vol`), provider-scoped display (`DISPLAY`), provider-scoped analytics (`PROVIDER_SCOPED_ANALYTICS`), and empirical shadow scale relation ($C_5$) remain valid for shadow/research analytics where `qualified_liquidity_inputs = False`.

4. **P0-B Closeout & Next Roadmap Gate**:
   - P0-B is formally closed at terminal state `TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION`.
   - With P0-B closed, P0-C (`P0-C.1`, `P0-C.2`, `P0-C.3`) complete locally, and `P0-A.3E` Part A complete / Part B blocked, the exact next actionable roadmap milestone is **First Market-Wide Deterministic Analysis/Research Artifact**.

## 2026-08-19 - P0-C.3 Field-Level Freshness / As-Of Retrofit V1 complete

`P0-C.3 = COMPLETE_LOCAL` (`field_temporal_contract.py`, `push = NO`).

1. **Pure Deterministic Field-Level Temporal Contract**:
   - Implemented `field_temporal_contract.py` defining explicit `TemporalField` containers that bind `observed_at`, `as_of`, `freshness_status`, `pit_eligible`, `pit_status`, `stale_reason`, `domain`, and `lineage` directly to individual field values.
   - Six explicit freshness states: `current`, `expiring`, `stale`, `historical`, `missing`, `unknown`. Cadence/grace is domain-driven (via `freshness_history.RULES`); naive `date < today => stale` is strictly forbidden.
   - Four PIT states: `QUALIFIED`, `HISTORICAL_ONLY`, `LOOKAHEAD_VIOLATION`, `UNQUALIFIED_PRICE_BASIS`, `TIMESTAMP_MISSING_OR_INVALID`, `KNOWLEDGE_CUTOFF_MISSING`.

2. **Authoritative Producer Boundary Retrofit**:
   - `CanonicalRecord` in `market_data_contracts.py` now supports bound `temporal_fields` and `with_temporal_evaluation(reference_at=..., knowledge_cutoff=...)`.
   - `canonicalize_market_record` deterministically evaluates field-level temporal envelopes when reference time is provided.
   - `market_feature_store.py` provides `build_temporal_feature_records`, binding calculated feature columns to explicit field-level temporal envelopes.

3. **No Promotion / Fail-Closed Invariants Preserved**:
   - Price fields without positive `RAW_AS_TRADED` or `PIT_OBSERVED` authority remain strictly `pit_eligible=False` (`UNQUALIFIED_PRICE_BASIS`).
   - Future/lookahead dates relative to `reference_at` or `knowledge_cutoff` are rejected with `LOOKAHEAD_VIOLATION` / `future_*_rejected`.
   - Stale-but-valid data retains exact numeric values while setting `is_actionable=False` and recording explicit `stale_reason`.
   - `RAW_AS_TRADED` remains **NOT_PROMOTED**; liquidity/volume authority remains unpromoted.

4. **Next Roadmap Gate**:
   - With `P0-C.1`, `P0-C.2`, and `P0-C.3` complete locally, the canonical universe boundary and freshness layer are established.
   - Next actionable focus: `P0-B.2D` (volume authority promotion review) / first market-wide deterministic analysis artifact.

## 2026-08-19 - P0-A.3E prospective multi-session evidence collection complete; event-window qualification blocked

`P0-A.3E = PART_A_COMPLETE_EVIDENCE_ACQUIRED; PART_B_BLOCKED_PENDING_QUALIFIED_EX_DATE`.

1. **A3E Part A Prospective Multi-Session Collection is COMPLETE_EVIDENCE_ACQUIRED**:
   - Distinct multi-session completed-bar (`bc`) evidence retained across Sessions 1–4 under lineages `70a7904` and `4150f02c`.
   - Per-symbol evidence matrix: Session 1 (HPG PASS, VCB PASS); Session 2 (HPG BLOCKED, VCB PASS); Session 3 (HPG BLOCKED, VCB PASS); Session 4 (HPG PASS, VCB BLOCKED).
   - Partial sessions (`SESSION_PARTIAL`) and honest `BLOCKED_NO_COMPLETED_EVENT` outcomes are verified contract-compliant and do not invalidate evidence or indicate defects.
   - No further live prospective WebSocket acquisition is required for A.3E.

2. **Part B Event-Window Price-Basis Qualification is BLOCKED_PENDING_QUALIFIED_EX_DATE**:
   - Requires explicit official corporate-action ex-date evidence and executed distribution status.
   - Inferring ex-date from record date or fabricating adjustment factors remains strictly forbidden.
   - `RAW_AS_TRADED` remains **NOT_PROMOTED**.
   - `OFFICIAL_CLOSED_BAR_FINALITY_DOES_NOT_BY_ITSELF_PROVE_RAW_AS_TRADED` and `NO_REVISION_OBSERVED != IMMUTABLE` remain binding.

3. **Critical Path & Next Milestone**:
   - With A.3E Part A complete and Part B safely fail-closed, the next actionable roadmap milestone is `P0-C.3` (field-level freshness/as-of retrofit) per critical path governance.

## 2026-08-18 - P0-B.2B1 VALIDATED_SHADOW result; C1-C4 BLOCKED confirmed on full corpus

`P0-B.2B1 = VALIDATED_SHADOW_SCALE_RELATION_WITH_UNRESOLVED_RESIDUALS`.

1. **C1-C4 confirmed BLOCKED on full corpus**: All four original candidates fail across the complete
   40-session / 35,231-symbol-session corpus (C1 exact=0/35,231 = 0.0000%; C2=2; C3=1; C4=2).
   Root cause is exclusively unit-scale mismatch (C1-C4 are missing a ×10 factor) plus composition
   mismatch for C2-C4 (include boards that contribute nothing to daily_v).

2. **C5 = 10 × board_G1_quantity** matches 35,164/35,231 = **99.8098%** exactly over the full
   40-session retained corpus. Determinism verified: two independent runs produce identical content
   hash `ac5942913291c9ac8efb73d77a3b97dbb9068f111c8c6996422b66ef4e2b183d`.

3. **Scale is EMPIRICAL_CANDIDATE only.** The ×10 factor must NOT be encoded as "Trades quantity
   unit = 10 shares". `semantic_unit_interpretation = UNKNOWN` is binding.
   `scale_status = EMPIRICAL_CANDIDATE`. No authority promotion from this milestone.

4. **67 residuals remain unresolved** (0.19% of eligible sessions):
   - 62 `POSITIVE_DELTA_MULTIPLE_OF_100` across 53 symbols — consistent with a small number of G1
     executions present in OHLC daily_v but absent from the canonical Trades corpus; true root cause
     NOT established.
   - 5 `NEGATIVE_DELTA_MINUS_4` confined to SHB and VIX only across 5 trading dates.
   - 0 `OTHER`.
   - Zero overlap with Task-160's 27 known REMAINING_FAILED units — that hypothesis ruled out.

5. **Provenance gap recorded**: canonical Trades source commit
   `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02` is `SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY`.
   This does not invalidate the retained evidence but must remain visible for any promotion review.

6. **Not QUALIFIED_VOLUME_COMPOSITION and not QUALIFIED_LIQUIDITY_INPUTS.**
   `qualified_liquidity_inputs = False` unconditionally from this milestone.
   P0-B.2C (va/turnover) is NOT implemented. P0-B.2D promotion review is the required next step.
   P0-B is NOT closed. `P0-A.3E = ACTIVE_MULTI_SESSION_COLLECTION` is preserved and untouched.

## 2026-08-18 - P0-B.2A_B2B terminal verification complete; P0-B blocked

`P0-B.2A_B2B` (DNSE Daily Volume Composition Reconciliation V1) is **BLOCKED**.
Terminal verification on a real 1-day canonical trades vs OHLC corpus (944 eligible symbol-sessions) found 60 discriminating sessions. Of these 60, zero yielded an exact daily `v` match across all candidate compositions (`C1`-`C4`). The result was 60 `CONFLICTING` and 884 `INSUFFICIENT_DISCRIMINATION` sessions.
Volume semantics are completely unpromoted. P0-B is NOT closed. `QUALIFIED_LIQUIDITY_INPUTS` are NOT emitted. `P0-B.2C` (va/turnover) was explicitly scoped out and not implemented.

## 2026-08-18 - Isolated Bulk Acquisition Framework V1 completed; independence from P0-B confirmed

`ISOLATED_BULK_ACQUISITION_FRAMEWORK_V1 = COMPLETE_LOCAL` (branch `feature/isolated-bulk-acquisition-framework-v1`).

1. **Independent Lanes**: `ISOLATED_BULK_ACQUISITION_FRAMEWORK_V1` for official documents and `P0-B` market-volume reconciliation are independent lanes. The document acquisition framework is not a prerequisite for P0-B.
2. **Acquisition vs Qualification Separation**: Raw document acquisition (`data-landing/`) never promotes evidence to financial-fact, observation, feature, or provider authority. `RawDocumentRecord.qualification_state = "unknown"` remains unconditionally assigned.
3. **No Cross-Talk with Existing Pillar-B**: The framework operates in strict path and logical isolation from existing `official_document_acquisition.py` / `official_document_store.py` production infrastructure; it does not replace, wrap, or modify them.

## 2026-08-18 - Cross-Sectional Deterministic Reconciliation approved for P0-B market-volume semantics

`P0-B_QUALIFIED_VOLUME_LIQUIDITY_QUALIFICATION_DESIGN`.

1. **Approved Qualification Method**: Cross-Sectional Deterministic Reconciliation across complete eligible cohorts and discriminating sessions (sessions with distinct continuous, put-through, and odd-lot activity) is the approved qualification method for unresolved DNSE daily `v`/`va` market-composition semantics.
2. **Single-Ticker / Single-Session Insufficiency**: A single ticker/session coincidence is explicitly insufficient for authority promotion.
3. **Exchange/Regime Awareness**: Trading-phase classification must be exchange/instrument/regime aware, not a universal hard-coded clock assumption.
4. **Missing Observation Treatment**: Known missing observations remain explicit and are never imputed as zero.
5. **Closeout Boundary**: P0-B closeout emits `QUALIFIED_LIQUIDITY_INPUTS` (volume, trading value, turnover, participation basis). It explicitly does **NOT** establish `POSITION_SIZING_IS_SAFE`.

## 2026-08-18 - A.3D keepalive correction live-validated; A.3E Session 1 acquired

`P0-A.3D = COMPLETE_LOCAL_NO_PUSH` remains governed `EXPERIMENT_SHADOW_ONLY`. Corrective commit
`ecb2c6c17039f123e7e8fe5b7dd53604c2893f58` fixed the verified defect where routine `ping`
keepalive/control traffic could exhaust the semantic receive budget before a closed-bar content
opportunity. `ping` remains non-secret observable and receives `pong`, but consumes no semantic
control, ignored-non-`bc`, or total semantic-frame budget; the absolute session deadline remains
the boundedness authority. This is an implementation safety property, not production or price
authority.

The subsequent human-governed A.3E session
`2026-08-18-postfix-ecb2c6c` is `SESSION_EVIDENCE_ACQUIRED`, with accepted HPG and VCB evidence
at the corrective source lineage. This validates the bounded post-fix capture path only. It does
not promote `RAW_AS_TRADED`, official closed-bar finality, revision immutability, PIT safety, or
registry/provider authority. `OFFICIAL_CLOSED_BAR_FINALITY_DOES_NOT_BY_ITSELF_PROVE_RAW_AS_TRADED`
and `NO_REVISION_OBSERVED != IMMUTABLE` remain binding.

`P0-A.3E = ACTIVE_MULTI_SESSION_COLLECTION`, with two separate substreams:

- **A. `PROSPECTIVE_MULTI_SESSION_COLLECTION`** — `OPERATIONAL / SESSION_1_ACQUIRED`.
- **B. `EVENT_WINDOW_PRICE_BASIS_QUALIFICATION`** — `BLOCKED_PENDING_QUALIFIED_EX_DATE`.

No ex-date may be inferred from record date. Until a qualifying official ex-date exists, the
event-window component remains fail-closed; no A.3E result opens `P0-A.4` or `P0-B`.

## 2026-08-18 - P0-A.3C evidence acquired; P0-A.3D governed prospective collector integrated locally

`P0-A.3C_DNSE_PROSPECTIVE_WEBSOCKET_PAYLOAD_SEMANTIC_EVIDENCE_ACQUISITION =
COMPLETE_EVIDENCE_ACQUIRED`. The retained human-run evidence package at
`C:\Projects\StockLookup\operations-review\p0-a3c-live-20260818-090834` independently validates
`PASS_EVIDENCE_ACQUIRED` on HPG attempt 2 and VCB attempt 2, with final state
`PASS_EVIDENCE_ACQUIRED_BOTH_SYMBOLS`. Both records are real WebSocket `ohlc_closed.1.json`
completed-bar payloads with `T = "bc"`, requested symbol/resolution correspondence, collector
execution-ID linkage, deterministic hash/replay verification, and no source-baseline mutation.
Attempt 1 for each symbol is correctly retained as `BLOCKED_NO_COMPLETED_EVENT`; no observation
was fabricated.

The HPG/VCB payloads contain the documented OHLC-Closed required fields and empirically reconcile
that `tradingDate` and `tradingSessionId` are optional/absent in these messages. This verifies
current protocol/payload shape only. It does **not** establish `RAW_AS_TRADED`, non-revision,
corporate-action behavior, board/lot semantics, historical REST PIT safety, source registry
authority, or any provider/production authority. `RAW_AS_TRADED = NOT_PROMOTED` remains binding.

`P0-A.3D_GOVERNED_PROSPECTIVE_COLLECTOR_INTEGRATION = COMPLETE_LOCAL_NO_PUSH` at local commit
`3291ed8afda3c6aba8100f77bf5c88a2915801fd` (parent
`77bfe95f203ea87aa80ffbc5918215234f3fcbc7`). It moved only the byte-baselined A.3C shadow
collector/test prior art into tracked source and preserved `EXPERIMENT_SHADOW_ONLY`. The bounded
hardening is limited to request/payload correspondence rejection, evidence-output collision
refusal, non-secret control/ignored-type/timeout observability, separated bounded receive budgets,
and a total wall-clock cap. No live call, credentials, daemon, reconnect, raw-lake integration,
RawObservation redesign, database write, registry change, or authority promotion occurred.

**Next gate:** `P0-A.3E` — **Prospective Multi-Session / Event-Window Price-Basis Qualification**.
It must explicitly separate (A) bounded, human-owned prospective evidence collection from (B)
event-window qualification, which can proceed only when a qualifying official corporate-action
ex-date is actually evidenced. It may not infer an ex-date, require a future event to exist, or
fabricate event evidence. Without that evidence, the event-window portion is blocked/fail-closed.
No daemon or unattended collector is authorized. Critical path: `P0-A.3D` → `P0-A.3E` →
`P0-A.4` / `P0-B` → `P0-C.3`.

## 2026-08-17 - P0-A.3B closed; P0-A.3C prospective WebSocket evidence gate opened

`P0-A.3B_DNSE_PROSPECTIVE_PIT_PRICE_AUTHORITY_ARCHITECTURE_REVIEW = COMPLETE_READ_ONLY`.
Architecture verdict: `SOURCE_SEMANTICS_BLOCKED`. No code, runtime, provider, registry, or
price-basis authority changed.

**Review findings:**
- No current DNSE price source, feed, or field is authoritative `RAW_AS_TRADED`. The bounded
  DNSE REST OHLC authority remains `ADJUSTED_RETROSPECTIVE`; other REST ticker/session price basis
  remains `UNKNOWN` unless separately bounded-qualified.
- The WebSocket `ohlc_closed` prospective lane remains an `EXPERIMENT/SHADOW`, semantically
  unqualified, non-authoritative, and has zero real retained completed-event observations today.
  Transport speed, first receipt, append-only retention, and timestamp proximity do not establish
  raw/as-traded, adjustment, revision, session/calendar, or odd-lot/board semantics.
- The shadow disposition is `DEFER`: do not reject, promote, port, or reimplement it. Its useful
  future concepts (`logical_bar_identity`, first-observed retention, duplicate-identical handling,
  append-only revision linkage) and identified retention gaps (additive logical/business identity,
  revision linkage, streaming/session reconciliation) are not implementation authorization.
- Prospective qualification cannot retroactively make historical REST OHLC PIT-safe. Raw/as-traded
  price authority and corporate-action adjustment authority remain independent per-use gates.

**Next gate:** `P0-A.3C` — **DNSE Prospective WebSocket Payload Semantic Evidence Acquisition**
is `EVIDENCE_ACQUISITION_NEXT`, `NO_PRICE_BASIS_PROMOTION`, and
`HUMAN_LIVE_EXECUTION_REQUIRED`. Its sole objective is first real retained, non-synthetic DNSE
`ohlc_closed` completed-bar evidence: payload shape, field/symbol identity, units/scaling,
provider/source and receipt timestamps, supplied session fields, and naturally observed
duplicate/revision behavior. Same-day REST-vs-WS comparison may investigate correspondence only;
matching values do not prove `RAW_AS_TRADED`, non-rewriting, or PIT safety.

**Bounded capture and completion conditions:**
- One human/PowerShell-owned bounded foreground launch at operator-selected live timing; no daemon,
  unattended reconnect, polling, or AI-owned background process. Scope is two operator-selected
  eligible liquid `EQUITY` symbols, one supported resolution, and at least one real completed-bar
  payload retained for each symbol. Named tickers are regression examples only; no full session or
  full-universe requirement is inferred.
- Completion requires content/byte identity hash, receipt timestamp, supplied provider/session
  fields retained without invented meaning, deterministic replay/readback, same-day comparison
  recorded with its non-authority caveat, duplicate/revision retention without overwrite if naturally
  observed, and no registry/source-authority promotion or `market_raw_lake` integration.
- RawObservation changes, streaming integration, terminal-session reconciliation, price-basis
  registry changes, corporate-action mutability qualification, `RAW_AS_TRADED`/PIT promotion, and
  post-A.3C gate naming remain explicitly future and unauthorized until real evidence exists.

## 2026-08-17 - Future capability enrichment: macro, microstructure, forensics, and authority governance policy

`FUTURE_CAPABILITY_ENRICHMENT_V2`. Documentation and policy synchronization only.
No code modified, no runtime execution, no data, source, or model authority promoted.

**Durable policy decisions established:**
1. **P0 Critical Path Unchanged**: Proposed analytical and foundation capabilities do not alter
   the active critical path (`P0-A.3D` governed prospective collector integration → `P0-A.3E`
   prospective multi-session/event-window qualification → `P0-A.4`/`P0-B` → `P0-C.3`).
2. **Future Capability Placement without Premature Numbering**: Downstream requirements are
   documented without opening implementation; sub-milestone numbering remains intentionally TBD
   until the respective phase is authoritatively opened.
3. **Sector-Conforming Valuation (Rejection of Universal DCF)**: A universal cross-sector DCF is
   rejected. Candidate valuation model families remain subject to later qualification and
   sector/applicability contracts.
4. **Rejection of Uncalibrated Kelly Sizing**: Kelly sizing from assumed, LLM-generated, or
   uncalibrated probabilities is rejected; it requires empirical, out-of-sample calibrated
   distributions under qualified backtest semantics.
5. **Cross-Cutting Invariants vs Milestones**: Resumable checkpointing/manifests and isolated
   shadow execution/worktrees remain mandatory engineering invariants, not missing milestones.
6. **Three Distinct Authority Classes (Measurement vs Interpretation vs Causal Claim)**:
   - **Measurement**: Observed or deterministically-derived values from qualified inputs (e.g. `VN30F1M_basis = -12.4`, basis percentile).
   - **Interpretation / Hypothesis**: Analytical explanations of what a measurement may mean (e.g. `negative basis may be consistent with hedging demand`). This is an analytical hypothesis, never automatically a deterministic system fact.
   - **Causal / Predictive Claim**: Claims of forward predictive power (e.g. `SBV net injection predicts equities in 2–4 weeks` or `basis predicts market decline`). Requires qualified empirical validation and backtesting.
   - *Rule*: The system must never silently promote measurement → interpretation → causality.
7. **Canonical AI Research Handoff (Research Evidence Packet)**:
   - The canonical governed handoff to the AI research layer remains the **Research Evidence Packet (REP)**; no parallel canonical object called "Research Evidence Bundle" is created.
   - The REP evolves by carrying optional qualified facets (`market_price_context`, `volume_liquidity_context`, `foreign_flow_context`, `market_breadth_context`, `macro_monetary_context`, `derivatives_microstructure_context`, `financial_evidence`, `financial_forensics`, `valuation_context`, `portfolio_risk_context`, `thesis_evidence`, `counter_thesis_evidence`).
   - Each facet preserves its own provenance, freshness/knowledge time, PIT semantics, eligibility state, and reason codes. One BLOCKED facet does not invalidate an unrelated valid use case.
8. **Governed Deterministic Engines as Numerical Authority**:
   - Governed deterministic engines are the **numerical authority** for formalizable production and research metrics (avoiding simplistic statements like "AI does not do math").
   - AI may reason over numbers, compare values, perform exploratory calculations, synthesize evidence, identify contradictions, and generate thesis/counter-thesis arguments.
   - An AI-generated calculation does *not* become an authoritative Stock Lookup fact unless produced or verified through the governed deterministic pipeline. AI must never fabricate target prices, calibrated probabilities, adjustment factors, WACC, growth rates, or causal coefficients.
9. **Per-Use Authority & Readiness (No Global "100% Complete" Blocker)**:
   - Stock Lookup authority is per-use and per-capability, not a single global "100% complete" flag.
   - Each capability is independently eligible when the dependencies required by that specific use case are qualified.
   - Fail-closed behavior is enforced locally at the dependent boundary (e.g. current fundamental facts may be qualified while PIT backtesting is blocked; shadow screening may operate non-authoritatively while portfolio sizing is unavailable) without globally freezing unrelated valid capabilities.
10. **Future Analytical Signals (P1 Macro/Derivatives, P2 Financial Forensics)**:
   - SBV monetary/liquidity context, VN30 derivatives microstructure, and forensic accounting-risk signals (cash conversion, unusual receivables concentration, Altman/Piotroski health scores) are recorded as non-active future capabilities and do not alter the active P0 critical path.
   - Neutral terminology is required for forensics (`accounting_risk_signal`, `other_receivables_asset_concentration`); pejorative or legalistic claims ("rút ruột doanh nghiệp", fraud, manipulation) are strictly forbidden without authoritative legal proof.
11. **Screener Authority Classes**:
   - `SHADOW_RESEARCH_SCREENER` operates for research with explicit provenance, visible UNKNOWN/BLOCKED semantics, and no claim of authoritative actionability.
   - `AUTHORITATIVE_LIVE_ANALYSIS` remains blocked until required P0 price, volume/liquidity, and
     universe authorities are qualified; a later opened capability must also satisfy its
     output-specific gates.

## 2026-08-17 - P0-A.3A PIT price reconstruction contract integrated to local main (P0-A.3 IN PROGRESS)

`P0-A.3A_PIT_PRICE_RECONSTRUCTION_CONTRACT_V1`. Integrated into local `stock-core-private`
main (commit `e360adbbc801650e6ca4c7e324f9ffcf2f32f85b`, parent `f65dc4cb07a28623523e4a9f3672f1d0537a902e`, `push = NO`).
Independent read-only safety audit and narrow re-audit both completed (`P0A3A_SAFE_FOR_REAL_UNIVERSE_VALIDATION`).
No network calls, no runtime/DB writes.

**Committed files:**
- `pit_price_reconstruction_contract.py`
- `tests/test_pit_price_reconstruction_contract.py`

**Key semantics established:**
1. **Mechanical Mode Isolation & Explicit Actionability:**
   - `PIT_AS_KNOWN` and `RETROSPECTIVE_RESTATED` are mechanically separated across output schemas and universe summaries.
   - Every record explicitly carries `pit_backtest_eligible: bool`, true *only* when `mode == PIT_AS_KNOWN and verdict == QUALIFIED`.
   - `RETROSPECTIVE_RESTATED` records strictly emit `pit_backtest_eligible = False`, even when `verdict == QUALIFIED` (e.g. bounded HPG/VCB retrospective evidence).
   - `classify_universe()` replaces generic `qualified_tickers` with mechanically partitioned `pit_backtest_eligible_tickers` and `retrospective_qualified_tickers`.
2. **Positive Semantic Authority Required First for PIT_AS_KNOWN:**
   - Caller-supplied `retrieved_at` proximity can never self-authorize PIT eligibility.
   - `_price_basis_state()` requires positive `RAW_AS_TRADED` price-basis authority from `provider_price_basis_registry.bounded_price_basis_for()` before any caller observation is evaluated.
   - Only after `RAW_AS_TRADED` is authoritatively proven does the observation's shape (requiring all 7 `market_data_contracts.RawObservation` identity fields: `provider`, `dataset`, `instrument`, `retrieved_at`, `request_identity`, `raw_payload_hash`, `schema_version`), matching query identity, knowledge cutoff (`retrieved_at <= cutoff`), and temporal proximity act as supporting proof.
   - Retrospectively rewritten DNSE current-query responses cannot qualify merely because they were retrieved close to a session.
3. **Current Repository Authority Bounds Respected:**
   - Current repository authority provides no real `RAW_AS_TRADED` market-wide price authority; every active DNSE bounded authority is `ADJUSTED_RETROSPECTIVE`.
   - Real `PIT_AS_KNOWN` qualified count across the universe is correctly **0**. This is a verified negative proof of authority compliance, not an implementation failure.
4. **Corporate-Action Knowledge-Time & Cash Dividend Safety:**
   - Gating strictly uses `observed_at` (when Stock Lookup retained the bytes); `published_at` is ignored in knowledge-time cutoff comparisons.
   - Late amendments/cancellations cannot alter earlier as-known state.
   - Missing `ex_date` strictly fails closed (`REASON_MISSING_EXPLICIT_EX_DATE`); `record_date` is never substituted for `ex_date`.
   - Planned non-executed issuances remain fail-closed.
   - `official_corporate_action_ledger.event_key()` remains untouched.
   - Pure cash-dividend observations are gated fail-closed (`REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY`) without fabricating share-count ledger linkage or portable factors.
5. **Prospective Shadow Containment:**
   - `dnse_prospective_pit_shadow.py` remains untracked, non-authoritative, and deferred (`DEFER_CONFIRMED`); no live acquisition or forward-capture logic was imported or duplicated.

**Validation evidence:**
- Independent audit initially caught one blocking fail-open (temporal proximity self-authorization); defect was bounded-fixed and verified via narrow re-audit (`RAW_OBSERVATION_GATE = SAFE`, `MODE_ISOLATION = SAFE`).
- Full test suite post-fix: 320 passed, 0 failed, 0 error, 0 skipped.
- Focused contract tests: 86 passed, 0 failed, 0 error.
- Real retained P0-A.1 population validation over 1,660 instruments (1,528 success + 132 `PERMANENT` HTTP 400 `BAD_REQUEST` "invalid symbol"):
  - `PIT_AS_KNOWN`: 132 `BLOCKED`, 1,528 `UNKNOWN`, 0 `pit_backtest_eligible`.
  - `RETROSPECTIVE_RESTATED`: 132 `BLOCKED`, 1,528 `UNKNOWN`, 0 `pit_backtest_eligible`.

**Status & Next Gate:**
- `P0-A.3` is **IN PROGRESS** (sub-slice `P0-A.3A` complete on local main, `push = NO`).
- Subsequent authority records: `P0-A.3B` closed `COMPLETE_READ_ONLY` / `SOURCE_SEMANTICS_BLOCKED`;
  `P0-A.3C` is `COMPLETE_EVIDENCE_ACQUIRED`, `P0-A.3D` is `COMPLETE_LOCAL_NO_PUSH`, and active
  next gate is `P0-A.3E` prospective multi-session/event-window price-basis qualification.

## 2026-08-17 - P0-A.2 corporate-action multi-event extraction integrated to local main (P0-A.2 COMPLETE)

`P0-A.2_CORPORATE_ACTION_MULTI_EVENT_EXTRACTION_V1`. Integrated into local `stock-core-private`
main via fast-forward (independent read-only audit `SAFE_TO_INTEGRATE_LOCALLY`, `P0A2_CAN_CLOSE_AFTER_INTEGRATION`,
commit `a7e4a1ce7e8df1c24587c25f669393a5f0265b5e`, `push = NO`). Candidate branch
`feature/p0a2-multi-event-extraction-v1` from worktree
`stock-core-p0a2-multi-event-extraction-v1-20260817`. No network calls, no live acquisition.

**Changes integrated:**
1. **`corporate_action_events.py`:**
   - Added backward-compatible plural extraction boundary `extract_event_observations()` and facet detector `detect_event_facets()`.
   - Delegates to unmodified `extract_event_observation()` when fewer than 2 facets are present (all single-event documents unchanged).
   - Added `extract_explicit_cash_amount_per_share()`: extracts cash amount from explicit `"<amount> VND per share"` / `"đồng/cổ phiếu"` wording, never computed from a percentage rate.
   - Preamble shared facts (`record_date`) carried cleanly onto each facet; quantities/ratios/amounts isolated strictly to each facet span.
2. **`tests/test_official_corporate_action_pillar.py`:** Added 18 new regression tests (108 total, 90 passing, 18 legacy VCB fixture skips). All 18 new tests run and pass.

**Verified results preserved:**
- SSI retained notice (`ssi-vsdc-198728`) yields exactly two independent observations:
  - `cash_dividend`: `cash_amount_per_share = 1000.0` VND (explicit text), `record_date = "2026-08-18"`, `ex_date = None`, `lifecycle_state = "record_date_confirmed"`.
  - `bonus_shares`: `stock_ratio = 0.2` (explicit 5:1 rate), `record_date = "2026-08-18"`, `ex_date = None`, planned issuance remains non-executed (`shares_after = None`, `lifecycle_state = "record_date_confirmed"`).
  - Both facets strictly enforce `record_date` != `ex_date` (`ex_date_absent` warning attached).
  - Neither facet reaches an unqualified price adjustment factor.
- HPG issuer-IR regression preserved (`stock_dividend`, executed, `shares_after = 8,442,964,520`, ex-date absent, factor `NOT_READY`).
- Zero field leakage between facets, distinct deterministic observation hashes, shared provenance preserved.

**Downstream ledger constraint (not a P0-A.2 blocker):**
- Current `official_corporate_action_ledger.py` `event_key` is share-count-based (`shares_after` / `shares_issued` / `shares_before`).
- Pure cash-dividend observations without share changes land in `unlinked_observations` with reason `"no share-change identity; cannot be linked to an event"`.
- Downstream milestones `P0-A.3` / `P0-A.4` must not fabricate linkage or price factors from this limitation.

**P0-A.2 is COMPLETE.**
Next gate: `P0-A.3` — **Market-wide PIT price reconstruction** (not started; depends on A.1 + A.2).

## 2026-08-17 - P0-A.2 corporate-action document-authority coverage extension integrated to local main

`P0-A.2_CORPORATE_ACTION_AUTHORITY_COVERAGE_V1`. Integrated into local `stock-core-private`
main via fast-forward (independent read-only audit `SAFE_TO_INTEGRATE_LOCALLY`, commit
`8f1367667971858db640f1d194412e70918bebe2`, `push = NO`). Candidate branch
`feature/p0a2-corporate-action-authority-coverage-v1` from worktree
`stock-core-p0a2-corporate-action-authority-coverage-v1-20260817`. No network calls, no live acquisition.

**Changes integrated:**
1. **`corporate_action_events.py`:** Added a generic, `source_id == "issuer_ir"` branch in
   `classify_retained_document()` using standard document-internal recital cues (`"thay đổi niêm yết"`,
   `"tổ chức niêm yết:"`, `"mã chứng khoán:"`) and cross-checking the stated ticker code against
   the caller's claim. Unmodified `is_vsdc` branch and `DOCUMENT_CLASS_CEILING` lifecycle contracts preserved.
2. **`config/official_source_registry.json`:** Declared `"listing_change_notice"` under `"issuer_ir"`.
   Admission remains host- and document-type-gated via `official_source_registry.py`.
3. **`tests/test_official_corporate_action_pillar.py`:** Added 18 new regression tests covering
   generic issuer-IR classification, HPG real notice validation, SSI real VSDC notice validation,
   and registry admission. All 18 new tests run and pass (72 existing pass, 18 legacy VCB tests skipped
   due to optional offline fixture absence).

**Verified results:**
- **HPG retained issuer-IR evidence:** Classifies via the generic `issuer_ir` path and reproduces
  the existing qualified result (`stock_dividend`, executed, `shares_after=8,442,964,520`,
  `adjustment_factor` `NOT_READY` for missing ex-date).
- **SSI retained VSDC evidence:** Validated through the real pipeline, remains strictly fail-closed:
  `record_date` (`2026-08-18`) != `ex_date` (`None`), planned bonus (`stock_ratio=0.2`) does not
  become an executed share count, 0 ledger entries created, 0 price adjustment factors reachable.

**P0-A.2 is NOT complete.**
- **Remaining P0-A.2 gap:** The retained SSI document (`ssi-vsdc-198728`) contains both cash-dividend (10%)
  and bonus-share (20%) facets, while the current single-event-per-document extraction model captures only
  `bonus_shares`. Full multi-event extraction from single compound notices remains an open gap before
  P0-A.2 can be considered complete.
- **Do not start or choose P0-A.3.**

## 2026-08-17 - P0-A.2 corporate-action prior art review: REJECT_AND_REIMPLEMENT

`P0-A.2_CORPORATE_ACTION_EVIDENCE_SCALE_OUT_REVIEW`. Reviewed prior art branch family
`1183c72`→`d7b9bf3` ("feat(core): scaffold official corporate actions foundation").

**Disposition: `REJECT_AND_REIMPLEMENT`.**

**Meaning of disposition:**
- Reject the duplicate/weaker prior-art pipeline scaffolding;
- **DO NOT** rebuild current B3/B4 architecture.
- Current-main `corporate_action_events.py` (B3 event materialization) + `official_corporate_action_ledger.py`
  (B4 official ledger) remain the authoritative implementation basis.

**Main reasons:**
1. **Document-class lifecycle ceiling already exists on main:** Current main already implements document-class
   authority boundaries and life-cycle classification (`corporate_action_events.py` / `DOCUMENT_CLASS_CEILING`).
2. **Official source registry gate already exists:** Current main enforces strict source registry gates
   (`official_source_registry.py` / `config/official_source_registry.json`).
3. **N-way conflict / arithmetic / supersession handling already exists:** B3/B4 already provide robust
   event deduplication, ratio/cash arithmetic, and multi-source conflict reconciliation.
4. **Real-evidence tests already exist:** Main has comprehensive regression suites against real VNM, HPG,
   and other official documents.
5. **Prior art is ticker-specific and duplicates these contracts:** Branch `1183c72`→`d7b9bf3` introduced
   ticker-specific scaffolding that duplicates and weakens the contracts already established on main.

**Preserved core invariants:**
- `record_date` != `ex_date` (ex-date is not inferred from record date).
- Planned issuance != executed issuance (distribution execution requires distinct evidence).
- No unqualified adjustment factors (ratios remain pure until explicit adjustment authority is qualified).
- SSI VSDC notice evidence remains fail-closed until validated through the canonical pipeline.

**Next gate: `P0-A.2 — extend current-main corporate-action document-authority coverage`.**
Scope:
- `issuer_ir` `listing_change_notice` support through the existing B3/B4 path;
- Validate already-retained SSI VSDC evidence through the real pipeline;
- No network acquisition.

## 2026-08-17 - P0-C universe semantic evidence qualification

`P0-C_UNIVERSE_SEMANTIC_EVIDENCE_QUALIFICATION_V1`. Integrated into local `stock-core-private`
main via fast-forward (independent read-only audit `SAFE_TO_INTEGRATE_LOCALLY`, commit
`0f29019da83e83144f4f7f3832f054e04be66a97`, `push = NO`). Precondition: the entry below ("P0-C.1
and P0-C.2 canonical universe foundation implemented, local worktree only") was itself integrated
into local main (commit `5ea3b6a85f734bc299c64464bf4d8452881c9116`) before this milestone started.
Sole writing agent: Claude Code, on branch `feature/canonical-universe-semantic-qualification-v1`.
No live DNSE call.

**Exchange/market semantics: investigated, `UNKNOWN` (unqualified).** Re-examined `marketId`/
`productGrpId` across three retained DNSE endpoints beyond `/market/instruments`:
`/price/{symbol}/secdef` and `/market/trading-session` (both already retained from the 2026-08-10
qualification pass, `operations-review/dnse-market-data-qualification-20260810/probe_results.json`
— no new fetch). All three retain `marketId` as an opaque code with no human-readable label
anywhere; no first-party DNSE documentation or SDK spec exists in this workspace. Corroboration
remains 2-3 familiar tickers per code, which this project's own doctrine already treats as
insufficient (see the 2026-08-11 entry below). No mapping implemented.

**Listing/active-status semantics: investigated, `UNKNOWN` (unqualified), candidate fields found.**
`/price/{symbol}/secdef`'s already-retained HPG/VNM/QNS responses carry `finalTradeDate`,
`symbolAdminStatusCode`, `symbolTradingMethodStatusCode`, `symbolTradingSanctionStatusCode`, and
`securityStatus` — genuinely promising fields by name, but all three retained examples show an
identical all-normal state with zero contrasting (suspended/delisted) example to confirm what they
distinguish. No live probe was attempted: no reliably-evidenced delisted/suspended DNSE symbol
exists in this workspace, and `security_definition` is per-symbol, so even a confirmed semantic
would still need its own market-wide bulk-ingestion milestone (1,660 calls) before it could
populate `ACTIVE_UNIVERSE` — out of this milestone's bounded scope regardless. No mapping
implemented; `listing_status` stays `UNKNOWN`.

**`UNKNOWN_SECURITY_GROUP` (secondary, bounded): `PARTIAL`, ~99.6% resolved.** The 1,590-record
population partitions exhaustively by raw `securityGroupId` (`EW`=1,346, `BS`=203, `EF`=21, `FU`=8,
`MF`=6, no-code=6). Every populated `name` field (not a sample) was inspected: `EW`→`WARRANT`
(697/697 unanimous, "Chứng quyền"), `BS`→`BOND` (~57/67 explicit "Trái phiếu", remainder
consistent), `EF`→`ETF` (20/21 explicit "ETF"), `FU`→`DERIVATIVE` (8/8 "HĐTL", corroborated by
`symbol_type_raw`), no-code→`INDEX` (6/6 individually confirmed "Chỉ số ..."). `MF` (6 records) was
deliberately left `UNKNOWN` — its own evidence mixes generic "Quỹ đầu tư" with "Quỹ ETF" phrasing,
evidence against folding it into `ETF`. New module `dnse_security_group_semantics.py`
(`dnse_security_group_semantics/v1`) implements this as a strictly additive refinement; never
modifies `dnse_instrument_universe.py`'s own `"ST"`→`EQUITY` classification, which uses the same
generalize-from-named-sample method this new mapping reuses, not a looser one.

**`canonical_universe_tiers.py` updated only where necessary to consume this**: `INDEX` now gets
its own reason code (`index_confirmed_not_applicable`, `quality_status="provider_reported"`),
split from `SYNTHETIC`/`INDEX_OR_SYNTHETIC` (still `index_or_synthetic_reserved_unqualified`,
still genuinely unevidenced). Tier DAG unchanged.

**Real 2026-08-12 snapshot re-run** (same snapshot as the entry below, `content_hash=965c4b30...`):
`MASTER_OBSERVED` unchanged at 3,250. `LISTED_EQUITY_CANDIDATE`: 1,660 INCLUDED (unchanged) / 1,590
UNKNOWN → now 6 UNKNOWN + 1,578 EXCLUDED (`instrument_type_warrant`=1,346,
`instrument_type_bond`=203, `instrument_type_etf`=21, `instrument_type_derivative`=8) + 6
NOT_APPLICABLE (`index_confirmed_not_applicable`). `ACTIVE_UNIVERSE.included` **unchanged at 0** —
the correct, expected result: security-group evidence says nothing about listing/active status and
correctly does not resolve it; the 1,660 `EQUITY` instruments still show exactly
`listing_status_unknown`, byte-identical to before. Confirmed by a direct new test
(`test_qualified_instrument_class_never_fabricates_listing_status`), not just by the aggregate
counts. 60 tests pass (43 existing + 17 new); `py_compile` and `git diff --check` clean.

**Does not establish:** any exchange or listing-status authority; the 6 `MF` records' classification;
any P0-A/P0-B status change; a push to `origin`. **Active next gate:** `P0-A.2 Corporate-action
evidence scale-out` review-for-promotion (see `docs/ROADMAP.md`). Foundation and semantic
qualification are integrated on local main (`0f29019da83e83144f4f7f3832f054e04be66a97`, `push = NO`).

## 2026-08-17 - P0-C.1 and P0-C.2 canonical universe foundation implemented, local worktree only

Executed the `P0-C.1_P0-C.2_CANONICAL_UNIVERSE_REVIEW_FOR_PROMOTION` gate recorded in the
"Authority doc rebaseline" entry below and in `STATE.md`'s `## PRIOR-ART BRANCHES`. Sole writing
agent: Claude Code, on a dedicated worktree/branch off this file's own then-current main HEAD
`eebae8722793ee3a7c621d76c074af70492a1a12`
(`feature/canonical-universe-foundation-promotion-v1`,
`worktrees/stock-core-canonical-universe-foundation-v1-20260817`). **Local commit only — not
merged to main, not pushed, no live DNSE call.**

**Ported and bounded-patched, both `PROMOTE_WITH_BOUNDED_PATCH` per the prior review:**
`canonical_instrument_reconciliation.py` (C.1, from `b4e3c71`) and `canonical_universe_tiers.py`
(C.2, from `3d9a2ab`), plus their contract docs and 28 existing tests (all still passing
unmodified). C.1's `COMPANY_PROFILE` `instrument_class` extraction now reads `qualified_fields`,
matching `name`/`exchange` in the same function (two new direct tests: it previously read an
unrelated top-level field, untested either way). C.2's membership and ledger-event rows now carry
`instrument_class`/`exchange` as first-class fields, carried verbatim from C.1's own selected
values — no new normalization. C.2's non-equity exclusion reasons are now class-specific
(`instrument_type_etf`/`_warrant`/`_right`/`_bond`/`_derivative`, aligned with
`dnse_instrument_universe.INSTRUMENT_CLASSES`) instead of one generic bucket; the `INDEX`/
`SYNTHETIC` branch is explicitly relabelled `index_or_synthetic_reserved_unqualified`
(`quality_status="unqualified"`) since no current classifier authority has ever emitted those
values. New no-network integration adapter
`tools/build_canonical_universe_from_retained_snapshot.py` wires an already-retained DNSE
security-master snapshot through C.1 then C.2, binding every output to that snapshot's own
path/`content_hash`/`snapshot_id`/`retrieved_at`; it never calls `discover_universe()`. 15 new
tests added (43 total); `py_compile` and `git diff --check` clean.

**Verified against the real, already-retained 2026-08-12 snapshot**
(`operations-review/dnse-market-data-lake-v2-20260812/data/market_raw_lake/universe/
5c61b853c6f806e7120c56646b2af64e241aa26e70cccd37b9ddf1288258c4d4.parquet`,
`content_hash=965c4b30e003d5a1fa0f4963b102c605d8fc4485def3ccf98a153dec88a46af9`): `MASTER_OBSERVED`
3,250; `LISTED_EQUITY_CANDIDATE` 1,660 `INCLUDED` / 1,590 `UNKNOWN` (`instrument_type_unknown`) / 0
`EXCLUDED` / 0 `NOT_APPLICABLE` — exact match to this file's and `STATE.md`'s existing DNSE
security-master facts; `ACTIVE_UNIVERSE` 0 `INCLUDED` / 3,250 `UNKNOWN`, the expected fail-closed
result, not a defect. Independent cross-check: this run's C.1 artifact content-hash
(`eb253a5a1a0601b90322265ee954bdb82f9751ab37994568c89d69a9ea16ba5d`) is byte-identical to a
pre-existing dev-run artifact already retained at
`operations-review/p0-c1-canonical-instrument-reconciliation-20260816/`, confirming the port
preserved C.1's exact original behavior against the same real input.

**Does not establish:** `P0-C` completion; `P0-C.3` (not started); `ACTIVE_UNIVERSE` qualification
for any instrument (no listing-status or exchange-label evidence source exists anywhere in this
codebase for any DNSE-only instrument); any finer classification of the 1,590
`UNKNOWN_SECURITY_GROUP` population (still fully undifferentiated — no `securityGroupId` besides
`"ST"` has ever been empirically mapped); any P0-A/P0-B status change; a main-branch merge.

**Remaining universe-semantic blockers, explicit and unscoped:** exchange-label mapping (DNSE
`marketId` -> HOSE/HNX/UPCoM, same gap the 2026-08-11 entry below already declined to guess from two
data points); listing/active-status evidence (no qualified source exists); 1,590
`UNKNOWN_SECURITY_GROUP` finer classification. None has a scoped milestone yet; each needs its own
owner-authorized evidence-sourcing decision. Next gate for this thread is that scoping, not
`P0-A.2`/`P0-B`/`P0-C.3` by default and not `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` or other
single-ticker work.

## 2026-08-20 - P3-C Comparative Financial Evidence Scale-Out Partial Closeout

`P3C_COMPARATIVE_EVIDENCE_SCALEOUT = PARTIAL_LOCAL` (`p3c_comparative_financial_evidence.py`, `tools/run_p3c_comparative_financial_evidence.py`, `config/promoted_comparative_financial_evidence.json`, `push = NO`).

1. **Qualified bounded uplift:** An official SSI issuer-IR FY2023 audited consolidated annual report was retained at its immutable local path and SHA-256 verified (`eafcbccf…c30e3`). Six exact primary-statement facts were replayed through the generic sector recognizer: FVTPL assets, loans, total assets, total equity, and total/parent profit after tax. No new issuer was introduced.
2. **Measured outcome:** The refreshed 11-issuer panel rises from 102 to 108 qualified facts. P3-B exact-qualified results rise from 70 to 75; SSI FY2024 return on assets and return on equity are upgraded from ending-balance proxies to exact average-denominator calculations. The aggregate proxy count remains 15 because FY2023 has no FY2022 average-balance evidence; this is disclosed rather than silently treated as an improvement.
3. **Fail-closed boundary:** A discovered VCB FY2023 portal location was not used because its host is absent from the approved source registry. No VCB bytes/facts were acquired. CapEx was not mapped because no exact generic CapEx semantic line was acquired. Corporate residual gaps, P3-A’s explicit-ex-date block, price/liquidity, valuation, ranking, execution, and backtesting authorities are unchanged.
4. **Next gate:** P3-D may acquire only registry-approved official comparative evidence for VCB FY2023 and residual corporate identity gaps, with the same fact-level provenance, immutable-byte hashing, and no proxy promotion.

## 2026-08-20 - P3-D Residual Comparative Financial Evidence Scale-Out Partial Closeout

`P3D_RESIDUAL_EVIDENCE_SCALEOUT = PARTIAL_LOCAL` (`p3d_residual_comparative_financial_evidence.py`, `tools/run_p3d_residual_comparative_financial_evidence.py`, `config/promoted_residual_comparative_financial_evidence.json`, `push = NO`).

1. **Residual reconciliation:** The P3-C 55-gap count is correct by definition. SSI FY2023 evidence resolved the FY2024 earnings-growth comparison while making FY2023 the first observed annual period, whose missing FY2022 comparator is independently required. No gap-derivation defect or threshold change was introduced.
2. **Qualified bounded uplift:** Five existing retained, SHA-256-verified, approved issuer-IR audited consolidated filings were replayed through the generic statement recognizer: HPG FY2022–23 and PVD FY2022–24. Ten exact source-page facts (revenue and total assets for each issuer-period) raised the panel from 108 to 118; P3-B exact-qualified metrics rose from 75 to 86 and residual gaps fell from 55 to 42. HPG and PVD FY2022 ROE changed from ending-balance proxy to exact average-denominator calculations.
3. **Authority boundary:** Every document is checked against the existing source registry, immutable bytes, and original materialization page text. VCB FY2023 is explicitly `VCB_FY2023_BLOCKED_SOURCE_NOT_APPROVED`; the unapproved `portal.vietcombank.com.vn` candidate was not used, no registry entry changed, and no bytes/facts were acquired. CapEx remains unpromoted and no proxy was created.
4. **Next gate:** P3-E may pursue the remaining approved retained annual revenue/total-assets evidence gaps. Any VCB FY2023 use first needs a separate owner-authorized source-authority promotion decision.

## 2026-08-20 - P3-E Fundamental Coverage Closeout & Valuation-Input Readiness Gate

`P3E_FUNDAMENTAL_COVERAGE_CLOSEOUT = COMPLETE_LOCAL` (`p3e_fundamental_coverage_closeout.py`, `valuation_input_readiness.py`, `config/promoted_fundamental_coverage_closeout_evidence.json`, `push = NO`).

1. **Comparative lane closed:** The P3-D 42-gap inventory classifies as 28 `STRUCTURAL_BOUNDARY_GAP`, one `SOURCE_AUTHORITY_BLOCKED` (VCB FY2023), and 13 current-window actionable metric outputs. The supported research boundary is the latest authoritative annual period plus one immediate predecessor when present; no unlimited backward-acquisition mandate is created.
2. **Qualified uplift:** Six existing retained approved FY2024 consolidated statements (HPG, NVL, PAN, POW, QNS, VNM) were SHA-256 and source-page verified and replayed through generic statement recognition. Twelve exact revenue/total-assets facts raise the panel 118→130, P3-B exact results 86→94, and reduce missing results 42→29. No current-window revenue/assets gap remains.
3. **Valuation gate, not valuation:** `valuation_input_readiness.py` reports financial identity readiness independently from `MARKET_INPUT_BLOCKED` caused by P3-A/raw-as-traded/dated-share alignment limits. It produces no multiple, target price, intrinsic value, ranking, scenario, or recommendation. Corporate P/E/P/B/P/S/EV-Sales financial inputs are ready where their current facts exist; EBITDA and FCFF inputs remain partial. Bank and securities EV/EBITDA/FCFF semantics are explicitly not applicable.
4. **Persistent boundaries:** `VCB_FY2023_SOURCE_AUTHORITY_BLOCKED` remains explicit but does not block VCB FY2024 P/E/P/B financial-input readiness. CapEx/FCF is terminally `CAPEX_FCF_BLOCKED_MISSING_EXACT_IDENTITY`; no proxy was introduced. P3-A remains independently blocked.
5. **Next gate:** P3-F may design a bounded valuation/scenario capability only after separately qualifying market-price and dated-share inputs; it is not authorized by this closeout itself.

## 2026-08-20 - P3-F Current Market Valuation Basis Activation & Sector-Aware Valuation MVP

`P3F_CURRENT_MARKET_VALUATION_RESEARCH = PARTIAL_LOCAL` (`p3f_current_market_valuation.py`, `tools/run_p3f_current_market_valuation.py`, `push = NO`).

1. **Current-market boundary:** The selected 2026-07-30 HPG close comes only from the retained, evidence-bounded DNSE current-state window and remains `CURRENT_MARKET` / `ADJUSTED_RETROSPECTIVE`; it is not `RAW_AS_TRADED`, PIT, or backtest-eligible. The date is the latest retained price session for which the official HPG share-transition bridge proves coverage.
2. **Activated facts, not advice:** HPG's qualified current price (VND 21,800), dated official common shares (8,442,964,520), and FY2024 qualified corporate facts yield descriptive P/E, P/B, P/S, and EV/Sales only. Every metric remains `is_actionable = false`; no fair value, target, recommendation, ranking, portfolio decision, or scenario probability exists.
3. **Fail-closed cohort:** The remaining ten issuers stay issuer-level blocked. DNSE current-price authority is not generalized beyond its evidence-bounded tickers; VCB's retained payload is malformed, and no dated current-share chain is inferred from FY2024 period-end shares. Banks and securities keep P/E/P/B-only applicability; industrial EV and FCFF semantics remain inapplicable.
4. **Persistent boundaries:** Historical valuation and P3-A remain blocked, and `CAPEX_FCF_BLOCKED_MISSING_EXACT_IDENTITY` remains terminal. The next permitted design gate is a bounded observed-metric scenario/relative-valuation research boundary, without forecasts, probabilities, target prices, or execution output.

## 2026-08-20 - P3-F2 Current Valuation Input Authority Foundation

`P3F2_CURRENT_VALUATION_INPUT_FOUNDATION = COMPLETE_LOCAL` (`current_valuation_input_authority.py`, `tools/run_p3f2_current_valuation_input_authority.py`, `push = NO`).

1. **Generic contract, instance-scoped authority:** The reusable resolver accepts arbitrary canonical instruments and evidence rows. It preserves `CURRENT_MARKET`, `PIT_OBSERVED`, `RAW_AS_TRADED`, `ADJUSTED_RETROSPECTIVE`, and `UNKNOWN`; qualifying a current DNSE close never promotes raw-as-traded or PIT authority.
2. **Session and price discipline:** A daily close is accepted only for the latest fully completed Vietnamese weekday session present in retained evidence, with canonical-provider symbol agreement, valid payload shape/value, retained request lineage, and explicit freshness. Malformed, missing, stale, conflicting, and unresolved observations fail closed.
3. **Share and action discipline:** Current market cap accepts only explicit `common_shares_outstanding` candidates with coverage through the valuation date. Period-end, weighted-average, listed, issued, treasury, and diluted identities remain distinct. A potentially share-changing action blocks eligibility when timing/completion is unresolved; no ex-date, execution, continuity, or resulting shares are inferred.
4. **Integration and operations:** P3-F2 supplies qualified inputs only; P3-F remains the multiple-calculation authority. The read-only P3 cohort scan is the operational work queue, not an acquisition campaign. P3-G remains reserved for its existing scenario/relative-valuation scope and is not started here.

## 2026-08-20 - P3-F3 Operational Current Valuation Input Scale-Out

`P3F3_OPERATIONAL_VALUATION_INPUT_SCALEOUT = PARTIAL_LOCAL` (`tools/run_p3f3_operational_valuation_input_scaleout.py`, `operations-review/p3f3-operational-valuation-input-scaleout-20260820/p3f3_operational_valuation_input_scaleout_artifact.json`, `push = NO`).

1. **Cohort-Wide DNSE Materialization:** Materialized latest-completed DNSE daily OHLC observations (session 2026-08-19) for all 11 authoritative cohort issuers (`GAS`, `HPG`, `NVL`, `PAN`, `POW`, `PVD`, `QNS`, `SSI`, `VCB`, `VNM`, `VRE`) into runtime evidence store with explicit request lineage, hash verification, and provider/symbol agreement.
2. **Price Authority Scale-Out (1→11):** Generic P3-F2 price qualification elevates from 1 ready issuer (HPG) to 11 ready issuers (`PRICE_READY = 11`, `PRICE_BLOCKED = 0`). All prices are qualified under `CURRENT_MARKET` / `ADJUSTED_RETROSPECTIVE`; `RAW_AS_TRADED` remains `NOT_PROMOTED` and `historical_pit_eligible = False`.
3. **Fail-Closed Share Basis Governance:** Share basis across the entire cohort remains `SHARE_BLOCKED` (`0/11 SHARE_READY`, `11/11 SHARE_BLOCKED`) for valuation session 2026-08-19 due to absence of verified official evidence proving common shares outstanding through 2026-08-19. Forward inference and synthetic continuity remain prohibited; corporate actions (e.g. SSI unexecuted issuance) remain blocked.
4. **Valuation Rerun Integrity:** Rerunning P3-F sector-aware valuation engine through the P3-F2 resolver seam confirms 0/11 valuation-ready issuers and 0 activated multiples for session 2026-08-19, preserving fail-closed boundaries. P3-G remains reserved for future relative-valuation/scenario research.

## 2026-08-20 - P3-F4 Generic Current Share Authority Root-Cause & Enablement

1. **Root cause is combined, not a ticker queue:** Existing approved evidence includes FY2024 period-end/weighted counts and one executed HPG transition, but no scalable source proves `common_shares_outstanding` through the 2026-08-19 valuation session. The retained provider field is `ISSUED_SHARES`, not an approved substitute. Unresolved SSI issuance and the coverage gap after HPG’s 2026-07-30 corroboration remain blocking facts.
2. **Generic timeline boundary:** `current_share_authority.py` is integrated into P3-F2’s share qualifier. It accepts only explicitly qualified `common_shares_outstanding` with an explicit effective interval covering the valuation date, preserves all other identities, blocks conflicting values and unresolved share-changing actions, and never forward-fills from a last known count.
3. **Registration discipline:** VCB/VNM legacy share citations cannot be remapped to later governed manifest records because the citation rows do not carry an immutable document-hash linkage. No evidence bytes, source registry, or source authority was changed.
4. **Next owner gate:** The sole highest-leverage future candidate is retained `VCI.overview.issue_share` metadata. It remains `AUTHORITY=NOT_PROMOTED` pending an owner decision on exact outstanding-share semantics, effective-date/freshness, corporate-action completeness, and permitted use. The P3-F4 rescan remains 0/11 `SHARE_READY` and 0/11 `BOTH_READY`; P3-G remains reserved and unstarted.

## 2026-08-20 - Global Roadmap Blocker Rebaseline + MVA Operating Contract

1. **Readiness modes:** `MINIMUM_VIABLE_ANALYSIS_SHADOW` is a deterministic current descriptive research mode, not decision support. Its mandatory artifact envelope is `is_actionable_for_execution=false`, `pit_backtest_eligible=false`, `liquidity_sizing_authority=BLOCKED`, and `valuation_scope=CURRENT_DESCRIPTIVE_ONLY`. Historical PIT, liquidity, and sizing can remain blocked in MVA. `FULL_DECISION_SUPPORT_READY` requires qualified current-share, canonical-universe, volume/traded-value, historical price/corporate-action PIT, historical universe/entity PIT, liquidity/risk/sizing, and PIT-backtesting authorities.
2. **Universe denominator:** An empirical active cohort is a derived shadow denominator only. It requires explicit as-of date, lookback/window, source completeness, inclusion rule, and deterministic identity; it neither promotes nor substitutes for canonical-universe authority, and no fixed count is adopted.
3. **Sector and market-data boundaries:** Current DNSE price authority is limited to bounded current descriptive use; `RAW_AS_TRADED`/historical PIT remains unpromoted. Volume/traded-value market composition remains insufficient for liquidity and sizing. Industrial CapEx/FCFF/EV conditions do not gate banks or securities; future sector-appropriate P/B-ROE/residual-income-style valuation contracts remain future work. `interbank_on_rate`, `sbv_net_injection_20d`, and `vn30f1m_basis` are source-qualification backlog only.
4. **Ordering:** The active gates are current-share promotion review, MVA shadow operation, shadow denominator, volume/traded-value authority, future P3-G current relative valuation/scenario, corporate-action plus historical PIT, historical universe/entity PIT, liquidity/risk/sizing, PIT backtesting, then deeper valuation/financial/sector/macro work. P3-G remains reserved and is not started by this decision.

## 2026-08-20 - P3-F5 Current Share Source Promotion & Allowed-Use Review

1. **Candidate is retained, not promoted:** `VCI.overview.issue_share` is confirmed as a retained `ISSUED_SHARES` observation in `metadata.shares_outstanding`; its state remains `AUTHORITY_NOT_PROMOTED_PENDING_OWNER_DECISION`. The review found 1,682 positive integral values of 1,683 metadata rows, which proves scale only. It does not establish `common_shares_outstanding`, treasury treatment, or a valuation-date effective interval.
2. **Comparison and freshness are not semantic proof:** HPG has the same numeric value as an executed official current-common anchor but a different identity; VNM has the same number as an FY2024 period-end anchor but not a common effective-date contract; VCB differs numerically; and SSI is blocked by a planned/undated issuance. All retained provider observations are dated 2026-08-14 against the P3-F3 2026-08-19 session, while the provider is absent from the approved official-evidence registry and has no retained semantic documentation.
3. **Corporate-action and market-cap boundary:** The generic read-only resolver withholds a provider value for unresolved share-event timing. `ISSUED_SHARES` is not allowed as a market-cap denominator, a `common_shares_outstanding` alias, or P3-F2/P3-F valuation authority. The P3-F3 authoritative result remains 0/11 share-ready and 0/11 both-ready; the review's hypothetical 9/11 proxy observations are not an activated valuation output.
4. **Permitted future use and next evidence gate:** The recommendation is `MORE_EVIDENCE_REQUIRED` and `PROVIDER_PROXY_USE_ONLY`: only after a separate owner-approved bounded policy could a provider observation be labelled as a current descriptive MVA shadow proxy. It must retain the mandatory MVA envelope and remains prohibited for execution, PIT backtesting, liquidity/sizing, qualified-official labelling, or automatic valuation activation. The exact next gate is acquisition of independent provider semantic and effective-date evidence; P3-G remains reserved and unstarted.

## 2026-08-20 - P3-F6 MVA Provider-Share Proxy Policy & Shadow Valuation Activation

1. **Bounded owner approval:** The owner-approved policy is exactly `MVA_PROVIDER_ISSUED_SHARE_PROXY_USE`. It permits retained `VCI.overview.issue_share` only as `PROVIDER_REPORTED_ISSUED_SHARES_PROXY` in `MINIMUM_VIABLE_ANALYSIS_SHADOW`. Its binding semantic identity remains `ISSUED_SHARES`, source authority remains `NOT_PROMOTED`, `official_share_authority=false`, and `common_outstanding_equivalence=false`.
2. **Strict MVA envelope:** Every proxy bundle requires `runtime_mode=MINIMUM_VIABLE_ANALYSIS_SHADOW`, `is_actionable_for_execution=false`, `pit_backtest_eligible=false`, `liquidity_sizing_authority=BLOCKED`, and `valuation_scope=CURRENT_DESCRIPTIVE_ONLY`. It fails closed without that complete envelope and cannot emit recommendations, targets, rankings, sizing, execution, historical valuation, PIT results, or scenario probabilities.
3. **Authoritative lane unchanged:** P3-F2 and P3-F retain their original resolver and formulas. The 2026-08-19 authoritative P3-F3 cohort remains `SHARE_READY=0/11`, `BOTH_READY=0/11`, and zero authoritative valuation methods. A proxy price/share pair is never converted into authoritative readiness.
4. **Degraded proxy contract:** The generic qualifier requires canonical mapping, positive integral shares, exact VCI field lineage, retrieval/observation time, `ISSUED_SHARES`, freshness, corporate-action safety, and explicit MVA permission. Retained stale observations are visible only as `PROXY_STALE` / `DERIVED_PROXY`; SSI and VCB are `PROXY_CORPORATE_ACTION_BLOCKED` with no inferred ex-date, execution, shares-after, or continuity. The separate metric identity is `market_cap_provider_issued_share_proxy`.
5. **Measured scope and boundary:** At the retained session, 1,680 of 1,683 provider rows are eligible only as degraded proxy observations; the 11-issuer proof cohort has 9 proxy market-cap inputs, proxy P/B/P/S/EV-Sales for 9 and proxy P/E for 8. P3-F sector gating remains intact, including bank/securities exclusion from industrial EV semantics. This broad shadow coverage supports a future MVA daily research bundle activation review, not P3-G; P3-G remains reserved and unstarted.

## 2026-08-20 - P3-F7 MVA Daily Research Bundle & Shadow Active-Cohort V1

1. **Daily shadow contract:** `MVA_DAILY_RESEARCH_BUNDLE_READY = YES` for the deterministic `MINIMUM_VIABLE_ANALYSIS_SHADOW` bundle only. Its required envelope is retained intact, and the bundle emits no recommendation, target, ranking, sizing, execution, historical valuation, PIT backtest, scenario probability, Consumer, or Dashboard output.
2. **Derived denominator, not universe authority:** `COHORT_EMPIRICALLY_ACTIVE` is a deterministic shadow denominator derived from retained metadata instruments with one positive-close/present-volume observation in every one of the 20 completed sessions ending 2026-08-19. It has 527 members of 1,683 candidates; 1,156 exclusions are retained with explicit incomplete/malformed coverage reasons. It is not `ACTIVE_UNIVERSE`, does not infer listing status, and does not adopt a fixed cohort count as authority.
3. **Feature and breadth boundary:** Current close context, return/momentum, moving averages, volatility, and provider-scoped relative volume are emitted only for complete cohort members as `SHADOW_ONLY` or `DERIVED_PROXY`. Breadth is `127` advancing, `291` declining, and `109` unchanged over the explicit 527 denominator. Relative volume remains non-liquidity; foreign-flow value and macro-liquidity are blocked when no qualified current retained contract exists.
4. **Separate research lanes:** P3-B fundamental readiness is attached only where retained (11 records). P3-F6 proxy valuation coverage is 9, while authoritative valuation coverage remains zero; the lanes are never merged. Source authority, `RAW_AS_TRADED`/historical PIT, liquidity/sizing, and P3-G remain unchanged and blocked/reserved.

## 2026-08-20 - P3-F8 MVA Operational Daily Run & Research Quality Validation

`P3F8_MVA_OPERATIONAL_VALIDATION = COMPLETE_LOCAL` (`tools/run_p3f8_mva_operational_run.py`, `operations-review/p3f8-mva-operational-run-20260820/p3f8_mva_operational_run_artifact.json`, `push = NO`).

1. **Operational Usability Verdict:** `MVA_OPERATIONALLY_USABLE` confirmed for daily shadow research across the 2026-08-19 market session. The bundle satisfies all operational criteria: deterministic generation, explicit session resolution, exact breadth reconciliation (127 advancing, 291 declining, 109 unchanged, 0 missing over 527 empirical denominator), preserved proxy/authority separation, complete technical features across active members, and clear disclosure of blocked capabilities.
2. **Research Utility Classification:** Market trend/MAs, breadth, 20d momentum, and 20d volatility are classified `USEFUL_NOW`. Provider-scoped relative volume, P3-F6 proxy valuation (9 issuers), P3-B audited fundamentals (11 issuers), and sector taxonomy are `USEFUL_WITH_WARNING`. Foreign flows, macro liquidity, scenario analysis, and rankings are `BLOCKED_BUT_NONCRITICAL_FOR_MVA`.
3. **Ranked Blocker Inventory:** The primary analytical bottlenecks are (1) lack of verified current-common-shares authority (source acquisition needed), (2) fundamental statement extraction limited to 11 proof issuers (generic extraction scale-out needed across the 527 active cohort), and (3) volume/traded-value liquidity semantics (needed for execution/sizing).
4. **Next Gate Recommendation:** Generic fundamental statement extraction scale-out across the 527 active cohort delivers the highest direct research-utility unlock. P3-G remains reserved and must not be entered prematurely.

## 2026-08-20 - P3-F9 Exact-Session MVA Snapshot Boundary

1. **Root cause and boundary:** F7 read the dashboard runtime directly and inherited P3-F3's frozen 2026-08-19 session; no generic current-session shadow materializer existed. P3-F9 adds a DNSE-only shadow snapshot boundary rather than writing the Dashboard/runtime database.
2. **Exact-session discipline:** One generic `/price/ohlc` request contract runs across the canonical mapping. The resolved completed session is retained only if present exactly; intraday, malformed, provider-failed, and missing records are explicit failures, never prior-session substitutions. Provider, dataset, field identity, request, payload hash, retrieval time, price basis, and qualification remain bound to each observation.
3. **MVA-only authority:** The snapshot is `CURRENT_MARKET` descriptive-only under the mandatory MVA envelope. It does not promote `RAW_AS_TRADED`, PIT, liquidity/sizing, source authority, valuation authority, or a canonical universe. P3-F7/F8 may consume it only under exact resolved/snapshot/bundle session equality.
4. **Observed operating result:** The controlled live provider window retained six exact 2026-08-20 observations with six complete 20-session MVA records. The remaining 1,677 canonical candidates are marked `NOT_ATTEMPTED_BOUNDED_PROVIDER_WINDOW`, never represented by a 2026-08-19 fallback. This is a partial freshness proof, not marketwide freshness readiness.
## 2026-08-20 - Evidence-Bound Classification & Relative Context Scale-Out V1

`CLASSIFICATION_RELATIVE_SCALEOUT_V1 = READY_LOCAL` (`sector_relative_research_context.py`, `strategy_research_eligibility.py`, `evidence_aware_research_screener.py`, `push = NO`).

1. The retained `vnstock:Listing(source=VCI).symbols_by_industries` metadata snapshot is accepted only as `PROVIDER_DESCRIPTIVE_CLASSIFICATION`. Each record retains its raw provider label, conservative normalized label, VCI namespace, source artifact, individual as-of value, and provider-reported status. It is not official, canonical, or qualified classification.
2. The 33 prior qualified classifications are unchanged and take precedence. Provider groups are isolated to the single VCI namespace and require at least five members. This yields 486 lower-authority contexts; the four-name provider telecom group fails closed, as do the pre-existing small qualified classes.
3. Relative output remains same-session technical context only: 20-day momentum, volatility, provider-scoped relative volume, and trend-state distribution. It excludes cross-metric provider fundamentals, valuation, ranking, recommendation, sizing, execution, historical PIT, and liquidity authority.
4. `RELATIVE_CONTEXT_AVAILABLE` remains qualified-only. New explicit provider-descriptive and any-relative screen filters, eligibility states, and Review Pack labels prevent consumers from conflating the two authority tiers.
## 2026-08-20 - Catalyst & Event Research Context V1

`CATALYST_EVENT_RESEARCH_CONTEXT_V1 = READY_LOCAL` (`catalyst_event_research_context.py`, `run_catalyst_event_research_context.py`, `push = NO`).

1. An event is a source-linked `FACT`; a catalyst interpretation is a distinct `INFERENCE` carrying the event identity, scenario/dossier linkage, thesis/counter-thesis hashes, open question, and invalidation relevance. AI is prohibited from creating event facts or factual dates.
2. The retained official corporate-action ledger produces one eligible HPG stock-dividend/listing-change event. It is `COMPLETED`; the original ledger's absent ex-date and record date remain unknown, and no record/payment/listing date is substituted. Its research impact remains ambiguous/unknown rather than positive or negative.
3. Catalyst eligibility requires at least one evidence-backed event. It is therefore HPG-only (1/523); all other records retain `NO_EVIDENCE_BACKED_EVENT`. The 25-name Review Pack and its scenario cases receive no upgrade because HPG is not in that queue.
4. This consumer context creates no corporate-action price adjustment, historical PIT/backtest, recommendation, scoring, probability, target, expected return, liquidity, sizing, or new authority. Broader event coverage needs a separately governed generic event source, not a manual ticker campaign.
## 2026-08-20 - Governed Generic Issuer Disclosure / Event Feed V1

`GENERIC_ISSUER_EVENT_FEED_V1 = TERMINAL_NO_APPROVED_ROUTE` (`push = NO`; no ingestion source or runtime data changed).

1. The existing local `news_sync` RSS collector was the sole plausible generic route under current provider governance. A read-only live probe of its configured VnExpress business feed returned HTTP 200, valid XML, 60 items, GUID/title/link/pubDate fields, and a retained payload hash. It is technically reachable but is not an issuer-disclosure source contract.
2. The route fails the required research-event gate: zero accepted ticker mappings in the probe; no issuer/instrument identity field; publisher-feed rather than disclosure identity; no established category/event lifecycle, update/supersession, pagination/incremental, or immutable raw-payload retention semantics. Its current local `news_latest.csv` export ends 2026-07-22, before the 2026-08-20 daily research session.
3. No generic source is promoted, acquired, or adapted. No crawler, manual ticker routing, production DB write, feed sync, or downstream event expansion occurs. Existing Event Context remains one HPG official-qualified completed event; source authority, corporate-action price adjustment, historical PIT, recommendation, valuation, liquidity, and sizing remain unchanged.
4. Any future generic issuer-event route requires an owner-approved provider/source contract with bounded route, explicit issuer identity, retained raw payload/reference, temporal/revision semantics, and permitted research authority before implementation.
## 2026-08-20 - Evidence-Aware Candidate Comparison V1

`EVIDENCE_AWARE_CANDIDATE_COMPARISON_V1 = READY_LOCAL` (`evidence_aware_candidate_comparison.py`, `push = NO`).

1. Comparisons require an explicit same-session ticker list, requested dimensions, and source identities. Normal shortlists are bounded 2–10; the existing deterministic 25-name Review Pack is permitted only in explicit compact-summary mode. Unknown tickers, invalid size, unsupported dimensions, and mixed sessions fail closed.
2. The engine compares only retained same-session technical values and research-lens states. Relative percentile outputs are directly comparable only under a shared cohort identity; incompatible qualified/provider descriptive cohorts produce `NOT_COMPARABLE_COHORT`. Individual fundamental values produce `COMPARISON_UNAVAILABLE` because the daily product retains no like-for-like values with compatible period/scope/unit evidence.
3. Pairwise output is restricted to field-grounded `FACT` statements and visible authority/missing-state cells. It never treats missing evidence as zero/worse, higher provenance as better economics, or a comparison as a winner, rank, recommendation, target, probability, expected return, liquidity, sizing, valuation, or PIT claim.
4. The comparison is a read-only consumer of Screener, Review Pack, Dossier, Task, Scenario, Event, Eligibility, and Relative Context identities. It changes none of their queue, owner annotation, historical state, or authority semantics.
## 2026-08-20 - Deterministic Market Regime & Breadth Research Context V1

`MARKET_REGIME_BREADTH_CONTEXT_V1 = READY_LOCAL` (`market_regime_breadth_context.py`, `push = NO`).

1. The versioned artifact measures only the exact-session 523-member `EMPIRICAL_ACTIVE_SHADOW_ONLY` cohort. Fixed 60% rules produce `BREADTH_MIXED`, `MOMENTUM_BREADTH_MIXED`, and `EMPIRICAL_COHORT_TREND_PARTICIPATION_MIXED`; these are contemporaneous participation descriptors, never authoritative Vietnam-market, bull/bear, forecast, timing, alpha, or expected-return claims.
2. The retained session has 219 above and 304 at/below MA20; 283 positive, 210 negative, and 30 zero 20-day momentum observations. Volatility is a same-session cross-sectional distribution only (median 0.01840; p25 0.01269; p75 0.02501), with no historical-regime statement. Provider-relative-volume is 523/523 `DERIVED_PROXY` and explicitly non-liquidity/non-turnover.
3. Existing Screener research-product counts are passed through and reconciled: 193 `POSITIVE_TREND_RESEARCH` and 320 `WEAK_TREND_RESEARCH`. They differ from breadth counts by predicate definition, not by data substitution. Market context is read-only metadata for Review Pack and Candidate Comparison; Strategy Eligibility remains unchanged.
4. The artifact is immutable per source identities/session and can later be joined to genuinely future observed outcomes without altering T-state. This milestone implements neither calibration nor regime-conditioned performance/backtesting.
## 2026-08-21 - Evidence-Aware Downside & Uncertainty Research Context V1

`DOWNSIDE_UNCERTAINTY_RESEARCH_V1 = READY_LOCAL` (`downside_uncertainty_research_context.py`, `push = NO`).

1. The 523-record exact-session artifact maintains six independent domains: observed technical downside context, empirical market context, scenario downside, evidence uncertainty, execution-risk assessability, and event visibility. No composite risk/downside score, rank, probability, expected loss, VaR, sizing, portfolio, valuation, or recommendation is emitted.
2. The real cohort has 210 negative 20-day momentum records, 304 at/below MA20, and 131 above the same-session p75 volatility threshold. These are observed contemporaneous states, not predictions of price decline. The technical domain is adverse for 378 records; a review flag applies to 389 with the exact technical and/or scenario reason list retained.
3. Evidence uncertainty is explicitly not business/economic risk; no event evidence is explicitly not no event risk. All 523 execution states are `EXECUTION_RISK_NOT_ASSESSABLE`, never illiquid/safe/high risk, because qualified liquidity/traded-value semantics remain unavailable. Scenario downside is available for 25 Review Pack cases and unavailable for 498 others.
4. Candidate Comparison receives the full independent vector as a non-ranking section and the review overlay preserves 25 source-linked blocks. The artifact can later be frozen at T and joined only to genuinely later observations; no calibration or outcome/hit-rate evaluation is implemented.

## 2026-08-21 - Price Structure & Breakout Research Context V1

`PRICE_STRUCTURE_BREAKOUT_RESEARCH_V1 = READY_LOCAL` (`price_structure_breakout_context.py`, `push = NO`).

1. The exact-session 523-record source exposes only 20 retained observations. V1 therefore uses current close against a prior 19-session close-only support/resistance candidate, explicitly excluding the current bar. The retained high/low fields are scale-incompatible with close and are not used; a 50-session structure is explicitly unavailable rather than synthesized.
2. The real deterministic distribution is 19 `BREAKOUT_CONFIRMED_BY_RULE`, 54 `NEAR_RECENT_RESISTANCE`, 315 `IN_RANGE`, 115 `NEAR_RECENT_SUPPORT`, and 20 `BREAKDOWN_CONFIRMED_BY_RULE`; range state is 47 compression, 331 expansion, and 145 stable. These state names describe a rule match only—not an expected move, recommendation, or successful breakout.
3. The `SHADOW_ONLY` context has a compact daily overlay, 523-eligible bounded price-structure lens, transparent Screener presets, a Scenario `FACT` overlay, downside reason linkage, Candidate Comparison cells, and 25 Review Pack blocks. Provider-relative-volume can only qualify an elevated proxy (87 records); it is never liquidity, tradability, institutional activity, or execution capacity.
4. This establishes current descriptive technical research only. `RAW_AS_TRADED`, historical PIT/backtest, corporate-action event adjustment, valuation, liquidity/sizing, and recommendation authority remain unpromoted.

## 2026-08-21 - Evidence-Aware Research Setup Classification V1

`RESEARCH_SETUP_CLASSIFICATION_V1 = READY_LOCAL` (`research_setup_classification.py`, `push = NO`).

1. Ten small multi-label rules are evaluated independently across all 523 exact-session shadow records. They describe observable trend continuation, breakout/near-resistance, breakout-plus-provider-volume-proxy, support/pullback, range compression, weakening, breakdown, and relative-strength contexts; they are neither exclusive strategies nor a composite score.
2. The real distribution is 278 multi-label, 167 single-label, and 78 `NO_DISTINCT_SETUP` records. Counts reconcile to source features: 193 trend continuation, 19 breakout, 13 breakout-plus-elevated provider-relative-volume proxy, 115 near support, 47 compression, 194 weakening, and 20 breakdown. Relative strength is 129 cases: 7 qualified-classification and 122 `QUALIFIED_LOWER_AUTHORITY` provider-descriptive cases; 10 cases are `UNAVAILABLE` due to unavailable comparable relative context.
3. Every setup evaluation carries its exact rule, observed inputs, source identities, qualification state, authority ceiling, and deterministic content identity. Market breadth is attached as a contemporaneous fact but is not a setup gate. `NOT_PRESENT` remains distinct from `UNAVAILABLE`; no AI or ML classification is involved.
4. The artifact is a read-only source for Screener, Candidate Comparison, daily/Review Pack, Scenario FACT, and Downside FACT overlays. It freezes clean setup-at-T cohort identities for a genuinely future retained-session join, without computing setup success, alpha, probability, edge, or recommendation accuracy. No PIT/raw-as-traded, liquidity, valuation, sizing, execution, or recommendation authority changes.

## 2026-08-21 - Prospective Research Context Extension V1

`PROSPECTIVE_RESEARCH_CONTEXT_EXTENSION_V1 = READY_LOCAL` (`prospective_research_context_extension.py`, `push = NO`).

1. The immutable original 2026-08-20 snapshot remains byte-stable at `prospective_research_snapshot:caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a`. The supplemental extension is a separate immutable object linked by that identity; it never rewrites the frozen original records, queue state, evidence authority, or AI/dossier lineage.
2. The extension was sealed after a precondition scan found no retained exact-session observation later than 2026-08-20. Its temporal contract accepts only source artifacts whose research session exactly equals T; data/research observation session, not file or implementation timestamp, is the controlling boundary. A future-session source fails closed.
3. All 523 frozen tickers link their existing Setup/Price/Downside/Relative state and one shared Market Context reference. The extension exposes 18 grouping keys, including the measured setup labels, `market:BREADTH_MIXED`, technical downside states, fundamental authority, and qualified/provider-descriptive/unavailable relative authority. It preserves provider-relative-volume as a proxy and `NOT_PRESENT` versus `UNAVAILABLE` setup states.
4. A minimal adapter now validates snapshot/extension identity and produces frozen grouping dimensions for a future strict-later observation. It returns `PENDING_FUTURE_OBSERVATION` today; no future data, attribution, outcome, performance, alpha, hit-rate, probability, recommendation, PIT/backtest, liquidity, sizing, valuation, or event authority was used or promoted.
