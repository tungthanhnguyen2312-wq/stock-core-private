# Decisions & Architectural Decision Records

## 2026-08-30 - Canonical Wide Fundamental Research Cohort Cutover V1

`CANONICAL_WIDE_FUNDAMENTAL_RESEARCH_COHORT_CUTOVER_V1 = PASS` (`push = NO`).

1. The narrowest current-default boundary is `fundamental_research_cohort_selection.resolve_current_fundamental_cohort`: default `CURRENT_WIDE_GOVERNED_V1` reads the retained wide scoring artifact and its qualified scaleout reconciliation, verifies identity, denominator, and zero residual, and fails closed on absence, corruption, or disagreement. It has no ticker list and never falls back to legacy data.
2. `fundamental_cross_sectional_scoring.execute()` and the canonical daily shadow resolver both use that selector. The daily chain and Producer manifest retain selector, cohort identity, denominator, and reconciliation identity. The normal canonical command has no new required option; the internal explicit `LEGACY_HISTORICAL_FROZEN_523_V1` seam is only for bounded replay/reproduction. Direct historical-base reproduction now also requires that explicit selector.
3. Existing scaleout evidence is reused, not regenerated: 523 → 1,507, 984 newly admitted, 157 newly admitted names with `NO_ELIGIBLE_PROVIDER_FACTS`, and 88 sector-special/out-of-scope records. The bounded 27/28 retained comparison remains 75/106→106/106 and 83/123→123/123 recommendation/invalidation retention; lifecycle recommendation context is 58 `UNCHANGED`, 0 `MISSING` under wide. No engine code for scoring, opportunity, recommendation, invalidation, or lifecycle changes.
4. Authority effect is exactly `CURRENT_RESEARCH_DEFAULT_COHORT_CUTOVER_ONLY`; stronger authority promotion is `NONE`. No provider/network work, registry mutation, canonical overwrite, primary checkout write, or reinterpretation/deletion of the frozen historical cohort occurred. The retained cutover validation artifact records the source identities and deterministic selector result.

## 2026-08-30 - Market-Wide Fundamental Research Cohort Scale-Out V1

`MARKET_WIDE_FUNDAMENTAL_RESEARCH_COHORT_SCALEOUT_V1 = PASS` (`push = NO`).

1. Root cause of the ~523-name fundamental cross-sectional research cohort, reconciled rather than asserted: `fundamental_cross_sectional_scoring.build_artifact()` was already fully generic (`denominator = len(base["operational_proxy"]["records"])`, no hardcoded cohort inside the function). The 523 boundary came entirely from `market_wide_historical_fundamentals_scaleout.execute()`'s default `p3f10_frozen` argument, which read the frozen 2026-08-20 `EMPIRICAL_ACTIVE_SHADOW_ONLY` 523-member snapshot (`p3f13_official_financial_evidence_scaleout.DEFAULT_P3F10`) even though `build_artifact()` itself was already parameterized by `p3f10_frozen`/`p3f13_current`. This is the identical class of finding the 2026-08-27 `FINANCIAL_FACT_COVERAGE_RECOVERY_AND_SCALEOUT_V1` milestone made for the sibling `market_wide_current_fundamental_research` pipeline.
2. New `fundamental_research_cohort_scaleout.py` fixes exactly that ceiling, generically: it reuses `financial_fact_coverage_recovery.build_extended_p3f10_artifact`/`build_extended_p3f13_artifact` (already existing, already tested, already proven against the full 1,507-name official research universe by the 2026-08-27 milestone) completely unmodified, and feeds their output into `market_wide_historical_fundamentals_scaleout.build_artifact` and `fundamental_cross_sectional_scoring.build_artifact`, both also completely unmodified. No engine file (`fundamental_cross_sectional_scoring.py`, `market_wide_historical_fundamentals_scaleout.py`, `financial_operational_proxy.py`, `market_wide_current_fundamental_research.py`, `p3f10_fundamental_evidence_scaleout.py`, `p3f13_official_financial_evidence_scaleout.py`) was edited by this milestone; `git diff` for this checkpoint touches only new files.
3. Membership widens 523 → 1,507 (984 newly admitted, residual zero — every officially-applicable ticker receives a manifest record). Within that wider membership, `financial_operational_proxy.py`'s pre-existing, deliberate `SUPPORTED_ENTITY_TYPES = {"corporate"}` sector boundary is preserved unchanged: 88 non-corporate/unresolved tickers correctly receive `ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE`, identically to how the narrow cohort's own bank/securities names were already treated. Of 1,419 corporate tickers, 1,259 reach `OPERATIONAL_PROXY_OR_VERIFIED_RESEARCH_EVIDENCE` and 160 remain `NO_ELIGIBLE_PROVIDER_FACTS` (157 of them newly admitted) — a genuine, unchanged evidence ceiling, not a cohort-membership defect. READY_RESEARCH_ONLY axis coverage grows roughly 2.5x market-wide (e.g. `PROFITABILITY_QUALITY` 449→1,229); thin `GROWTH_MOMENTUM` coverage (2→39) is reported honestly, never used as an artificial cohort limiter, per the existing independent-axis contract.
4. The narrow 523-member subset's own retained facts and derived_metrics are proven byte-identical under widening (zero mismatched tickers, zero missing). Percentile-based axis *scores* for those same tickers do recompute against the wider comparable population — the correct, expected behavior of the unmodified `AVAILABLE_FEATURE_PERCENTILE_MEAN/v1` formula run over a larger population, not a scoring-formula, threshold, or percentile-definition change (those remain byte-identical code). This distinction — same rule, different evidence-driven population — is the same one the 2026-08-27 recovery milestone drew for `market_wide_current_fundamental_research`'s entity-classification counts.
5. Bounded downstream replay (real retained local artifacts only, no network, primary Producer checkout read-only and never written) for 2026-08-27/2026-08-28 reuses `daily_session_shadow_recommendation.build`, `current_daily_decision_research_product.attach_decision_context`, and `multi_session_thesis_recommendation_lifecycle.build_artifact` verbatim, substituting only the wide `fundamental_cross_sectional_scoring` artifact for the narrow one as an ordinary input value. Session Bundle recommendation/invalidation retention closes fully: 75/106→106/106 and 83/123→123/123 (the residual 31/40 `TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION` cards, e.g. `AMP`, resolve to real, well-formed, non-fabricated `shadow_security_recommendation` records). The 27→28 lifecycle's 58 comparable records move from 41 `UNCHANGED`/17 `MISSING` to 58 `UNCHANGED`/0 `MISSING`; `comparable_count` itself is unchanged (it is Session-Bundle-membership-driven, not fundamental-cohort-driven).
6. Deliberately not done: `fundamental_cross_sectional_scoring.execute()`'s default and `daily_session_shadow_recommendation.SHARED_CONTEXT_RELATIVE_PATHS['fundamental']` are **not** repointed to the wide artifact. The narrow 523-member cohort remains the live canonical default. Promoting the wide cohort to the canonical default is a distinct, separate, owner-authorized cutover milestone — this one only proves the wide artifact is correct, evidence-respecting, and reproducible, matching this repository's established convention (the 2026-08-27 recovery milestone made the identical choice for its own sibling pipeline).
7. Bulk retained raw/canonical financial evidence (`operations-review/p1f-milestone-20260803/...`, `operations-review/governed-official-evidence-v1/...`, and per-session descriptive/tactical/bundle artifacts) is large, gitignored, operator-local data not tracked by a fresh `git worktree add` checkout. This milestone's tools read it via an explicit `--evidence-root`/CLI-path parameter (defaulting to this worktree, pointed at the primary Producer checkout for this run) rather than a new hardcoded default; only reads occurred against the primary checkout, and every write landed under this worktree's own `operations-review/` (gitignored, uncommitted).
8. Regression: 16 new tests (`tests/test_fundamental_research_cohort_scaleout.py`, mixing real end-to-end retained-evidence proof with synthetic-fixture unit tests) plus 5 new tests (`tests/test_replay_fundamental_cohort_scaleout_downstream_v1.py`) all pass. Focused regression across every touched/consumed module (`fundamental_market_opportunity_ranking`, `thesis_catalyst_downside_research_cases`, `shadow_action_readiness`, `fundamental_thesis_invalidation_precision`, `shadow_security_recommendation`, `action_instrumentation`, `daily_session_shadow_recommendation`, `daily_producer_pipeline`, `current_daily_decision_research_product`, `multi_session_thesis_recommendation_lifecycle`, `p3f10_fundamental_evidence_scaleout`, `p3f13_official_financial_evidence_scaleout`, `market_wide_current_fundamental_research`, `financial_fact_coverage_recovery`) is 176/182 passing; the 6 residual failures are confirmed pre-existing and unrelated (a `p3e_fundamental_coverage_closeout.py`/`financial_statement_template_recognizer.py` VNM `total_assets` ×1,000,000 scale/unit-ambiguity defect, and three `daily_producer_pipeline.py` tests for unrelated 2026-08-21 session registry data this fresh worktree does not carry) — no file either failure touches was modified by this milestone.

## 2026-08-30 - Canonical Daily Shadow-Recommendation Autosourcing V1

`CANONICAL_DAILY_SHADOW_RECOMMENDATION_AUTOSOURCING_V1 = PASS` (`push = NO`).

1. The auto-source insertion point is `daily_producer_pipeline.run_daily_producer()` immediately after completed-session registry input resolution/coherence validation and before `run_session_operation()`; this preserves the required dependency order and avoids building recommendation context inside Session Bundle construction.
2. The existing `daily_session_shadow_recommendation/v1` engine chain is reused without rule changes. Exact session market/tactical evidence comes from the registered session selection; its pre-existing session-independent retained contexts are explicitly named, not discovered by glob/latest or acquired. One immutable per-session retained chain is reused only when full canonical content/source identities match; a same-session difference, corruption, or session mismatch is an explicit integrity failure.
3. Normal canonical production supplies no manual parameter. The retained explicit seam remains for bounded/test/debug injection but is accepted only if it is the identical same-session auto-resolved `shadow_security_recommendation/v1` artifact; a conflict fails closed. Individual missing/not-ready recommendation records remain explicit local research absence and do not fail the market-data pipeline.
4. The bounded 27/28 canonical-producer replay auto-sourced the chain and retained recommendation/invalidation for 75/106 and 83/123 cards. It confirms lifecycle compatibility at 58 comparable names (41 `UNCHANGED` recommendation contexts, 17 `MISSING`); neither the 523-name upstream cohort boundary nor any authority was widened.

## 2026-08-30 - Daily-Session Shadow Recommendation and Invalidation Production V1

`DAILY_SESSION_SHADOW_RECOMMENDATION_AND_INVALIDATION_PRODUCTION_V1 = PASS` (`push = NO`).

1. `shadow_security_recommendation/v1` and its five upstream engines (`fundamental_market_opportunity_ranking`, `thesis_catalyst_downside_research_cases`, `shadow_action_readiness`, `fundamental_thesis_invalidation_precision`, `action_instrumentation`) were each already pure `build_artifact()`/`build()` functions taking plain `Mapping` inputs, with zero hardcoded path/session/ticker logic; every hardcoded frozen-cohort path lived only in each module's throwaway `execute()` convenience wrapper or its one-off `tools/run_*.py` script. No engine's rule, threshold, or label vocabulary was touched.
2. New `daily_session_shadow_recommendation.py` is orchestration only: it calls the six engines in their established two-phase, boundary-informed order (base shadow readiness → fundamental boundary precision → preliminary technical action → boundary-informed final shadow readiness → final technical action → shadow security recommendation), substituting the target session's own raw `market`/`tactical` research for the frozen-cohort inputs while reusing already-retained, legitimately session-independent context (fundamental cross-sectional scoring, valuation-research proxy, corporate events, TTM, A1/A2 temporal) exactly as the canonical Daily Producer pipeline already treats its own `fundamental`/`catalyst` dimensions. It fails closed (`DailySessionShadowRecommendationError`) on a market/tactical session mismatch or a missing session, and asserts the produced artifact's own `as_of_session` equals the requested session before returning.
3. `daily_research_session_operations.build_operation()`/`run_session_operation()` gained exactly one new optional parameter, `shadow_security_recommendation`, threaded to the pre-existing `current_daily_decision_research_product.build()` hook — the same additive pattern already used for `portfolio`/`macro`. A canonical run that does not supply it is unaffected byte-for-byte; the capability cannot make an unrelated Daily Producer session fail globally, since production of the artifact happens as a separate, prior step, never inline inside the session operation itself.
4. The bounded 2026-08-27→2026-08-28 replay (real, retained local artifacts only; no network; no registry mutation; no canonical-artifact overwrite) produced two genuine same-session `shadow_security_recommendation/v1` artifacts (523-name governed denominator, zero residual, each `as_of_session` matching its own day) and fed them through the existing, unmodified Session Bundle retention contract. Retention succeeded verbatim for 75/106 (27th) and 83/123 (28th) tickers; the remainder is explicit `TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION` (outside the pre-existing 523-name fundamental cross-sectional cohort, not a defect this milestone introduces or should paper over). The 27→28 lifecycle replay's 58 comparable records reproduce unchanged; 41 of them now carry retained recommendation+invalidation context (was 0 before this milestone) and all 41 are `UNCHANGED` label-to-label with zero newly-activated/cleared invalidations across the one trading day — an evidenced zero-transition result, not a gap — while the pre-existing UIC/VTV material tactical-confirmation-loss transitions are untouched. `authority_effect = NONE` throughout; no target, sizing, probability, performance, PIT, or RAW_AS_TRADED authority was created.

## 2026-08-30 - Session Bundle Decision-Context and Lifecycle Enrichment V1

`SESSION_BUNDLE_DECISION_CONTEXT_AND_LIFECYCLE_ENRICHMENT_V1 = PARTIAL_BY_EVIDENCE` (`push = NO`).

1. `current_daily_decision_research_product.build()` gained one new optional, additive input (`shadow_security_recommendation`) and one new `attach_decision_context()` step. For each Session Bundle card it retains the existing `shadow_security_recommendation/v1` packet's per-ticker `recommendation` and `fundamental_invalidation` verbatim — exact label, reason codes, warnings, authority boundaries, and upstream artifact identity — never translating a label, never deriving a recommendation from tactical state, and never recomputing an invalidation boundary from raw fundamentals.
2. Session coherence is a hard gate, not a preference: a retained upstream packet whose `as_of_session` does not equal the bundle's own session is rejected as explicit `SESSION_MISMATCH_...` unavailability, never silently attached as a misdated "current" value. A missing, unverifiable (tampered content hash), or ticker-absent upstream artifact is likewise explicit and reason-coded. Every card carries both fields even when unavailable (`None` plus a sibling `..._retention` status/reason record), matching the existing `_recommendation`/`_invalidation` `Mapping`-or-`None` contract `multi_session_thesis_recommendation_lifecycle.py` already relied on.
3. `multi_session_thesis_recommendation_lifecycle.py` required no change to read the new fields — its pre-existing `_recommendation`/`_invalidation` consumption contract already matched the retained shape exactly. The only change is additive: `_material()` now also emits `UPSTREAM_FUNDAMENTAL_INVALIDATION_CLEARED`, symmetric with the already-existing `UPSTREAM_FUNDAMENTAL_INVALIDATION_ACTIVATED`, since `INVALIDATION_CLEARED` was already a defined transition value that real data could never previously reach.
4. The bounded 2026-08-27→2026-08-28 replay reconstructs both retained Session Bundles (106 and 123 tickers) with the corrected builder, reusing only already-retained local artifacts (no network, no registry mutation, no canonical-artifact overwrite). The only existing `shadow_security_recommendation` artifact is as-of 2026-08-25 — a separate, frozen 523-name research cohort, not either daily session — so both sessions correctly report 0 retained / 100% explicit `SESSION_MISMATCH` or `TICKER_NOT_IN_UPSTREAM`. The pre-existing 123/58/65/48 denominator/comparable/initial-only/prior-only counts and the UIC/VTV material tactical-confirmation-loss result reproduce byte-identically, proving the fix changes nothing it should not. Direct unit tests separately prove same-session retention end-to-end. Authority effect `NONE`: no recommendation or invalidation was generated, translated, or recomputed. The genuine remaining blocker — `shadow_security_recommendation` has only ever run once, against the frozen cohort, never per daily session — is a future acquisition/scheduling gate, not something this milestone opens.

## 2026-08-30 - Multi-Session Thesis and Recommendation Lifecycle V1

`MULTI_SESSION_THESIS_AND_RECOMMENDATION_LIFECYCLE_V1 = PARTIAL_BY_EVIDENCE` (`push = NO`).

1. Lifecycle V1 compares only retained qualified Session Bundle snapshots through an explicit governed session chain; it never uses calendar-day subtraction, reconstructs history, or recomputes an upstream research engine.
2. Component transitions preserve exact upstream opportunity, tactical, strategy, scenario, recommendation, and structured-invalidation values where present. Missing dimensions are `MISSING`, not neutral or directional. No ordering is imposed on recommendation labels, high-risk states, WAIT, or AVOID; ambiguous changes remain `STATE_TRANSITION`.
3. The only directional lifecycle semantics are an explicit newly triggered upstream fundamental invalidation (`INVALIDATED`) and a gain of the existing `BREAKOUT_READY` confirmation state (`CONFIRMED`). Recommendation-label changes, priority gain/loss, and confirmation loss are material-change reasons, not new actions.
4. The retained 27→28 pair demonstrates 58 comparable records but lacks per-security shadow recommendation and structured invalidation outputs. The artifact remains prospective multi-session research only, with authority effect `NONE`: no new recommendation, target, sizing, probability, P&L, performance, backtest, PIT, or RAW_AS_TRADED claim is emitted.

## 2026-08-30 - Market-wide Implied-Growth and Reverse-Valuation Research V1

`MARKET_WIDE_IMPLIED_GROWTH_AND_REVERSE_VALUATION_RESEARCH_V1 = PARTIAL_BY_EVIDENCE` (`push = NO`).

1. The new projection is an adapter over existing valuation semantics, not a third valuation ontology. `EXISTING_INTRINSIC_VALUE_GAP_V1` uses only an existing upstream per-share intrinsic result and an upstream current price; `REVERSE_FCFF_TERMINAL_GROWTH_V1` uses the existing FCFF perpetuity relationship and solves only terminal growth inside explicit supplied bounds.
2. WACC, forecast FCFF, market enterprise value, source identities, and solver bounds are required inputs. Missing inputs, invalid price/economics, an inadmissible terminal-growth bound, no root, and non-convergence fail closed. Proxy multiples and fundamental scores are retained context only and never supply assumptions.
3. The retained 2026-08-28 replay evaluates the 523-record current-valuation research denominator with 0 READY/0 PARTIAL/4 BLOCKED/519 UNAVAILABLE. No governed upstream intrinsic output or sourced FCFF fixed-input envelope exists, so no numeric value gap or implied growth is emitted.
4. The result is `CURRENT_RESEARCH_ONLY`, `is_actionable=false`, and has authority effect `NONE`: no target, recommendation, sizing, probability, historical PIT, or RAW_AS_TRADED authority is created. Any future expansion requires an upstream qualified current intrinsic-input/output envelope; it is not an authorization to create assumptions or acquire data.

## 2026-08-28 - FPT FY2025 Debt Line-Code Cell Disambiguation V1

`FPT_FY2025_DEBT_LINE_CODE_CELL_DISAMBIGUATION_V1 = OUTCOME_A_FPT_DEBT_QUALIFIED_BY_CELL_LEVEL_CODE_EVIDENCE` (`push = NO`).

1. A malformed primary TSV code token is never repaired. `match_geometry_ambiguous_line_code_cell` may locate one malformed OCR code cell only when the existing OCR-only physical-line reconstruction, code/value bands, borrowing-label terms, and two exact monetary cells produce one row. It returns the original token (`3²0` here), its bbox, and the unchanged row/value lineage; a token outside the code band, a missing label identity, multiple candidate cells, or ambiguous monetary cells fails closed.
2. `ocr_cell_code_read/v1` is the only secondary procedure: the deterministic 240-DPI source render is cropped to the discovered code-band × code-row rectangle, hashes the crop, expands it by fixed 4× Lanczos, and invokes Tesseract once with fixed English/PSM-8 and a digits-only whitelist. The whitelist is limited to the accounting line-code field. Only raw ASCII digits satisfying the existing 1–3 digit code contract and exactly matching the already-declared taxonomy code can qualify; an empty, invalid, or conflicting raw result blocks. No DPI/PSM/threshold/rotation loop, Unicode replacement, monetary OCR, or ticker-specific conditional exists.
3. The retained FPT crop returns raw `320`; p10 code 338 stays primary-exact. Their source-bound values are 19,169,697,497,955 and 1,903,789,988,184 VND, so the pre-existing explicit component sum qualifies debt at 21,073,487,486,139 VND. P3-F13 remains additive/non-overwriting and replays 138→142. FPT current primary-core coverage moves 6→7/7, fundamental readiness stays `PARTIAL` because only compatible prior annual periods are absent, leverage is supportable, and valuation input availability remains partial.
4. The deterministic owner-focus queue's next P0 target is PNJ FY2025 `net_income`, an existing image-only official-document opportunity. This does not authorize a further FPT technique or any next milestone; no network, provider, package/model install, production DB, Dashboard, VALUE, ranking, recommendation, target, probability, sizing, or PIT promotion occurred.

## 2026-08-28 - FPT FY2025 Image-Table TSV OCR Evidence Qualification V1

`FPT_FY2025_IMAGE_TABLE_TSV_OCR_EVIDENCE_QUALIFICATION_V1 = OUTCOME_B_OCR_GEOMETRY_WORKS_WITH_NUMERIC_AMBIGUITIES_BLOCKING_SOME_FACTS` (`push = NO`).

1. The retained FPT issuer-IR scan is handled by a generic image-table TSV adapter: deterministic PyMuPDF grayscale render, hashed render identity, Tesseract TSV word boxes, raw sequence/confidence, and explicit `OCR_TSV_POSITIONED_TOKEN` provenance feed the existing physical-line and X-band contract. Native tokens retain `NATIVE_PDF_POSITIONED_TOKEN`; the OCR header extension restored the native fused-header fallback, and HPG/PAN/VNM/AAA behavior is unchanged.
2. Exact OCR numeric cells on p12 independently qualify FY2025 revenue (line 10, 70,112,825,100,710 VND) and consolidated parent-attributable net income (line 61, 9,376,127,629,501 VND); p13 OCF qualifies at 10,136,043,915,911 VND. p8 cash exactly corroborates its existing fact. The page-10 line-320 code is retained as OCR text `3²0`; no substitution is allowed, so debt cannot use line 300 or an inferred correction and remains blocked until both exact line-320 and line-338 evidence exist.
3. P3-F13 ingress is ephemeral and non-overwriting: cash is `EXACT_MATCH`; revenue, net income, and OCF are new qualified keys (138→141 facts). FPT's retained-only fundamental replay becomes `PARTIAL` with exact margin and cash-flow-to-earnings plus ROA/ROE ending-balance proxies; it still has no prior annual period and no qualified debt. Current valuation/readiness counts, VALUE, ranking, recommendations, sizing, and PIT authority remain unchanged.
4. The updated owner-focus matrix moves FPT from three to six current core facts; YoY and trend remain unavailable. The exact next evidence target is FPT FY2025 `total_interest_bearing_debt` on the same retained document through `IMAGE_ONLY_TABLE_OCR`, not a new acquisition or an automatic next milestone.

## 2026-08-27 - Owner-Focus Core Financial Panel Coverage & Evidence Priority V1

`OWNER_FOCUS_CORE_FINANCIAL_PANEL_COVERAGE_AND_EVIDENCE_PRIORITY_V1 = OUTCOME_B_OWNER_FOCUS_PANEL_BUILT_WITH_SECTOR_CONTRACT_GAPS` (`push = NO`).

1. The new artifact is a deterministic consumer of P3-F13, the retained PDF corpus inventory, the owner-focus configuration, and the existing current-fundamental provider envelope. It covers exactly SSI, HPG, PAN, EVF, VNM, FPT, PVD, NVL, POW, and PNJ in configured order; it neither queries a network surface nor substitutes acquisition fixtures.
2. Core panels are sector-aware and contain only canonical identities already present in the taxonomy. SSI uses the promoted securities vocabulary, never corporate revenue/debt semantics. EVF remains a finance-company schema-only boundary: no real-data proof corpus or retained official document exists, so `SECTOR_CORE_PANEL_CONTRACT_INCOMPLETE` is an explicit result rather than a new architecture or a corporate fallback.
3. Temporal coverage is derived only from compatible annual facts matching scope/currency/unit. Current level, two-period YoY, and three-period trend are separately represented; interim/provider periods remain distinct. HPG preserves the corrected code-61 parent-attributable FY2022/FY2023 facts plus FY2024 and is therefore closed for primary current/YoY/trend coverage, not automatically first for more extraction.
4. The lexicographic evidence queue is not an investment score. `P0` selects missing current primary core evidence, followed by consecutive-period, valuation-input, cash-flow-quality, secondary, and sector-contract reasons, with deterministic ordering. The current leading retained-evidence opportunity is FPT FY2025 parent earnings/revenue/debt in an image-only official report; it is reported as `IMAGE_ONLY_TABLE_OCR` for a future authorized capability and is not run here.

## 2026-08-27 - HPG Parent-Attributable Net Income Semantic Correction V1

`HPG_PARENT_ATTRIBUTABLE_NET_INCOME_SEMANTIC_CORRECTION_V1 = OUTCOME_A_CANONICAL_CONSOLIDATED_NET_INCOME_CORRECTED` (`push = NO`).

1. Consolidated canonical `net_income` means the parent-attributable line 61. The generic financial-statement extractor therefore permits the legacy line-60 fallback only when statement scope is explicitly `separate` or `unconsolidated`; it cannot silently qualify consolidated or unproven scope.
2. A single governed active-fact correction registry is exact-keyed by the old retained `(document_sha256, citation_id)`. It corrects only HPG FY2022 from p106/code 60/8,444,429,054,516 VND to p107/code 61/8,483,510,554,031 VND and FY2023 from p88/code 60/6,800,388,315,081 VND to p89/code 61/6,835,064,334,356 VND. The retained historical citation JSONL is immutable; active lineage records the superseded citation and correction reason, then cites the independently qualified structural row.
3. The correction is accounting-reconciled: parent-attributable earnings plus the stated non-controlling-interest share equals each prior consolidated-profit total exactly. All six HPG structural candidates now are `EXACT_MATCH`; collision handling remains non-overwriting and no candidate enters ingress.
4. Only relevant derived outputs are recomputed: HPG FY2022→FY2023 earnings YoY is -19.4312%, net margins are 5.9993% and 5.7460%, and OCF-to-earnings is 1.4472x and 1.2645x. Current HPG P/E consumes unchanged FY2024 earnings, so valuation research-usable coverage and READY/VALUE authority do not change. No acquisition, provider, database, dashboard, strategy, recommendation, ranking, target, sizing, or PIT authority is opened.

## 2026-08-27 - HPG Column-Major Financial Table Geometry Disentanglement V1

`HPG_COLUMN_MAJOR_FINANCIAL_TABLE_GEOMETRY_DISENTANGLEMENT_V1 = OUTCOME_A_HPG_COLUMN_MAJOR_GEOMETRY_QUALIFIES_FACTS` (`push = NO`).

1. Existing `pypdf` visitor text matrices are sufficient for this retained-native-text capability. The page-evidence contract now preserves deterministic token origins, raw callback order, conservative-width bbox provenance, and parser identity; no PDF dependency, OCR, network, provider, or document was added.
2. The generic `COLUMN_MAJOR_WITH_LINE_CODES` path reconstructs physical lines from bounded, per-page geometric tolerance, then derives semantic X-bands only after finding explicit two-period header evidence. It uses header order, not a left/right convention, to bind current/comparative value bands; requires a canonical metric's existing line code to occur inside the CODE band; treats NOTE as a distinct optional band; and blocks overlapping/ambiguous cells. Wrapped labels retain all fragments and are joined only when an immediately preceding label-only physical line has compatible geometry.
3. HPG's retained FY2022 and FY2023 reports each independently yield page/table/row/period-cited revenue, parent-attributable net income, and operating cash flow. Their P3-F13 identities already collide: revenue and OCF independently `EXACT_MATCH`, while parent-attributable code-61 net income is a `VALUE_CONFLICT` with the prior materialization. No candidate enters ingress and no official fact is overwritten. AAA/PAN/VNM behavior and VCB/SSI corporate exclusion remain unchanged; no valuation, strategy, VALUE, or PIT authority expands.

## 2026-08-27 - Official Financial Normalization Scale Correction V1

`OFFICIAL_FINANCIAL_NORMALIZATION_SCALE_CORRECTION_V1 = OUTCOME_A_NORMALIZATION_DEFECT_CORRECTED_PANEL_CLEAN` (`push = NO`).

1. `Fact.value` means base currency for qualified monetary facts: `parsed_display_value × explicitly qualified unit_scale`. The generic boundary rejects missing currency or non-positive/unknown scale and never uses magnitude inference.
2. Ten pre-existing errors are corrected only by exact `(document_sha256, citation_id)` registry entries with retained display values: VNM FY2024 revenue/assets and VRE FY2025 cash, current liabilities, net income, operating cash flow, revenue, equity, assets, and total debt. Historical artifacts stay untouched; the active fact retains its original lineage plus correction provenance.
3. The current 138-fact panel is clean: 128 existing exact + 10 corrected, mismatch 0 and residual 0. VNM structural reconciliation changes from `VALUE_CONFLICT` to `EXACT_MATCH`; VRE ratios remain unchanged because their components scale together, while VNM net margin and ROA are corrected because only revenue/assets were wrong. Coverage, readiness, valuation, and VALUE authority do not expand.

## 2026-08-27 - Bilingual Non-Form-Code Corporate Financial Table Recognition V1

`BILINGUAL_NON_FORM_CODE_CORPORATE_FINANCIAL_TABLE_RECOGNITION_V1 = OUTCOME_B_STRUCTURAL_RECOGNIZER_WORKS_PARTIALLY` (`push = NO`).

1. **Structural recognition is a fallback, not a rewrite.** `official_financial_structural_table.py` is dispatched from `official_financial_pdf_page_evidence.extract_candidates` only when the existing exact-form `discover_tables` finds zero tables on a corporate document. AAA's path never reaches the new module; every pre-existing test is byte-identical.
2. **Three genuine layout families, not one generic "bilingual" shape.** Real retained evidence across VNM/HPG/PAN shows a row-major-with-codes family (label+code+note+values on one line), a column-major-with-codes family (the PDF's text layer draws the whole table as parallel label/code/value runs, confirmed on HPG), and a row-major-no-codes IFRS-style family (VNM, no VAS line code at all). Each needed distinct row-matching logic; a single generic row walker silently mispairs labels and values on the column-major family.
3. **Consolidated-scope selection required a real-evidence bar, not a heading-text heuristic alone.** A table-of-contents entry, a section divider, an auditor's-report sentence, a notes-page cross-reference, and a segment-reporting sub-table can all contain the exact phrase "Consolidated Balance Sheet" without being the primary statement. The recognizer requires the phrase to open its own occurrence (not follow a preposition/article), excludes known front-matter/divider pages by their own heading, and — when more than one candidate block still remains — requires the block to ALSO independently resolve real unit and period-column evidence before selecting it.
4. **Two real correctness bugs were found only by cross-checking extracted values against known ground truth, not by unit tests in isolation.** (a) A PDF text-layer artifact renders some numbers with a spurious space before the thousands comma ("37 ,165,930"); the original tokenizer silently matched only the tail ("165,930") as if it were the whole value. (b) `normalized_value` was never multiplied by the table's own `unit_scale`, understating every value on a non-1-scale table (VNM's "VND million" table) by that factor. Both are fixed; a fragmented number now fails closed as `UNPARSEABLE` rather than silently truncating.
5. **Phase 13 reconciliation is additive evidence, never a silent overwrite.** All 7 target tickers already carry `OFFICIAL_QUALIFIED` P3-F13 facts for the identities this milestone targets, sourced through an earlier, differently-provenanced route. `reconcile_against_existing_panel` classifies each newly qualified candidate against the existing panel (`EXACT_MATCH` / `VALUE_CONFLICT` / `NOT_COMPARABLE_NEW_KEY`) and marks a colliding key ineligible for ingress; none of this milestone's 6 candidates was merged. 5/6 are `EXACT_MATCH` (strong independent corroboration); 1 is a real `VALUE_CONFLICT` — VNM's existing revenue entry stores its displayed figure without applying its own stated `unit_scale`, understating revenue 1,000,000x — flagged for owner review, not resolved here.
6. **Net P3-F13 coverage is unchanged by design, not by shortfall.** Because zero of the 6 new candidates are eligible for ingress (Decision 5), official-qualified cells remain 70 and valuation `RESEARCH_USABLE` counts are unchanged. This is a provable no-op (`merge_document_qualified_facts_into_panel` was never invoked with an eligible key), consistent with "do not optimize for a nonzero fact count."
7. **Debt extraction and three of seven target documents are honest, unresolved gaps, not silently forced.** `total_interest_bearing_debt`'s two-component aggregation stays Vietnamese-anchor-only (extending it needs its own evidenced anchors, out of this bounded pass). QNS75/GAS/QNS41 correctly report no recognized table: QNS75 is the narrative annual-report volume whose statements are a separate retained document, GAS is a bare disclosure notice, and QNS41's notes-dominant front-matter pages did not independently resolve consolidated scope or a clean period year.

## 2026-08-27 - Retained Official Financial PDF Extraction Scaleout V1

`RETAINED_OFFICIAL_FINANCIAL_PDF_EXTRACTION_SCALEOUT_V1 = OUTCOME_B_RETAINED_PDF_EXTRACTION_PARTIAL_LAYOUT_CEILING` (`push = NO`).

1. The scaleout denominator is every local `%PDF-` byte set under `operations-review`, deduplicated by SHA-256 before replay. Duplicate paths preserve provenance but cannot trigger a second extraction; image-only documents are inventoried and never OCR'd in this milestone.
2. The existing page/table extractor is replayed unchanged. AAA reproduces its already-qualified facts exactly. Native-text reports without the current exact VAS form-code/table proof remain blocked rather than receiving a new ticker recipe or fuzzy alias; VCB/SSI remain bank/securities layout boundaries and receive no corporate mapping.
3. No newly qualified fact entered P3-F13. Official financial cells remain 70, valuation research coverage and READY/VALUE remain unchanged, and no provider/network/DB/strategy authority was opened. The exact next capability is structural bilingual/non-form-code corporate table recognition with the same page/row/period evidence requirements.

## 2026-08-27 - Official Financial PDF Page/Table Extraction and Citation V1

`OFFICIAL_FINANCIAL_PDF_PAGE_TABLE_EXTRACTION_AND_CITATION_V1 = OUTCOME_A_GENERIC_PDF_EXTRACTION_QUALIFIES_NEW_OFFICIAL_FACTS` (`push = NO`).

1. `official_financial_pdf_page_evidence/v1` is a retained-bytes, native-text extraction boundary—not an acquirer or a fact store. It verifies the source SHA-256 before parsing, emits deterministic page text hashes and identities, and preserves table/row evidence and native coordinates only where the text layer supports them. OCR/provider fallback is not activated.
2. Explicit AAA FY2024 PDF claims establish issuer, annual 2024 period, consolidated audited scope, VND, and unit scale 1. Five statement-table fragments yield exactly seven cited canonical corporate facts: cash, total assets, equity, total interest-bearing debt (with disclosed components), revenue, parent-attributable net income, and operating cash flow. Missing currency/scale, unproven period, blocked candidate, ambiguous mapping, or unsupported bank/securities layout is fail-closed.
3. Qualified page/table-cited rows enter only the existing P3-F13 constrained ingress. The 1,507-name retained-evidence replay moves the financial identity inventory from 64 to 70 official-qualified cells, residual zero. AAA becomes `OFFICIAL_QUALIFIED` but only `PARTIAL`: no 2023 official fact exists for its YoY calculations.
4. This is an evidence/citation gain, not valuation or strategy authority. Research-usable valuation coverage remains market cap 888, P/E 9, P/B 10, P/S 9, EV 9, EV/Sales 9, EV/EBITDA 0, with READY/VALUE 0. No provider/network/production DB/Dashboard mutation, recommendation, ranking, target, sizing, or PIT promotion occurs.

## 2026-08-27 - Approved Issuer-IR Official Financial Evidence Cohort V1

`APPROVED_ISSUER_IR_OFFICIAL_FINANCIAL_EVIDENCE_COHORT_V1 = OUTCOME_C_APPROVED_ROUTES_CURRENT_EVIDENCE_CEILING` (`push = NO`).

1. The acquisition boundary is exactly ABS, ABW, ACB, MBB, MWG, TCB, AAA, AAT, and BID on their owner-approved issuer-IR hosts. ABT remains rejected. One foreground pass used bounded same-host index/document resolution only; there was no provider, Dashboard, production-store, retry, polling, or archive crawl path.
2. A document is counted only if it is a same-host PDF with a PDF content signature. Category/detail HTML is preserved as a resolver record, never relabelled as a financial statement. The 18-document ceiling was respected (actual 1): AAA FY2024 annual report, content hash `fa5a765bf5214c56a609361699a04e9d527e99b34c18c2ff52ac12aecd197fd8`.
3. The AAA PDF lacks the complete page/table-bound metadata and canonical-value extraction needed by `official_financial_filing_evidence`/P3-F13. No source-absent unit, scope, audit state, currency, period, or numeric scale is inferred, so it creates no qualified fact. Every other route has an explicit terminal disposition retained in the cohort artifact.
4. The P3-F13 panel now has a constrained additive ingress for future cited, qualified document facts; it rejects uncited/unqualified rows. Bank inputs remain limited to bank canonical identities, and corporate revenue/debt/EV-family semantics are not manufactured for ACB/MBB/TCB/BID. Current run is a panel no-op: 0 facts, conflicts, readiness/valuation/authority changes.

## 2026-08-27 - Annual provider financial metadata retention and flow semantic corroboration V1

`ANNUAL_PROVIDER_FINANCIAL_METADATA_RETENTION_AND_FLOW_SEMANTIC_CORROBORATION_V1 = OUTCOME_B_PROVIDER_ANNUAL_METADATA_RECOVERED_SEMANTICS_PARTIAL` (`push = NO`).

1. **Retain raw before parsing.** KBS's existing approved annual endpoint is captured as exact immutable response bytes and SHA-256 before the installed adapter discards `Head`/`Audit`/`Unit` metadata. The first eight empty payloads are retained as a request-contract correction record, not silently retried as semantic evidence; the corrected eight calls exhaust but do not exceed the 16-request budget.
2. **Narrow sidecar, exact lineage.** `provider_financial_source_metadata/v1` keys provider, exact route/parameters, ticker, family, annual fiscal period, raw response hash, and derived adapter-payload hash. It joins only those exact payloads; annual and quarterly modes cannot cross-propagate.
3. **KBS `United` is scope, not scale.** Source label `Hợp nhất` is retained as the provider's consolidated statement-scope indicator. It is not a numeric unit. Report/update dates and audit status are recovered; currency, numerical unit and scale are not exposed and remain unknown. The documented `unit=1000` request plus adapter `×1000` transform remains an adapter transform only.
4. **No promotion from partial metadata.** Even with scope/date/audit provenance, flow facts have no provider-owned currency/unit contract and no aligned same-year official anchors in this bounded projection. Semantic-basis and valuation outputs remain unchanged; PVD/VNM are not reopened. The next gate is exact-route provider currency/unit evidence plus independent aligned flow anchors.

## 2026-08-27 - Annual provider financial history retention repair and flow reconciliation V1

`ANNUAL_PROVIDER_FINANCIAL_HISTORY_RETENTION_REPAIR_AND_FLOW_RECONCILIATION_V1 = OUTCOME_B_ANNUAL_HISTORY_RECOVERED_SEMANTICS_PARTIAL` (`push = NO`).

1. **Annual is a separate retained period contract.** `*_year.parquet` is replayed only into additive annual observations/facts; no quarterly byte or fact is overwritten. The existing filename collision explains historical loss, while KBS `YYYY-Năm` required an explicit annual column parser repair.
2. **Replay before acquisition; acquisition was exact and bounded.** Nine repository annual payloads were replayed first. They did not overlap the official-citation panel, so the approved 8-issuer × 3-family plan ran once per route (24/24 successful) with no retry, failover, delay, scheduler, or production-database write. Adapter-return parquet bytes and hashes plus request dispositions are retained.
3. **Missing provider metadata stays missing.** Acquisition-envelope ticker/provider/family identity is recorded separately from provider metadata. Report dates, audit/review, scope, currency and unit are `None`/unknown where the adapter did not expose them. KBS’s documented upstream multiplier is retained as a transform method, never inferred from magnitude.
4. **Annual numerical matches do not widen authority.** Fourteen aligned annual exacts exist, but flow and unresolved-scope/unit rows remain non-comparable; PVD/VNM remain untouched. Existing semantic-basis evaluation has zero absolute-qualified shapes and the isolated valuation replay is byte-identical. The next evidence gate is retained provider-owned annual scope/currency/unit metadata plus independent flow corroboration.

## 2026-08-27 - Provider Financial Semantic Basis Qualification V1

`PROVIDER_FINANCIAL_SEMANTIC_BASIS_QUALIFICATION_V1 = OUTCOME_C_RETAINED_PROVIDER_ABSOLUTE_SEMANTICS_REMAIN_UNQUALIFIED` (`push = NO`).

1. **Both evidence legs are required, not either.** A `(provider, statement_family)` shape may
   qualify `PROVIDER_ABSOLUTE_RESEARCH_QUALIFIED` only with (a) provider-owned schema or explicit
   library-contract evidence, **and** (b) zero-disagreement, discriminating (≥2 issuers, ≥5x
   magnitude spread), official-anchor reconciliation. Leg (a) alone is a ratio/pattern identity —
   internally consistent with a hypothesis, never an independent anchor — the exact trap
   `docs/kbs_empirical_basis_qualification.md` already names for a different provider. Leg (b)
   alone on a single ticker is explicitly excluded by the milestone brief.
2. **Installed library source beats a live probe.** `vnstock==4.0.4`'s own source
   (`vnstock/explorer/kbs/financial.py`) proves KBS requests `unit=1000` and multiplies every value
   by 1000.0 before returning it — stronger evidence than any fresh network capture, since it shows
   the exact transform, not a schema snapshot. `vnstock/explorer/vci/financial.py` has zero
   occurrences of unit/scale/currency handling of any kind. A bounded Phase-4 live probe was
   evaluated and skipped: it could not change the outcome, since leg (b) is blocked by data
   availability (no retained annual payloads), not remaining schema uncertainty, and recovering
   that history is out of this milestone's scope ("do not acquire broad new financial coverage").
3. **Real reconciliation found real disagreement, not just absence of evidence.** `(VCI,
   balance_sheet)` is the only shape with any official-anchor evidence: 6/8 issuers agree exactly
   on `shareholders_equity`, 5/7 on `cash_and_cash_equivalents` — but PVD (~25,250x) and VNM
   (~2.7%) reproducibly disagree on both. A shape with live counter-examples in its own tested
   sample is not "consistent reconciliation" regardless of how many other issuers agree; this is
   the concrete case the "no single-ticker proof may become market-wide authority" rule protects
   against, generalized to a small-sample proof with visible contradictions. Flagged (not fixed —
   different owner/lane): PVD's and VNM's own official citations may themselves be wrong (PVD's
   635,711,153 VND cited "total equity" is implausibly small) or scope-mismatched.
4. **One real, unrelated retention/propagation bug found and fixed.**
   `canonical_fact_store.load_official_citations` mapped citation metric `cash_and_equivalents` to
   canonical name `cash_and_equivalents`, but `canonical_financial_facts.METRIC_REGISTRY` spells
   the same concept `cash_and_cash_equivalents` — the identical pre-existing two-spellings
   correspondence `financial_fact_coverage_recovery.OFFICIAL_PANEL_CANONICAL_METRIC_ALIAS` already
   documents for a different consumer of the same two names. The citation silently never matched
   any built fact. Fixed the mapping value (not the citation file, which correctly uses the
   official-evidence-panel's own established spelling).
5. **Per-fact `PROVIDER_EXACT_RESEARCH_USABLE` is additive and independently gated.** New
   `provider_financial_semantic_basis.classify_provider_exact_research_usable` requires a fact's
   own `qualified`/`official_citation_agreement` status **and** its own independently-resolved
   `statement_scope` (never `unknown`) — belt-and-suspenders against a coincidental value match
   masking a scope mismatch. Wired into `financial_fact_coverage_recovery.classify_identity_cell`
   as a new optional parameter; omitting it reproduces prior behavior byte-for-byte (verified by
   test). Finds 10 real qualifying facts today, all for tickers already `OFFICIAL_QUALIFIED` for
   the same identity via the separate p3f13 panel — zero net inventory-cell change, by construction
   (the citation pool and the `PROVIDER_TIER` pool are disjoint today), not by an implementation
   gap. QNS is an instructive near-miss: its cash value matches its citation exactly, but zero
   minority interest leaves its own `statement_scope` unresolved, so the belt-and-suspenders check
   correctly withholds the tier.
6. **Full-universe recompute: 0 cells changed, valuation byte-identical.** 12,914-cell inventory
   before/after identical in every state count (residual 0 both times); rerun current-valuation
   artifact's `artifact_sha256` is byte-identical to the pre-milestone one. `READY`/`VALUE` stay
   0/1,507. No official promotion, no new provider, no acquisition, no ticker-specific branch.

Validation: `tests/test_provider_financial_semantic_basis.py` (25 tests covering all 17 named
requirements) plus the full pre-existing suite touching every module reused
(`test_canonical_financial_facts.py`, `test_financial_fact_coverage_recovery.py`,
`test_pan_fy2024_financial_identity_qualification.py`,
`test_ssi_fy2024_financial_identity_qualification.py`,
`test_export_ai_bundle_pillar_a_cache.py`) all pass; `py_compile`; `git diff --check`. Zero network
in any deterministic test; the one bounded, read-only, zero-write, zero-network pass over
`dashboard-runtime` (reconciliation + evidence loading) touches only the 8 tickers that carry an
official citation, by construction.

## 2026-08-27 - Current Financial Fact Coverage Recovery and Scale-Out V1

`CURRENT_FINANCIAL_FACT_COVERAGE_RECOVERY_AND_SCALEOUT_V1 = OUTCOME_B_BOUNDED_RECOVERY_PARTIAL` (`push = NO`).

1. **Root cause, not a new engine.** `market_wide_current_fundamental_research.py` (and the P3-F10/P3-F13 layers it composes) has only ever examined the frozen 523-name "empirical active cohort" snapshot captured on 2026-08-20. The retained raw/canonical financial stores those same builders already read (`operations-review/p1f-milestone-20260803/shadow-build-a/data/market-wide-financials/`, `.../shadow-build-b/data/canonical-financial-facts/`) independently carry observations for 1,493 tickers, 972 of which have at least one usable (non-`unavailable`-status) canonical fact that was never looked at, purely because they fall outside the 523-name membership list. This is a mapping/scope gap in already-retained evidence, not a missing source.
2. **Reuse, not recreate.** New `financial_fact_coverage_recovery.py` calls three already-existing, already-tested generic builders completely unmodified, only fed a wider ticker membership: `p3f10_fundamental_evidence_scaleout.build_scaleout_artifact` (already parameterized by `cohort`/`raw_records`/`canonical_records`, never hardcoded to any cohort internally), `p3f13_official_financial_evidence_scaleout.build_scaleout_artifact` (cohort membership is derived from `p3f10_artifact["instrument_dispositions"]` directly — it never reads the frozen bundle itself, so it widens automatically), and `market_wide_current_fundamental_research.build_artifact` (entity-class resolution, trajectory context, authority-tier assembly — identical per-ticker logic already applied to the narrow 523). No line of any of those three files changed. New `tools/derive_financial_fact_coverage_recovery_v1.py` orchestrates the widen → rerun-valuation → report pipeline and writes only to a new `operations-review/current-financial-fact-coverage-recovery-and-scaleout-v1-20260827/` directory.
3. **Verified no silent change to the narrow cohort.** `tests/test_financial_fact_coverage_recovery.py::test_widening_cohort_is_byte_identical_for_the_narrow_subset` rebuilds both the narrow (523) and wide (1,507) fundamental artifacts from the same retained inputs and asserts every one of the 523 already-covered tickers' records are byte-identical between the two runs, and that the official-qualified issuer count (13) is unchanged. Widening only adds records for previously-unexamined tickers; it never mutates an existing one.
4. **Entity-identity reconciliation is case B (stale/incomplete routing), not genuinely-unknown classification.** `market_wide_current_fundamental_research._entity_class_resolution` already resolves entity class from a market-wide-scoped evidence hierarchy (official readiness > P2-E/P2-E3 qualified classes > retained P3-F10 sector > VCI provider-industry snapshot), but was only ever invoked for the 523-name cohort. Rerunning the exact same function over the full 1,507-name universe resolves 1,407 of 1,412 raw-`unknown` tickers (mostly via the already-approved `VCI_PROVIDER_INDUSTRY` research-only mapping, 1,392 of them) with zero conflicts, leaving only 5 genuinely unresolved (unmapped/ambiguous provider industry label, explicit `ENTITY_IDENTITY_MISMATCH`, never guessed). This rules out options A (genuinely unknown), C (wrong-archetype metric requests — bank/securities keep their own narrow required-identity sets, `sector_financial_taxonomy.SECTOR_INAPPLICABLE_CORPORATE_METRICS` unchanged), and D (incompatible accounting semantics forced together — none is forced; provider facts stay descriptive-only).
5. **Distinguishing over counting.** Rerunning the unchanged `market_wide_current_valuation_input_scaleout.build_current_valuation_artifact` with the wider fundamental artifact substituted for the narrow one — holding price/share-authority (the already-recovered 2026-08-27 share artifact)/official-universe/P3E inputs identical — leaves every `metric_research_usable_counts` and `metric_ready_counts` value unchanged (market_cap 888, P/E 9, P/B 10, P/S 9, EV 9, EV/Sales 9, EV/EBITDA 0; `READY`/`VALUE` stay 0/1,507). The recovery's value is entirely in `first_blocker_counts` honesty: `FINANCIAL_ENTITY_IDENTITY_MISMATCH` 2,226→18 (a mislabeling artifact of the narrow cohort, now corrected) and `FINANCIAL_FACT_MISSING` 2,318→4,137 (the same underlying gap, now attributed to its real cause). No provider-tier fact is promoted to an absolute/exact value anywhere; `PROVIDER_RESEARCH` issuers remain descriptive-only by policy.
6. **Phase-1 identity inventory uses only existing canonical names.** `REQUIRED_IDENTITIES_BY_ENTITY` reuses the exact identity names already defined by `market_wide_current_valuation_input_scaleout.EARNINGS_IDENTITY_BY_ENTITY`/`EQUITY_IDENTITY_BY_ENTITY` (bank: `net_profit_parent`/`total_equity`; securities: `profit_after_tax_parent`/`total_equity`) plus the P3-B core metrics and the three retained EBITDA components (`profit_before_tax`, `interest_expense`, `depreciation_and_amortization`) for corporate. Insurance and finance_company retain zero defined identity requirement — that gap already exists in the current valuation contract and is not invented or filled here. One narrow, documented naming correspondence is applied (`cash_and_cash_equivalents` in the canonical fact store vs. `cash_and_equivalents` in the official evidence panel's own fact rows — the same balance-sheet line, two pre-existing spellings), not a new alias invented for coverage. Residual (expected vs. actually-classified cells) is 0 over all 12,914 required cells for the full 1,507-name universe.
7. **`PROVIDER_EXACT_RESEARCH_USABLE` stays empty by policy, not by oversight.** No provider-tier fact reaches that tier anywhere in the inventory, because statement scope/currency/scale remain `UNKNOWN_FAIL_CLOSED` for every provider observation market-wide — the same discipline `market_wide_current_fundamental_research.py`'s own module docstring already states. `PERIOD_MISMATCH`/`SCOPE_MISMATCH` are not forced into the single-cell inventory (a different granularity — cross-period trend comparability, not single-fact presence); they are reported separately via `trend_comparison_blocker_observations`, sourced from the existing `_pair_basis_eligibility` blocked-reason vocabulary with zero new logic.
8. **AI handoff is an isolated projection, not a rebuild.** New `ai_handoff_financial_fact_projection` is a pure function with no I/O, tested against all five required distinctions (official-qualified / exact-research-usable / descriptive-provider-only / missing / entity-not-applicable). No frozen 26/8 AI artifact is touched or regenerated.
9. **No promotion, no acquisition.** Zero network calls anywhere in the new module (verified by test); the official-qualified issuer count is unchanged at 13 throughout; no VALUE eligibility is created (`value_strategy_readiness.eligible` stays 0); no ticker-literal branch exists in the new code (verified by test). `financial_authority_tiers.BLOCKED` (confirmed zero retained source) rises 3→159 — a genuinely smaller, more honest ceiling than the prior `UNAVAILABLE` (984, meaning simply "never examined").

## 2026-08-27 - AI research handoff scope and routing V1

`AI_RESEARCH_HANDOFF_SCOPE_AND_ROUTING_V1 = COMPLETE_LOCALLY / AI_HANDOFF_READY` (`push = NO`).

Decisions:

1. **Same path.** Harden `ai_research_session_delivery` / `current_daily_decision_research_product` / Daily Producer delivery. Do not open a new research, ranking, or recommendation engine.
2. **Routing defect, not market data.** The external-AI test that returned AAA/AAM/AAN/ABB/AFX/AMP sampled the alphabetical front of the useful-card / NDJSON universe. Canonical JSON `sort_keys` and `sorted(universe)` make that order deterministic for identity, not a review queue. Keep NDJSON alphabetically deterministic and mark it `FULL_UNIVERSE_LOOKUP_ONLY`.
3. **Primary file.** `ai_research_session_bundle.json` is the only normal human-review upload. Manifest/session bundle/canonical post-close handoff carry `recommended_ai_inputs` (`normal_human_review` vs `arbitrary_ticker_lookup`). Do not delete the NDJSON companion.
4. **Analysis scope.** Primary bundle `analysis_scope` lists owner-focus, broader watchlist, mandatory coverage count, deterministic discovery cohorts, high-priority review, full-universe companion role, and `no_alphabetical_sampling=true`. Review order is `OWNER_FOCUS_REVIEW_REQUIRED_BEFORE_MARKET_DISCOVERY`. Presentation/analysis scope only; no investment authority.
5. **Owner-focus config.** Portable `config/owner_research_focus.json`: SSI, HPG, PAN, EVF, VNM, FPT, PVD, NVL, POW, PNJ. Broader WATCHLIST keeps QNS. `is_portfolio_holdings=false`. Absent owner-focus tickers emit an explicit missing card.
6. **Extractor.** New `python tools/extract_ai_research_tickers.py --session YYYY-MM-DD --tickers ...` resolves the unique Daily Producer run (or requires `--run-identity`). No latest-file navigation, no network, no recomputation. Keep `extract_ai_ticker_context.py` for an already-held NDJSON file.
7. **Semantics.** `entry_action` stays the existing tactical enum. Bundle/brief/cards state `entry_action_is_research_label_not_execution_instruction=true` and `is_actionable=false`. BUY_ON_CONFIRMATION / EARLY_ENTRY / ACCUMULATE_IN_BASE are not recommendations.
8. **Frozen 26/8.** No data regeneration, no DNSE, no Dashboard publish. Retained 26/8 primary bundle already contains all 10 owner-focus names; bounded HPG/PAN/SSI extraction does not return AAA/AAM.
9. **Authority unchanged.** `authority_effect = NONE`.

Validation: focused delivery/product/extractor/Daily Producer/canonical-post-close tests; retained 26/8 hash self-verify + extractor; `py_compile`; `git diff --check`. Zero network.

## 2026-08-27 - Market-wide current valuation session-native scale-out V1

`MARKET_WIDE_CURRENT_VALUATION_SESSION_NATIVE_SCALEOUT_V1 = OUTCOME_C_CURRENT_RETAINED_EVIDENCE_CEILING_ESTABLISHED` (`push = NO`).

Decisions:

1. **Same lanes.** Continue `market_wide_current_valuation/v1`, P3-F2/P3-F6 share proxy, and official-qualified fundamentals. No new valuation architecture.
2. **26/8 Daily Producer was already session-native.** Registered valuation `market_wide_current_valuation:cb333137…` binds P3F9B `p3f9_exact_session_snapshot:c25bc8ae…`. Isolated retained replay reproduces the same metric counts. Do not rewrite that frozen 26/8 Daily Producer artifact.
3. **Exact-session close only.** `_price_input` now requires `observation.session == snapshot.resolved_completed_session`. A prior-session lookback bar cannot substitute. Derive `--price` is required; the 2026-08-21 default is removed; `--expected-session` fail-closes mismatch. Level-2 passes both.
4. **Ceiling, not expansion.** Research-usable multiples still need official-qualified financial identities. Provider trends remain descriptive. Issued shares remain `ISSUED_SHARES` / not CSO. Authoritative READY stays 0. VALUE stays 0/1,507.
5. **AI compact pass-through.** Full-universe NDJSON now retains per-metric status/labels so research-proxy availability is distinct from authoritative unavailability. It does not say cheap/expensive. Frozen 26/8 NDJSON is not rebuilt.
6. **Authority unchanged.** `authority_effect = NONE`. Frozen 21/8/24 valuation identities unchanged.

Validation: focused valuation/AI/packet/Level-2/share tests; isolated 26/8 rematerialization vs Daily Producer counts; `py_compile`; `git diff --check`. Zero network.

## 2026-08-27 - Prospective research cohort first-future attribution V1

`PROSPECTIVE_RESEARCH_COHORT_FIRST_FUTURE_ATTRIBUTION_V1 = COMPLETE_LOCALLY / FIRST_STRICTLY_LATER_SESSION_MATERIALIZED` (`push = NO`).

Decisions:

1. **Same lane.** Sibling contract `prospective_research_learning/cohort_future_attribution/v1` inside `PROSPECTIVE_RESEARCH_COHORT_COLLECTION_SCALEOUT_V1`. Not a new learning engine, score, backtest, or ranking surface. Historical `first_real_observation()` remains the 523-member 2026-08-20 contract and is not reused or rewritten for the 25/8 cohort.
2. **Frozen T admission.** Attribution denominator is exactly the immutable 2026-08-25 snapshot `prospective_research_cohort_snapshot:4af5724516b386a3eda67515c322f01856eb9cb96a30287d3fa2a805f506bfc3` (95; 17/14/64). 26/8 triage/tactical state is optional `future_descriptive_state` only and never changes membership.
3. **Strictly later exact-session prices.** T close from retained 2026-08-25 P3F9B `p3f9_exact_session_snapshot:ce30d85d132db0cebfa85d1f7a2b0c8f3258ba9da39d5b093ea88cd5fc5c8ab7`. Future close from the governed canonical 26/8 attempt `p3f9_exact_session_snapshot:c25bc8aea24e1490e2d3b7f8957c3d861456599ca697674a1f4f61207dd8415a`. Registry-selected attempt root wins; disagreeing extra 26/8 copies fail closed. No prior-session, next-available, intraday, or missing-as-zero substitution.
4. **Descriptive arithmetic only.** Same retained representation (`DNSE_PROVIDER_NATIVE_RAW` / identity transform / current-descriptive adjusted-retrospective). Label `PROSPECTIVE_OBSERVED_CLOSE_TO_CLOSE_DESCRIPTIVE`. Zero/invalid T close and representation mismatch stay explicit rows. `RAW_AS_TRADED` not promoted. No costs, dividends, or invented corporate-action adjustments.
5. **One horizon.** 2026-08-25 → 2026-08-26 is the first later completed session. Multi-horizon statistics are not emitted. Later sessions can materialize additional artifacts without rewriting the frozen T snapshot.
6. **Authority unchanged.** `authority_effect = NONE`. `PROSPECTIVE_DESCRIPTIVE_ATTRIBUTION_ONLY`; not PIT backtest, predictive, calibrated, recommendation, sizing, or execution.

Validation: 21 focused tests plus existing prospective-collection/learning/first-real-attribution tests; real 95-member materialization (85 observed / 10 `FUTURE_SESSION_MISSING`); identical replay no-op; `py_compile`; `git diff --check`. Zero network.

## 2026-08-27 - ADTV20 exact-reconciled trailing-window recovery V1

`ADTV20_EXACT_RECONCILED_TRAILING_WINDOW_RECOVERY_V1 = OUTCOME_C_CURRENT_SOURCE_CEILING_ESTABLISHED` (`push = NO`).

Decisions:

1. **Same lane.** This is evidence recovery inside `ADTV20_WINDOW_INTEGRITY_AND_CONFLICT_QUALIFICATION_V1` / `HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY_V1`. No new architecture, provider, or daily-pipeline blocker.
2. **Expected calendar unchanged.** Trailing 20 remains the last 20 sessions of the retained 40-session DNSE Trades corpus: `2026-07-15` through `2026-08-11`. Older 21st+ rows still cannot substitute.
3. **Session-first hole.** Inventory residual 0 over 1,507 × 20 = 30,140 cells. FHSC is missing for every official ticker on `2026-08-06` (1,507 cells). DNSE Trades for that session exist. Six HOSE names are 19/20 with that single FHSC_MISSING cell as the sole blocker (`AAA`, `BID`, `BWE`, `CTG`, `DPM`, `MZG`).
4. **Bounded acquisition of that cohort only.** Approved FHSC route `/market/stocks/{symbol}/trading/history` (`SUPPLEMENTAL_BOUNDED`). Budget 6, one GET each, no sleep/retry. 6/6 HTTP 200. Live payloads still omit `2026-08-06` (they do include later dates such as `2026-08-25`). 0 new `QUALIFIED_G1_EXACT` cells.
5. **Ceiling.** ADTV20 READY cannot reach 20/20 on this calendar until an already-qualified independent matched-value field emits `2026-08-06` and exact-reconciles to DNSE G1. Do not drop that DNSE session from the expected window. Do not coerce G1+G4. Filling the other 185 HOSE names that lack any FHSC file cannot create READY while this hole remains.
6. **Authority unchanged.** `authority_effect = NONE`. `ADV20_MATCHED_VOLUME` not emitted. `QUALIFIED_LIQUIDITY_INPUTS` and `POSITION_SIZING_IS_SAFE` stay false.

Validation: trailing-20 inventory residual 0; 19/20 vs 20/20; no older-session substitution; G1 formula/G4 exclusion; budget and 429 tests; live 6-request batch; `py_compile`; `git diff --check`. No daily-orchestration or Dashboard change.

## 2026-08-27 - Canonical daily one-command operational cutover V1

`CANONICAL_DAILY_ONE_COMMAND_OPERATIONAL_CUTOVER_V1 = COMPLETE_LOCALLY / DAILY_ONE_COMMAND_READY` (`push = NO`).

Decisions:

1. **Two-phase gate.** Phase A `ATTEMPT_ELIGIBLE` answers only whether bounded post-close acquisition may be attempted (safety floor, non-future session, DNSE working-date identity, no contradictory session evidence, route available). It does not prove market close, completed session, or exact-session data. Phase B `READY` remains `EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR` and is evaluated only against the actual retained response after exactly one acquisition attempt. Time alone never produces Phase B. M1's retained exact-session completion rule is unchanged; only its pre-acquisition READY-before-collect interpretation is corrected. 18:00 Asia/Ho_Chi_Minh remains a safety floor, not market-completion authority.
2. **Single market-wide acquisition owner.** `tools/collect_market_evidence.py` emits `capability_first_eod_collector/v1` packets (default cohort, `max_requests=50`) that cannot satisfy `assert_post_close_eligible` (`p3f9_exact_session_mva_snapshot/v2`, `FULL_CANONICAL_CANDIDATE_SET`). Daily Producer, runtime release, and trusted subset consume that canonical snapshot. The daily command therefore owns acquisition only through `canonical_post_close_pipeline.acquire_and_materialize` (P3F9B). Capability-first EOD stays an independent lower-level capability and is not invoked on this path.
3. **Same-session runtime + trusted subset before publication.** `canonical_dashboard_runtime_release` then `canonical_trusted_subset_release` must resolve to the same session as Daily Producer and `--expected-session`. Existing atomic/rollback semantics are reused. Stale prior-session artifacts fail closed.
4. **Publication delegation.** After local/session gates, call `tools/release_orchestrator.py all --live --expected-session <session> --complete-publication`. `governed_publication_completion.py` remains the remote publication authority. Do not reimplement CI/Pages in `daily_analysis_pipeline.py`.
5. **Fail at the exact stage.** Publication failure retains recoverable local state. GitHub timeout is not a data-integrity failure.
6. **No second orchestrator, no scheduler install.** One foreground bounded invocation. `authority_effect = NONE`.

Validation: two-phase gate tests; daily-operation tests (no acquisition before floor, Phase A vs Phase B, one P3F9B owner, producer/runtime/trusted/publication fail-closed order, idempotent replay, tamper, isolated 26/8 retained replay to PUBLISHED with `allow_dispatch=False`); existing M0/M1/publication tests; `py_compile`; `git diff --check`. No Dashboard source change. No live market-wide DNSE request.

## 2026-08-27 - Governed publication one-command completion V1

`GOVERNED_PUBLICATION_ONE_COMMAND_COMPLETION_V1 = COMPLETE_LOCALLY / ONE_COMMAND_PUBLICATION_READY` (`push = NO`).

Decisions:

1. **Same orchestrator.** `--complete-publication` is an opt-in live `all`-group stage. Dry-run and ordinary `--live` stay `GITHUB_SOURCE_UPDATED` and do not wait on GitHub Actions.
2. **Reuse before dispatch.** Exact-SHA completed Dashboard CI SUCCESS is reused. In-progress exact-SHA CI is watched via `gh run watch --exit-status`. Otherwise at most one `dashboard-ci.yml --ref main` dispatch, which must resolve back to the release SHA.
3. **Pages.** Automatic `workflow_run` success is reused only when logs prove `PUBLIC_BYTE_IDENTITY_PASS` for the expected session and exact source SHA. Otherwise one manual `deploy-pages.yml` fallback with `source_sha` and `validated_ci_run_id`. The Dashboard workflow still independently verifies that proof.
4. **PUBLISHED requires public-byte proof.** Workflow SUCCESS without `PUBLIC_BYTE_IDENTITY_PASS` is `BLOCKED_PUBLIC_BYTE_PROOF`.
5. **Race.** New-publication CI dispatch requires `HEAD == origin/main == RELEASE_SOURCE_SHA`. Recovery of a previously validated SHA may use current-main lineage `AHEAD` (workflow-only successor) only with exact-SHA CI proof, matching the 26/8 `534e497` / `691b63d` contract.
6. **No rollback of git history** after a successful Dashboard push if remote completion fails. Retain the recoverable SHA. No `git reset --hard`, force-push, or `git clean`.
7. **Authority unchanged.** `authority_effect = NONE`.

Validation: mocked `gh` tests (reuse, wrong SHA, watch, single dispatch, CI failure before Pages, public-byte required, timeout, idempotence, race, recovery); orchestrator backward-compatibility tests; `py_compile`; `git diff --check`; read-only live reuse of the 26/8 chain with `allow_dispatch=False` (zero workflow dispatch). No Dashboard source change.

## 2026-08-26 - Capability-First EOD 18:00 Operational Scheduling V1

`CAPABILITY_FIRST_EOD_1800_OPERATIONAL_SCHEDULING_V1 = COMPLETE_LOCALLY / SCHEDULER_READY` (`push = NO`).

Decisions:

1. **Provider/session evidence is primary.** Clock time is not proof of a completed VN market session. The gate never claims `PROVIDER_CONFIRMED_COMPLETED`.
2. **DNSE `working_dates` semantic ceiling.** The retained `/market/working-dates` contract is a forward calendar window. It proves working-date identity and prior/next dates only inside the observed window. It does not expose a documented market-closed/session-completed flag and has no historical coverage. Opaque extra fields are not interpreted as completion.
3. **18:00 Asia/Ho_Chi_Minh is a safety floor.** Same-day collection before the floor fails closed (`TOO_EARLY`) before the collector runs. After the floor, time alone never returns `READY`.
4. **READY semantic is `EXACT_SESSION_OBSERVED_AFTER_SAFETY_FLOOR`.** That requires working-date identity (or retained historical exact-session evidence when the forward window does not cover the date) plus sufficient retained exact-session observations acquired at or after the floor for the intended session.
5. **One-shot foreground command only.** `python tools/run_capability_first_eod_operation.py` reuses the existing collector and `tools/materialize_daily_market_research.py`. No OS scheduler, cron, daemon, poll, or sleep. Portable contract: `config/capability_first_eod_operation.json`. `SCHEDULER_READY=YES`.
6. **Authority unchanged.** `authority_effect = NONE`. RAW_AS_TRADED not promoted; PIT blocked; ADTV20/sizing not promoted; strict valuation remains bounded; no probability/target/ranking/recommendation authority.

Validation: focused gate and one-command tests (too-early, time-alone, READY, mismatch, future, weekend/holiday, omitted resolution, stale packet, provider unavailable, successful fixture chain, idempotent replay, tamper, collector/materializer failure, no network, no sleep/poll); `py_compile`; `git diff --check`; isolated 2026-08-26 replay against retained P3F9B exact-session evidence. No dashboard-runtime mutation. No Dashboard publish/deploy.

M0 terminal-state sync in the same commit: `CANONICAL_POST_CLOSE_ONE_COMMAND_PIPELINE_V1 = PUBLISHED / CLOSED` with deployed content source `534e4971edf2b9be62467ce89758b6625544558d`, Dashboard CI `32986483019` SUCCESS, Deploy Pages `32986911616` SUCCESS, public session `2026-08-26` `PUBLIC_BYTE_IDENTITY_PASS`. Dashboard `main` later includes workflow-only fallback `691b63dedec8625bfab7f6b126d8928a2184abf4`, which is not the deployed 26/8 content source.

## 2026-08-26 - Public session companion publication layer V1

`CANONICAL_POST_CLOSE_ONE_COMMAND_PIPELINE_V1` publication gap: missing current-session companions before release-smoke (`push = NO`).

Decisions:

1. **Producer publication layer, not a new orchestrator.** `dashboard_session_companions.py` is a pure compute + live apply module. Publication authority remains `release_orchestrator.py all` → `publish_release` → frontend → `publish_dashboard`.
2. **Retained 2026-08-26 evidence only.** Companions are computed from the canonical handoff, unique Daily Producer run, and frozen registry sources. 2026-08-25 Dashboard files are schema/presentation references and are never copied or relabelled.
3. **Write before release-smoke.** Dry-run plans both paths with zero mutation. Live writes the exact computed bytes after asset versioning and before `tests/release-smoke.test.js`.
4. **Exact whitelist and managed-path rollback.** Only `data/session_<YYYY_MM_DD>_manifest.json` and `report-<YYYY-MM-DD>.html` are added. On later-gate failure, newly created companions are unlinked and preexisting companion bytes are restored; unrelated tracked/untracked files are preserved. No `git clean` or `git reset --hard`.

Validation: focused companion tests (determinism, lineage, dry-run, live-before-smoke, whitelist, rollback); temp Dashboard `release_orchestrator all --live` with trusted subset / frontend / release-smoke / trusted verification; no real Dashboard or runtime mutation; no DNSE.

## 2026-08-26 - Canonical trusted-subset financial-evidence bridge V1

`CANONICAL_POST_CLOSE_ONE_COMMAND_PIPELINE_V1` trusted-subset gap: Outcome B, sidecar builder reused (Outcome A for taxonomy records only).

Decisions:

1. **Do not relabel the 2026-08-25 VCI sidecar.** `session_identity` is packaging excluded from `records_fingerprint`. A new market session rebuilds the sidecar from retained `data_bctc` payloads with a new envelope.
2. **Do not route 2026-08-26 through `export_ai_bundle.py`.** That exporter still requires same-session `vn_stock.db` OHLCV, `ta_signals.csv`, and `live_universe_status=live`. Canonical runtime has none of those on-session; re-running those generators is out of scope.
3. **Official citations are insufficient for taxonomy.** They carry canonical metrics, not Circular template `item_id` vocabularies. Taxonomy stays generated_evidence over retained statement payloads; source remains VCI; no official promotion.
4. **Consumer contract unchanged.** `verify_exact_session_bundle` still requires the four declared artifacts. Sidecar-optional `present:false` exists in export, but `publish_release.py` still requires the allowlist of four. No Consumer edit.
5. **Temp-only in this job.** Real `dashboard-runtime` is not written here. Owner runtime materialization is a separate authorized command.

Validation: focused adapter tests (lookahead, relabel, missing taxonomy, hash mismatch, session mismatch, Consumer, no network imports); retained 2026-08-26 canonical temp replay; `publish_release.py` dry-run; `release_orchestrator.py all` dry-run `PUBLISH_READY=YES`; existing canonical runtime adapter tests unchanged; `py_compile`; `git diff --check`.

## 2026-08-26 - P0 Daily Producer Triage And Session Governance Recovery V1

`P0_DAILY_PRODUCER_TRIAGE_AND_SESSION_GOVERNANCE_RECOVERY_V1 = DAILY_PRODUCER_TRIAGE_AND_SESSION_RECOVERY_PASS`.

The missing `full_universe_entry_candidate_triage/v1` generator is recovered from the governed 2026-08-24 post-close artifact (byte-identical replay of identity `e8488d55…`), its explicit `cohort_definitions`, and existing consumer contracts. Canonical Daily Producer for 2026-08-25 completes on registered exact-session inputs.

Decisions:

1. **Recover, do not invent.** Entry-relevant states remain `BASE_BUILDING`, `BREAKOUT_READY`, and `EARLY_REVERSAL_CANDIDATE`. High-priority review is the existing evidence-gated rule (eligible liquidity; market momentum not LOWER_QUARTILE; sector not LOWER_QUARTILE when available; no explicit tactical/fundamental conflict). Missing fundamental context is not an eligibility condition.
2. **No prior-day triage reuse.** 2026-08-25 triage is generated from 2026-08-25 descriptive, screening, and tactical inputs plus retained fundamental overlay. The 2026-08-21/named-20260824 file is schema/behavior reference only.
3. **Register then produce.** Session 2026-08-25 is entered in `config/daily_research_session_input_registry.json` with frozen identities only after coherence passed. Canonical Daily Producer is the governed path; Level-2 remains fallback.
4. **Do not conflate contracts.** Five names with fewer than 20 lifetime bars stay component-local technical gaps. They do not block the session. ADTV20, PIT, and current-share authority remain separate.
5. **Do not manufacture the next session.** 2026-08-26 close data is not created before that market session completes. Omitted `--session` on the Level-2 runner resolves latest completed working-date; explicit `--session YYYY-MM-DD` remains.

Validation: 2026-08-24 post-close identity replay; focused triage/producer/Level-2 tests; real 2026-08-25 generator run; scenario/strategy/opportunity/packet rebuild; Canonical Daily Producer PASS (`daily_producer_run:b1d7c838…`, coverage 888); `py_compile`; `git diff --check`.

## 2026-08-25 - Current Research Packet Dashboard Shadow Surfacing V1

`CURRENT_RESEARCH_PACKET_DASHBOARD_SHADOW_SURFACING_V1 = CURRENT_RESEARCH_PACKET_DASHBOARD_SHADOW_SURFACING_PASS` (`push = NO`).

The canonical `current_research_decision_packet/v1` already packages current decision context and optional research siblings. This milestone organizes those facts through the existing daily decision research product and the existing opt-in bundle attach. It does not redesign the packet, add a research-context sibling, or promote packet authority.

Decisions:

1. **Reuse the existing product surface.** Extend `current_daily_decision_research_product/v2` and `--include-current-research-decision-packet`. Do not invent a second dashboard architecture or write Consumer/`market-dashboard-main`.
2. **Shadow/opt-in only.** Default product and default bundle bytes stay unchanged. Missing or incorrect packet identity fails closed without altering the default path.
3. **Do not conflate scenario or priority contracts.** Packet scenario is the evidence-bound Bear/Base/Bull family and is never labelled CONSERVATIVE/BASE/SPECULATIVE. Packet `priority_tier` remains `current_opportunity_prioritization/v1` and is not merged with `daily_opportunity_decision_queue`.
4. **Authority labels are required presentation.** `NO_MATERIAL_RISK_ESTABLISHED` is not LOW_RISK; `RESEARCH_USABLE` is not authoritative READY; `ADJUSTED_RETROSPECTIVE` is not RAW_AS_TRADED; retrospective history is not PIT; record date is not ex-date; planned/approved is not executed; scenario axis is not probability; research priority is not entry action; research state is not sizing.
5. **Local absence stays local.** A missing or malformed optional packet component does not make the ticker unusable and does not revise upstream decision state.

Validation: focused product/packet tests; retained market-wide render 1,507/1,507 residual 0 malformed 0; `py_compile`; `git diff --check`. Packet identity `current_research_decision_packet:489e04894b5be6b1a0c8d4c69c41140706d32cf6dcec46b916b1ee7a95afb763`. No push, merge, deploy, default cutover, or authority promotion.

## 2026-08-25 - Current Corporate Event Context V1

`CURRENT_CORPORATE_EVENT_CONTEXT_V1 = CURRENT_CORPORATE_EVENT_CONTEXT_PASS` (`push = NO`).

Existing `current_official_event_context` already retains 4,450 official HNX/HOSE events, and corporate intelligence already maps only the 210 explicit-ex-date current rows plus three issuer/VSDC chains. This milestone adds a current-research sibling over the full retained event set rather than a second event engine or a CI/strategy rewrite.

Decisions:

1. **Reuse retained events.** Official event records keep their identities, taxonomy, and uncollapsed dates. Supplemental HPG executed, VNM executed record-date-only, and VCB planned-not-executed chains are the same CI sources, without re-importing the CI adapter subset.
2. **No inferred dates.** `record_date != ex_date`. Planned/approved is not executed. Announcement is not execution. Missing known_at is `UNKNOWN_NOT_RETAINED`, not as-of. A published/known timestamp after the research as-of is look-ahead and excluded. Previously blocked ex-date cases stay without ex-date.
3. **Statuses are factual.** `CONFIRMED_UPCOMING`, `CONFIRMED_RECENT` (30-day window reused from official event context), `EXECUTED` only with execution evidence, `PLANNED_NOT_EXECUTED`, `TEMPORAL_DETAILS_INCOMPLETE`, `CONFLICTING_EVIDENCE`, `DATA_LIMITED`. No bullish/bearish label.
4. **Dedup is exact.** Merge only across source families when ticker, type, and all of record/ex/execution dates that are present match. Same-source occurrence duplicates and near-date neighbors stay distinct. Conflicting ex-dates for the same record date fail closed.
5. **Downstream unchanged.** Default-off bundle attach. EVENT_DRIVEN still requires CI `PRICE_SHARE_AFFECTING` current official events. `research_priority` and `entry_action` are not modified. Frozen 2026-08-21/24 identities are unchanged.

Validation: focused tests; official event context and CI regressions; `py_compile`; `git diff --check`; retained replay `current_corporate_event_context:214e4a164b8058c572d9487b56d38c5ae5c226c7dae81d540e79a83533ca5934`. No push, merge, deploy, or authority promotion.

## 2026-08-25 - Current Financial Momentum Context V1

`CURRENT_FINANCIAL_MOMENTUM_CONTEXT_V1 = CURRENT_FINANCIAL_MOMENTUM_CONTEXT_PASS` (`push = NO`).

Existing `market_wide_current_fundamental_research` already joins official P3-B metrics, provider-series trends, and `fundamental_trajectory_context` (QoQ revenue/earnings alignment used by `FUNDAMENTAL_IMPROVEMENT`). That envelope is not a comparable-period momentum state, does not consume official FY YoY growth, and does not contrast operational improvement with current-session price momentum. This milestone adds a sibling current-research context rather than a second fundamental evidence lane.

Decisions:

1. **Reuse retained evidence.** Official FY YoY (`revenue_growth_yoy`, `earnings_growth_yoy`, two-period `net_margin`, `operating_cash_flow_growth_yoy`) and already-emitted provider series comparisons. No new facts, no provider-to-official upgrade, no adjacent-period substitution for a missing YoY pair. QoQ may appear only as `PARTIAL` with an explicit `YoY` absence warning.
2. **Keep identities distinct.** Consolidated/standalone, FY versus quarter, and parent versus total earnings fail closed. Bank/securities industrial revenue/margin/OCF are `NOT_APPLICABLE`. Provider `net_income` is not treated as parent-attributable bank/securities earnings.
3. **Transparent states, no score.** `BROAD_IMPROVEMENT`, `EARNINGS_IMPROVING`, `MIXED`, `DETERIORATING`, `LOSS_MAKING_OR_STRESSED`, `INSUFFICIENT_COMPARABLE_DATA`, `NOT_APPLICABLE`. Revenue up with earnings or margin down stays `MIXED`. One missing metric does not globally block a ticker.
4. **Operational versus price is a contrast, not a claim.** Current-session descriptive `momentum_20d` may show financial improvement without price momentum (HPG) or aligned-not-distinguished (SSI). Financial momentum is not price momentum, cheapness, or VALUE.
5. **Downstream unchanged.** Opt-in `export_ai_bundle.py` attach is default-off. `FUNDAMENTAL_IMPROVEMENT` still requires trajectory `BOTH_EXPANDING`. `research_priority` and `entry_action` are not modified. Frozen 2026-08-21/24 identities are unchanged.

Validation: focused tests; fundamental-readiness and strategy regressions; `py_compile`; `git diff --check`; retained replay `current_financial_momentum_context:1100ea5a39ea22747f9cd455f0ca86971046e54c07c99472695a452757b154e1`. No push, merge, deploy, or authority promotion.

## 2026-08-25 - ADTV20 Window Integrity And Conflict Qualification V1

`ADTV20_WINDOW_INTEGRITY_AND_CONFLICT_QUALIFICATION_V1 = MATCHED_VALUE_AUTHORITY_SCOPE_RESTRICTED` (`push = NO`).

The FHSC historical matched-value scale-out claimed 295 `ADTV20_READY` names by counting any 20 exact rows in the 40-session DNSE corpus. That is not the trailing 20 trading sessions. This milestone repairs the window, classifies all 5,447 conflicts from retained evidence, and narrows applicability. It does not acquire, retry HTTP 429, or rewrite the G1 formula.

Decisions:

1. **Session grid is 1,507 × 40 = 60,280 with residual 0.** Evaluated DNSE parquet pairs are 60,273. The prior 7-row discrepancy is seven structurally absent ticker-session parquet pairs (POM/VCI 2026-07-13, HPH/SGR 2026-07-14, OCH 2026-07-15, CT3 2026-07-16, ONE 2026-08-11), not unexplained evaluation. Accounting: 13,196 EXACT + 5,447 CONFLICT + 12,746 NOT_COMPARABLE + 28,884 no FHSC observation + 7 absent = 60,280.
2. **Conflicts are not coerced.** 5,258/5,447 conflicts are exactly FHSC matched volume/value = G1 shares + G4 raw shares. 184 unexplained residuals and 5 G1-only leftovers remain conflicts. The G1-only formula is not replaced by a G1+G4 identity that would fit more rows. Put-through is usually absent (5,297/5,447 have FHSC put-through value 0).
3. **Numerical EXACT is not authority.** 7,818 discriminating vs 5,378 non-discriminating exacts. Non-discriminating exacts are not promoted. HNX/UPCOM discriminating exacts are restricted-scope, not generic ADTV20 inputs. Observation-qualified scope is HOSE discriminating exact only (214 tickers, 6,805 sessions).
4. **`ADTV20_MATCHED_VALUE` is the expected trailing 20 trading sessions** `2026-07-15` through `2026-08-11`. A missing, conflicting, non-discriminating, or restricted session inside that window is not replaced by an older 21st observation. READY requires 20/20 HOSE discriminating exacts. True READY is 0 (was claimed 295); PARTIAL 213; BLOCKED 190; NOT_APPLICABLE 1,104. Missing is not zero. `ADV20_MATCHED_VOLUME` stays not emitted.
5. **Downstream gate unchanged.** ADTV20 is a research input for qualified records only. It is not a safe position size, participation cap, market-impact estimate, slippage model, or executable capacity. `QUALIFIED_LIQUIDITY_INPUTS` and `POSITION_SIZING_IS_SAFE` stay false. Frozen 2026-08-21/24 identities are unchanged.

Validation: session-grid residual 0; conflict taxonomy; trailing-window regressions; exchange applicability; focused tests; `py_compile`; `git diff --check`; frozen identities. No push, merge, deploy, or 429 retry.

## 2026-08-25 - Historical Matched Trading Value Authority V1

`HISTORICAL_MATCHED_TRADING_VALUE_AUTHORITY_V1 = MATCHED_TRADING_VALUE_AUTHORITY_CEILING_ESTABLISHED` (`push = NO`).

The prior G1/FHSC 12-row observation remains the only independently exact matched-value proof. This milestone names the monetary 20-session feature `ADTV20_MATCHED_VALUE`, scales one terminal disposition across the official 1,507-name universe, and does not manufacture a generic value field.

Decisions:

1. **Matched value is G1 only.** Formula `sum(G1.matchPrice * G1.matchQtty) * 10 * 1000` VND. G4 odd-lot and T1/T3/T4/T6 put-through stay retained and excluded. Missing boards are not zero-filled. `grossTradeAmount` and OHLC `v`/`va` are not matched value.
2. **`ADTV20_MATCHED_VALUE` is not ADV.** Trailing 20 actual qualified trading sessions, no calendar imputation, no 17/20 tolerance. Ready count is 0 because each qualified ticker has 3/20 sessions. `ADV20_MATCHED_VOLUME` is not emitted; volume authority is not derived from the value proof.
3. **No generic promotion outside the 12 exact rows.** Market-wide ceiling: 4 observation-qualified tickers, 1,503 official names `UNAVAILABLE_NO_INDEPENDENT_MATCHED_VALUE_ANCHOR`. `QUALIFIED_LIQUIDITY_INPUTS` and `POSITION_SIZING_IS_SAFE` stay false. No participation cap is embedded.
4. **Prospective opt-in only.** `export_ai_bundle.py` may attach the artifact behind a default-off explicit path. Frozen 2026-08-21/24 identities, current-session liquidity, current-share, and valuation/VALUE contracts are unchanged.

Validation: official 1,507 denominator; 12/12 discriminating `EXACT_RECONCILED`; focused tests; `py_compile`; `git diff --check`. No push, merge, deploy, or sizing/PIT/RAW_AS_TRADED promotion.

## 2026-08-25 - Current Common Shares Authority And Scaleout V1

`CURRENT_COMMON_SHARES_AUTHORITY_AND_SCALEOUT_V1 = CURRENT_COMMON_SHARES_AUTHORITY_CEILING_ESTABLISHED` (`push = NO`).

The prior valuation research layer still collapsed HPG’s official executed count into `QUALIFIED_OFFICIAL` without proving coverage through the price session, and it did not emit one explicit current-share terminal disposition per official-universe ticker.

Decisions:

1. **Keep identities separate.** `VCI.overview.issue_share` remains `ISSUED_SHARES` / `NOT_PROMOTED`. HOSE `outStanding` remains exchange outstanding volume. HNX `KLLH`/`KLNY`/`KLĐKGD` remain circulating/listed/registered-trading. Period-end and weighted-average shares never satisfy current common shares. Issued-minus-treasury is not inferred.
2. **Coverage-through-session is the current-common gate.** An official executed resulting count is `QUALIFIED_CURRENT_COMMON_SHARES` only when `valid_from <= session <= coverage_through` and no unresolved share-changing action remains. HPG’s 8,442,964,520 count is `QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT`.
3. **Reconcile later share-changing events without inferring dates.** Planned/upcoming events do not terminate an observation. Dated stock-dividend/bonus events in the observation-to-session gap without execution or resulting shares fail closed as `CORPORATE_ACTION_RECONCILIATION_REQUIRED` (HCC, IPA, NAG). Undated ISS remains `UNVERIFIABLE_FRESHNESS` (SSI, VCB).
4. **No generic authority source was manufactured.** The market-wide ceiling is 0/1,507 authoritative current-common. The existing valuation engine consumes the new artifact prospectively; formulas, VALUE thresholds, RAW_AS_TRADED, PIT, sizing, target-price/DCF, and frozen 2026-08-21/24 identities are unchanged.

Validation: official denominator 1,507 with zero unexplained drift; one terminal disposition per ticker; focused tests; `py_compile`; `git diff --check`. No push, merge, deploy, or authority promotion.

## 2026-08-25 - Market-Wide Current Valuation Research Scale-Out V1

`MARKET_WIDE_CURRENT_VALUATION_RESEARCH_SCALEOUT_V1 = COMPLETE_LOCALLY / CURRENT_RESEARCH_ONLY / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`.

The prior market-wide valuation envelope collapsed every ticker-level share row to `PROVIDER_REPORTED_STALE` and emitted only `BLOCKED`/`NOT_APPLICABLE` on the strict lane. This milestone materializes CURRENT RESEARCH valuation inputs over the official 1,507-name universe and the retained 2026-08-21 price session.

Decisions:

1. **Preserve resolver share tiers.** Statuses are `QUALIFIED_OFFICIAL`, `PROVIDER_REPORTED_CURRENT`, `PROVIDER_REPORTED_LAGGED`, `PROVIDER_REPORTED_STALE`, `PROVIDER_REPORTED_UNVERIFIABLE_FRESHNESS`, and `UNAVAILABLE`. Issued shares are never relabelled common outstanding.
2. **`READY` remains the authoritative gate.** It requires P3-F2 current-common coverage through the price session. Resolver `qualified_official` without that coverage is `RESEARCH_USABLE` only. VALUE still requires any strict `metrics.status==READY` and therefore stays blocked.
3. **`RESEARCH_USABLE` reuses the existing MVA/current-descriptive share contract plus official-qualified financial identities and P3-F formulas.** Provider-research absolute financials stay forbidden. EV/EBITDA stays blocked (`EXACT_EBITDA_COMPARABILITY_NOT_RETAINED`). Banks/securities industrial EV/Sales/EBITDA stay `NOT_APPLICABLE`.
4. **Fitness is per metric.** A missing EV/EBITDA does not globally block a ticker that has research-usable P/E or market cap.
5. **Prospective artifact only.** Default output is `operations-review/market-wide-current-valuation-research-scaleout-v1/`. Frozen 2026-08-21 (`e6d015f2…`) and 2026-08-24 (`b9ca1224…`) valuation identities, and the daily-session registry, are not rewritten. Daily analyst brief may attach coverage opt-in without changing attention priority or `valuation_authority`.

Validation: denominator 1,507 with zero unexplained drift; deterministic replay `market_wide_current_valuation:94d6116f6277cced9988281ea2d0327347079a973a8755128ee2ed726a5315aa`; stale-share and bank/securities EV regressions; VALUE 0 eligible; focused tests; `py_compile`; `git diff --check`. No push, merge, deploy, or authority promotion.

## 2026-08-24 - Market-Wide Historical Research Context V1

`MARKET_WIDE_HISTORICAL_RESEARCH_CONTEXT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`.

Current research already had same-session 20-bar technicals. It did not say where that state sat in the ticker's retained history. This milestone adds one retrospective descriptive contract over already-retained DNSE bars (2026-08-24 P3F9B snapshot plus 132 recovery overrides). It is within-ticker only.

Decisions:

1. **Reuse, do not duplicate, the feature engine.** Rolling volatility, 20-session momentum, MA20, and provider-scoped relative volume are `mva_daily_research_bundle.market_features()` on explicit last-20 observed-session slices. Windows use actual retained trading observations; missing sessions are not imputed.
2. **Preserve price basis.** Retained DNSE history stays `ADJUSTED_RETROSPECTIVE` with the snapshot's `CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED` source label. `RAW_AS_TRADED` remains `NOT_PROMOTED`; PIT remains `BLOCKED`.
3. **52-week is fail-closed.** It requires 252 retained observations. The current corpus has none, so every ticker is `INSUFFICIENT_HISTORY` rather than a calendar 52-week guess from a 45-day or 365-day lookback with fewer than 252 bars.
4. **No PIT membership, no cross-section through time.** Historical percentiles are own-history only. Cross-sectional historical comparison is `BLOCKED` / `HISTORICAL_PIT_MEMBERSHIP_UNAVAILABLE`.
5. **Structural context is not strategy or entry.** `TREND_CONTINUATION` / `MATURE_TREND` / `BASE` / `EARLY_REVERSAL` / `DETERIORATION` are derived from existing MA/momentum/vol primitives. They do not change `entry_state`, `entry_action`, `research_priority`, or strategy eligibility. Optional strategy-lane examples in `pilot_diagnostics` are reference-only.
6. **Producer integration in the same milestone.** `export_ai_bundle.py` gains `--include-market-wide-historical-research-context` (default off, explicit path, fail-closed hash) as a sibling of current descriptive research. No second integration milestone. Governed 2026-08-24 session artifacts and the 2026-08-21 freeze are not regenerated.

Validation: focused unit tests, real retained-data pilot, deterministic replay, short/missing history, no performance fields, no RAW_AS_TRADED/PIT promotion, `py_compile`, `git diff --check`, frozen 2026-08-24/2026-08-21 identities. No push, merge, deploy, or authority promotion.

Artifact: `operations-review/market-wide-historical-research-context-v1-20260824/market_wide_historical_research_context_artifact.json` (`market_wide_historical_research_context:bf25da2fc89f82b168b624fa5bfe4a4d3ec4ff4a6e3aa4f91cd7ae00d2ba1787`).

## 2026-08-24 - Same-Session Technical Coverage Recovery V1

`SAME_SESSION_TECHNICAL_COVERAGE_RECOVERY_V1 = COVERAGE_CEILING_ESTABLISHED`. The 881 same-session technical/tactical count on 2026-08-24 is complete coverage of exact-session observed bars after 132/132 history-only recoveries. Missing official-universe coverage is structurally `SESSION_MISSING` (no target bar), not a leftover materialization hole. Same-session eligibility remains `SHADOW_ONLY` and `is_current_session`; prior-session windows cannot satisfy it. Future snapshot lookback is 365 calendar days, matching recovery, and descriptive build fails closed on exact-session bars without current technicals. No ticker patches, no fabricated no-trade bars, no PIT/RAW_AS_TRADED promotion, and no retrofit of the governed 2026-08-24 session.

## 2026-08-24 - Daily Session Temporal Input Lock Hardening V1

`DAILY_SESSION_TEMPORAL_INPUT_LOCK_HARDENING_V1 = COMPLETE_LOCALLY`. After `bba1afe` closed the concrete 2026-08-21 queue-serving bypass, remaining construction/consumption holes could still attach later `official_universe`/`event_context` through a self-consistent manifest, a direct `build_operation()` dict, or mutation of `sessions[session]` after completion. The existing daily-session registry is now the lock: `registry["sessions"][session]` is the allowlist for operation construction, `completed_sessions[session].frozen_input_identities` rejects post-completion input mutation, and queue resolution additionally requires those registered identities (not merely a self-hashing run manifest). Optional inputs absent from a session stay absent. The governed 2026-08-24 operation and the immutable 2026-08-21 prospective snapshot identity are unchanged. No new registry, ranking, or opportunity semantic.

## 2026-08-23 - Watchlist Tactical Decision Closeout

`WATCHLIST_TACTICAL_DECISION_CLOSEOUT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL`. Owner-authorized
closeout on the same-day classifier below, before its first use against the actual configured
watchlist ahead of the 2026-08-24 market open. Four corrections, all inside
`watchlist_tactical_entry_classifier.py` (Producer) and `build_ticker_context.py`/
`ai_analysis_templates.md` (Consumer, `ai-core-private`); no new architectural lane or worktree.

**1. Entry guidance separated from position-management guidance.** The original `action` field
mixed two concerns: `BUY_ON_CONFIRMATION`/`EARLY_ENTRY`/`ACCUMULATE_IN_BASE`/`WAIT`/`AVOID` answer
"should I enter," but `HOLD_DO_NOT_ADD`/`REDUCE_EXIT` presuppose an existing position this pipeline
has no holdings input to confirm. New `entry_action` (`ENTRY_ACTION_BY_ENTRY_STATE`, a fixed 9→5
lookup) is now the PRIMARY field for "should I enter this ticker": `UPTREND_CONFIRMED` and
`DISTRIBUTION_RISK` now answer `WAIT` (no fresh low-risk entry trigger today, not a chase, and not
an artifact of an assumed position) and `BREAKDOWN_RISK` answers `AVOID` rather than the
position-only `REDUCE_EXIT`. The original `action` (`ACTION_BY_ENTRY_STATE`) is unchanged in value
and remains present as a SECONDARY, position-management-conditional field, now documented as such
everywhere it appears (module docstring, contract doc, Consumer docstrings, AI prompt template) --
never the basis for an entry decision when holdings are unknown.

**2. No full-position-readiness claims; sizing stays NOT_EVALUATED.** `is_full_position_ready` is
now unconditionally `False` and a new `position_sizing_status` unconditionally `"NOT_EVALUATED"`
for every record without exception, replacing the old BREAKOUT_READY-conditional gate (liquidity +
`OFFICIAL_QUALIFIED` fundamentals + non-risk-off market). Position sizing is not implemented
anywhere in this pipeline, so no ticker -- not even a fully-qualified `BREAKOUT_READY` -- may ever
be reported ready for a full-size position. Enforced twice, independently: Producer never computes
anything but the two constants, and Consumer's `watchlist_tactical_entry_classifier_contract()`
fails a record closed to `status="malformed"` if `is_full_position_ready` is ever anything but
`False` or `position_sizing_status` anything but `"NOT_EVALUATED"`, regardless of the bundle.

**3. Fundamentals confirmed never to gate EARLY_ENTRY/ACCUMULATE_IN_BASE.** Audited, not changed:
`entry_state`/`entry_action` derivation never reads `fundamental_tier` anywhere in
`_entry_state_rule()`/`_classify_ticker()`; fundamental tier only ever narrows `horizon` one tier
and lowers `data_quality.confidence`. Real-data proof: PAN (the watchlist's one
`ACCUMULATE_IN_BASE` ticker below) carries `OFFICIAL_QUALIFIED`/`PARTIAL` fundamentals that raised
its confidence to `HIGH` and kept horizon at the base `MULTI_WEEK_SWING` -- it did not gate the
classification, which was already reachable independent of fundamental tier.

**4. EARLY_REVERSAL_CANDIDATE and BASE_BUILDING tightened, both using only already-computed
fields.** `EARLY_REVERSAL_CANDIDATE` (rule `R6`) previously fired on a bare below-MA20,
momentum-turned-positive flip alone. It now additionally requires at least one independent
confirming signal -- market-relative momentum in the upper half of the cohort, sector-relative
momentum in the upper half of its own sector cohort (a new `sector_momentum_bucket` parameter
wired into `_entry_state_rule()`, from the already-computed `sector_relative_comparison` this
module already read for evidence text), or today's return positive together with elevated
provider-relative volume. An unconfirmed flip now falls to new rule `R6B` and reports
`SIDEWAYS_NEUTRAL` instead. `BASE_BUILDING` (rule `R7`) previously fired on low volatility plus no
elevated volume alone, regardless of how far or how persistently the ticker had declined. It now
additionally requires no bottom-quartile relative momentum and no confirmed-down session today, so
a persistent weak/downtrend that merely happens to be quiet no longer qualifies as a base.
`EARLY_ENTRY` remains reachable without a confirmed uptrend (preserved unchanged, per the original
milestone's explicit instruction) -- the correction is strictly a tightening of the evidence bar,
not a reversion to confirmation-only behavior.

**Real before/after, full retained 2026-08-21 session (1,683 candidates, 956 classified,
zero network calls -- offline regeneration from the same three already-retained source
artifacts):** `BASE_BUILDING` 77 -> 20, `DOWNTREND` 109 -> 140, `SELLING_PRESSURE_EASING`
139 -> 165 (the 57 tickers leaving `BASE_BUILDING` land exactly here: 31 in `DOWNTREND`, 26 in
`SELLING_PRESSURE_EASING`, confirmed by exact arithmetic, not estimated). `EARLY_REVERSAL_CANDIDATE`
(30), `SIDEWAYS_NEUTRAL` (274), `UPTREND_CONFIRMED` (177), `BREAKDOWN_RISK` (44), `BREAKOUT_READY`
(40), and `DISTRIBUTION_RISK` (66) are all byte-unchanged -- rules R1-R5/R8/R9 were not touched, and
real data shows every previously-confirmed `EARLY_REVERSAL_CANDIDATE` already carried a qualifying
confirming signal (R6B never actually fires on this session's data, though it is real, tested, and
reachable). New entry_action distribution: `EARLY_ENTRY` 30, `ACCUMULATE_IN_BASE` 20,
`BUY_ON_CONFIRMATION` 40, `WAIT` 1409, `AVOID` 184. `full_position_ready_count` stays 0 (previously
an "honest zero" for BREAKOUT_READY-specific reasons; now 0 unconditionally for every ticker and
every state). New artifact:
`operations-review/watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json`
(`watchlist_tactical_entry_classifier:bcc1e855f069e13b80d3e4b5b9c523a489356426fc32891a12c592265e7bc885`,
regenerated in place over the prior `4797deeb...` checkpoint).

**Frozen pre-open artifact for 2026-08-24.** Extracted the actual configured 11-ticker production
cohort (`export_ai_bundle.py`'s `DEFAULT_TICKERS`: POW, SSI, HPG, EVF, PAN, PNJ, FPT, QNS, VNM,
PVD, NVL) from the regenerated artifact above -- all 11 present and classified, none missing or
insufficient-data. Result: 1 `ACCUMULATE_IN_BASE` (PAN, `BASE_BUILDING`), 10 `WAIT` (POW/HPG/EVF/
QNS/PVD `SIDEWAYS_NEUTRAL`; SSI/PNJ/FPT `DISTRIBUTION_RISK`; VNM/NVL `UPTREND_CONFIRMED`), 0
`EARLY_ENTRY`, 0 `BUY_ON_CONFIRMATION`, 0 `AVOID` -- an honest, unglamorous real reading, not
adjusted for variety. Artifact:
`operations-review/watchlist-tactical-entry-decision-preopen-20260824/watchlist_tactical_entry_decision_preopen_20260824.json`
(local-only, gitignored like all `operations-review/` content, same as its source).

**Tests.** Producer: 42 tests in the two existing classifier test files (was 38; +4, including two
new hand-computed-cohort tests -- independent of the main 9-ticker fixture -- proving R6/R7 are
genuinely tighter: an unconfirmed momentum flip now resolves `SIDEWAYS_NEUTRAL` via `R6B`, and a
deep bottom-quartile decline with low volatility now resolves `DOWNTREND` via `R9`, not
`BASE_BUILDING`). Consumer: 38 tests across the three existing classifier test files (was 31; +7,
including a stronger "fails closed for BREAKOUT_READY too" test and two new full-real-universe
proofs added to the frozen-time E2E suite). All pass, including the real cross-repo frozen-time E2E
over the actual 11-ticker production cohort against the regenerated artifact. A targeted 356-test
Producer sweep (`-k "watchlist_tactical or market_wide_current or screening or export_ai_bundle"`)
reproduces the same 6 pre-existing failures by name (stale VCB/VNM/HPG evidence-state and
share-basis fixtures, unrelated to this classifier); a full 736-test Consumer sweep reproduces the
same 10 pre-existing failures by name (metadata-registry-shadow/phase7-8-9-11 batch/catalog
fixtures) -- neither is a regression. `py_compile` clean in both repos.

**Negative boundaries, unchanged.** No new technical indicator (the one new rule input,
`sector_momentum_bucket`, is an already-computed value newly wired into the rule function, not a
new computation). No ranking, score, probability, target price, valuation, RAW_AS_TRADED/PIT claim,
backtest, or new data acquisition anywhere. No push, merge, deploy, or production write in either
repository; local checkpoint commits only.

## 2026-08-23 - Watchlist Tactical Entry-State Classifier

`WATCHLIST_TACTICAL_ENTRY_DECISION_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. Owner-authorized bounded milestone: turn the already-computed current market-wide descriptive/screening/fundamental research into a deterministic tactical entry-state classifier, explicitly scoped to reuse existing lanes rather than build a new feature store or ranking engine. New `watchlist_tactical_entry_classifier.py` joins `market_wide_current_descriptive_research` (technical features, trend state, breadth/regime, liquidity), `current_market_screening_opportunity_comparison_foundation` (market/sector-relative momentum and volume percentile context), and `market_wide_current_fundamental_research` (official/provider fundamental tier), wired through `export_ai_bundle.py` into the Consumer using the identical opt-in/hash-verified attach convention every `market_wide_current_*` sibling already established.

**Taxonomy design.** `ticker_structure_state` (five values) is the ticker's own raw posture from `trend_state` and `momentum_20d`'s sign plus a close-vs-MA20 proximity test, reusing `price_structure_breakout_context.NEAR` (2%) rather than inventing a new threshold. `entry_state` (the required nine-state taxonomy) is a single ordered, first-match-wins decision table layered on top, additionally folding in market-relative momentum quartile (from screening's `momentum_bucket`), today's session return, provider-relative-volume confirmation (the `RELATIVE_VOLUME_ABOVE_COHORT_MEDIAN` screen flag), and a cross-sectional volatility regime (a ticker's `volatility_20d` compared only to the market's own contemporaneous median, never a historical compression claim). The table was exhaustively verified gapless and unambiguous across all 1,080 combinatorial input states before being run against real data.

**Action/full-position gating, the two clauses this milestone was most explicit about.** `action` is a fixed nine-to-seven lookup from `entry_state`. `EARLY_ENTRY` maps only from `EARLY_REVERSAL_CANDIDATE` (momentum has turned positive before price reclaims the 20-day moving average) -- deliberately not requiring `UPTREND_CONFIRMED` first, matching the milestone's explicit instruction that a confirmed uptrend must never gate `EARLY_ENTRY`. `is_full_position_ready` is `False` by construction for every `entry_state` except `BREAKOUT_READY`, and even there only with descriptive-liquidity eligibility, `OFFICIAL_QUALIFIED` fundamental readiness, and a market backdrop that is not broadly risk-off -- so `EARLY_ENTRY`/`ACCUMULATE_IN_BASE` can never reach `True`. This is enforced twice, independently: once in the Producer's `_is_full_position_ready()` gate, and again in the Consumer's `watchlist_tactical_entry_classifier_contract()`, which fails a record closed if `EARLY_ENTRY`/`ACCUMULATE_IN_BASE` and `is_full_position_ready=true` are ever both present, regardless of what the Producer bundle claims -- structural enforcement, not merely a prose promise. `EARLY_REVERSAL_CANDIDATE`/`BASE_BUILDING` use early/base language exclusively; no state is ever described as a confirmed bottom or top, and both carry a stricter, faster `invalidation` than a confirmed-trend state's.

**Fundamental-cohort boundary.** The fundamental-research lane's 523-member P3-F10/P3-F13 cohort is a structurally different universe from the descriptive/screening lane's 1,510-denominator cohort (different acquisition lineage, different "current" session concept). Rather than forcing a session/denominator cross-check that would fail closed for the ~1,160 tickers outside the fundamental cohort, this module verifies each of the three source artifacts' own content identity independently and joins by ticker only, reporting absence as an explicit `fundamental_context.status = "NOT_IN_FUNDAMENTAL_COHORT"` -- distinct from an in-cohort `BLOCKED` tier. Per the milestone's own instruction, missing/blocked fundamental authority narrows `horizon` (one tier toward `NEXT_SESSION_WATCH`) and lowers `data_quality.confidence`, but never forces `WAIT` by itself when tactical evidence is otherwise sufficient.

**Real-data result, not just synthetic.** Run against the actual retained 2026-08-21-session artifacts: 956/1,683 classified (exactly the descriptive lane's own same-session technical coverage count -- an independent cross-check the two lanes agree), all nine states populated with real counts, `market_state=MIXED_NO_CLEAR_MARKET_REGIME`, and `full_position_ready_count=0` -- an honest zero, since none of today's 40 `BREAKOUT_READY` tickers happen to be among the 13 `OFFICIAL_QUALIFIED` fundamental-tier issuers. No target price, probability, expected-return figure, or position-size/share-count field exists anywhere in the artifact, verified by an explicit key-absence test over the complete real 1,683-record output, not just the synthetic fixtures.

**Negative boundaries.** No new technical indicator, ranking engine, feature store, or evidence acquisition. No RAW_AS_TRADED, PIT, corporate-action/ex-date, backtesting, active-universe promotion, or portfolio-sizing-formula authority (`portfolio_weights_or_position_sizes` is explicitly labelled `SIZING_FORMULA_NOT_YET_IMPLEMENTED`, reserved for a future milestone). No protected valuation/Daily Analyst Brief WIP file was read or touched (the pre-existing untracked `market_wide_current_valuation_input_scaleout.py`/`tools/build_daily_analyst_brief.py` and their tests). 38 new Producer tests and 31 new Consumer tests pass; a targeted 244-test Producer sweep and a full 730-test Consumer sweep reproduce the same 6 and 10 pre-existing failures (respectively) confirmed byte-identical against each unmodified pre-milestone checkout via `git stash` -- neither is a regression. No push, merge, deploy, or production write in either repository. Full detail: `docs/STATE.md`'s 2026-08-23 entry.

## 2026-08-23 - Market-Wide Current Fundamental Research Scale-Out

`MARKET_WIDE_CURRENT_FUNDAMENTAL_RESEARCH_SCALEOUT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. A new `market_wide_current_fundamental_research.py` joins two already-existing, independently-qualified fundamental-evidence lanes -- the officially-qualified panel (`fundamental_research_readiness.py` / P3-B run over the current `p3f13_official_financial_evidence_scaleout.py` cohort) and the broad provider-research tier (`p3f10_fundamental_evidence_scaleout.py`'s full 523-candidate disposition matrix, retagged with P3-F15/P3-F16's `OFFICIAL_QUALIFIED`/`PROVIDER_RESEARCH`/`BLOCKED` vocabulary) -- into one deterministic, sector-aware, coverage-explicit artifact, then wires it through `export_ai_bundle.py` into the Consumer using the exact opt-in explicit-path/content-hash convention already established by `market_wide_current_liquidity_research`/`market_wide_current_descriptive_research`. It computes no new evidence and reopens no closed evidence-acquisition cohort.

`p3f13_official_financial_evidence_scaleout.py` gains two additive keys, `refreshed_panel_data` and `refreshed_fundamental_readiness`, exposing the current 13-issuer panel/readiness it already computes internally on every run (previously only its content hash was kept, mirroring `p3e_fundamental_coverage_closeout.py`'s own existing convention for the same two key names) -- every previously existing key, value, and its own 6-test suite are unchanged. The new module reads that current official panel plus P3-F10's frozen 2026-08-20 per-instrument disposition checkpoint, and for any ticker P3-F13 has since qualified (PNJ, FPT today), always prefers the current truth and records an explicit `supersedes_frozen_p3f10_disposition` note rather than serving a stale per-ticker view; PNJ's stale `sector="unknown"` tag is corrected to `corporate` in the process. A cross-repository content-identity guard (`p3f13_current.source_artifacts.p3f10 == p3f10_frozen.artifact_identity`) fails closed if the two inputs ever diverge.

Coverage over the fixed 523-candidate cohort: 13 `OFFICIAL_QUALIFIED` (94 exact metrics, 22 proxies, 49 missing, 9 sector-inapplicable `NOT_APPLICABLE`, full per-metric lineage/periods/family-state each), 507 `PROVIDER_RESEARCH` (retained VCI/KBS statement-family presence only, scope/currency/scale `UNKNOWN_FAIL_CLOSED`, zero computed metric values), 3 `BLOCKED` (no retained source). Evidence presence and usable-metric presence are reported as two distinct, never-conflated numbers: PNJ and FPT are both `OFFICIAL_QUALIFIED` yet both independently resolve `fundamental_research_readiness = BLOCKED` (every metric MISSING on a single retained period or an unreconciled input), so `issuers_with_official_facts = 13` while `issuers_with_usable_deterministic_metrics = 11`. Bank/securities sector-inapplicable metrics (VCB's `debt_to_equity`/`net_debt`/`cash_flow_to_earnings`) remain `NOT_APPLICABLE`, never missing or zero.

`export_ai_bundle.py` gains `--include-market-wide-current-fundamental-research` / `--market-wide-current-fundamental-research-path` (not enabled in any default/production invocation), mirroring the existing liquidity/descriptive attach layers exactly: fail-closed content-hash verification, verbatim per-ticker pass-through, `is_actionable=false` unconditional. Consumer (`ai-core-private`): `builders/build_ticker_context.py` gains the matching `market_wide_current_fundamental_research_contract`/`apply_bundle_*` pass-through, validating the two-shape safety envelope (full metric detail for `OFFICIAL_QUALIFIED`, disposition/allowed-forbidden-uses only for `PROVIDER_RESEARCH`/`BLOCKED`) and never upgrading one tier's record toward the other. 19 new Producer tests and 22 new Consumer tests pass. A full 4,161-test Producer sweep (4,125 passed / 20 failed / 13 skipped) and a full 696-test Consumer sweep (687 passed / 10 failed / 1 skipped) both reproduce their exact failure sets byte-identically on the unmodified pre-milestone checkout -- confirmed pre-existing (stale VCB/VNM/HPG evidence-state and share-basis fixtures, a `tools/handoff.py`-vs-`STATE.md` heading-format mismatch predating this session, missing-pre-generated-artifact/registry-shadow cases), not a regression.

**Negative boundaries:** no official-evidence acquisition, source-route discovery, or provider-semantic-inference promotion was reopened; `MARKET_WIDE_FINANCIAL_EVIDENCE_AND_SEMANTIC_COVERAGE_V1`'s 2026-08-22 `CLOSED_PARTIAL` gate is unchanged. No valuation, target price, ranking, recommendation, probability, portfolio sizing, PIT/backtest, or new DCF assumption exists anywhere in the artifact or its Consumer contract (verified by an explicit absence test). No new packet/workbench/digest/orchestration abstraction; no runtime/production database write; no push, merge, or deploy.

**Provider-series trend scale-out addendum.** The existing provider-tier permission for `provider_series_growth` is exercised strictly within this contract, using only the P3-F10-pinned retained canonical facts. `PROVIDER_RESEARCH` records may now carry revenue/earnings growth and assets/equity/operating-cash-flow direction only when two `provider_reported` facts share ticker, provider, canonical identity, and consecutive quarterly periods; conflicted/partial facts, provider switches, period gaps, and non-positive growth bases fail closed. The output is a trend/direction, not an absolute provider financial fact; every metric retains provider, periods, method, `PROVIDER_RESEARCH`, status, fact/observation lineage, limitations, comparability scope, and an exact blocker. Consumer validates and passes through this envelope verbatim, rejecting any absolute `value` field. This produces 1,236 available trends across 500 of 507 provider-research issuers, while 1,299 metrics remain explicitly blocked. No official evidence or tier is overwritten, and official-qualified records remain the stronger independent lane.

**Period-basis integrity correction.** Consecutive labels alone are not duration evidence. The contract now gives each trend pair a retained period-basis record (fiscal end/year/quarter, provider, scope, currency/scale state, semantic identity, and duration basis). Only balance-sheet `POINT_IN_TIME` comparisons and cash-flow pairs independently evidenced `SINGLE_QUARTER` survive; provider income-statement flows remain duration `UNKNOWN` and are blocked rather than inheriting cash-flow evidence. No YTD subtraction or other transformation is retained. Result: 1,054 valid trends, 1,481 blocked; 900 Q4→Q1 baseline transitions become 883 valid / 0 transformed / 17 blocked.

**Provider income-statement period semantics and trend recovery decision.** `KBS` and `VCI` are endpoint-specific, never interchangeable. A bounded first-party KBS schema check for `finance-info/{ticker}` with `type=KQKD`, `termtype=2` found `TermCode`, `PeriodBegin`, and `PeriodEnd` per quarterly row; that is sufficient evidence to classify the KBS income-statement endpoint's Q1/Q2/Q3/Q4 values as direct `SINGLE_QUARTER` for provider-research comparisons. The retained canonical layer does not preserve the individual bounds/unit/audit/revision fields, so each result retains that limitation and never invents a date, currency, scale, scope, or restatement chain. The VCI endpoint's `quarters` response has only `yearReport`/`lengthReport` and timestamps in the review; absent a first-party duration definition it remains `UNKNOWN`, and neither quarter labels nor observed numeric behavior may change that. A deterministic YTD-to-quarter transform specification is recorded but disabled because no supported retained endpoint is evidenced YTD. The existing artifact gains KBS-only direct income period coverage plus QoQ/YoY sub-comparisons (81/1 revenue and 70/1 earnings respectively), all with provider/source-period/fact-observation/source-hash/basis/transform/limitation lineage; Consumer validates those nested comparison envelopes before verbatim pass-through. Authority remains `PROVIDER_RESEARCH` and all non-fundamental lanes remain out of scope.

**Financial entity-class evidence hierarchy decision.** The existing market-wide fundamental artifact may use retained classification evidence only in this order: current P3-F13 official issuer class; P2-E/P2-E3 already-qualified current-state class; preserved P3-F10 class (never re-derived); then one retained VCI industry classification mapped only for the artifact's `PROVIDER_RESEARCH` envelope. The VCI source has no global entity-authority effect, is retained with source record/as-of/method/qualification metadata, and cannot classify `Dịch vụ tài chính`; labels that imply unambiguous bank/insurance/nonfinancial corporate sectors may be used, while conflicts among positive retained sources fail closed. This yields 440 concrete current-artifact research classifications (442 unknown to 2) without changing `entity_classification_contract.py`, the promoted registry, taxonomic classes, or any tactical rule. The existing sector-taxonomy result is attached as an applicability disclosure only: it blocks ordinary corporate `ebitda`/`ev_ebitda` for financial intermediaries, but cannot block the independently permitted same-provider descriptive trend envelope. KBS single-quarter and VCI unknown-duration semantics remain exactly unchanged. Artifact identity: `market_wide_current_fundamental_research:8b9dd05db11fa5c632906260c81c3e294cb40ad5fde56bd8f78c2d698df0449b`.

## 2026-08-23 - Market-Wide Fundamental Trajectory Context

`MARKET_WIDE_FUNDAMENTAL_TRAJECTORY_CONTEXT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL`. The existing fundamental artifact is extended in place with a descriptive, independent-dimension trajectory envelope only. A provider-research context may expose the existing comparable KBS QoQ revenue/earnings direction and basis, their deterministic alignment, the existing same-provider assets/equity/OCF directions, period coverage, entity class, and explicit limitations; it does not recalculate facts, values, quality, or a composite score. Revenue/earnings alignment requires matching provider/period pairs and uses only `BOTH_EXPANDING`, `REVENUE_UP_EARNINGS_DOWN`, `REVENUE_DOWN_EARNINGS_UP`, `BOTH_CONTRACTING`, `PARTIAL`, or `UNAVAILABLE`; balance-sheet movement is an explicitly non-evaluative descriptive state. The existing provider-series output does not carry a previous comparable direction, so acceleration is explicit `UNAVAILABLE`, rather than inferred. Official records receive `OFFICIAL_METRIC_CONTEXT_ONLY`, never a provider-derived direction, and Consumer validates the optional envelope before deep-copying it. The watchlist tactical engine remains unchanged and ignores the additive field, preserving frozen verdicts. No classification/period-semantic/source-route work is reopened and no authority is promoted. Artifact: `market_wide_current_fundamental_research:fc7619fcd7d0f5077a396c9e05fcdce14e97bdcdc078722c49e67070990d0feb`.

## 2026-08-23 - Current Screening Research Consumption Closeout

`CURRENT_SCREENING_RESEARCH_CONSUMPTION_CLOSEOUT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. The completed `current_market_screening_opportunity_comparison_foundation` artifact is made usable through the already-existing `market_wide_current_descriptive_research` Producer→Consumer contract only: `export_ai_bundle.py` adds a default-off explicit path that nests `screening_comparison` inside `tickers[ticker].market_wide_current_descriptive_research`; it does not create a top-level packet/key, feature store, digest, workbench, or orchestration layer. Both retained artifact identities must verify, and the screening artifact's source descriptive identity, session, denominator, and complete ticker set must match before the Producer attaches any result. A requested screening extension with a missing, tampered, or mismatched artifact fails the complete attach step closed.

The nested record preserves the screening artifact verbatim: 1,510 denominator, 960 observed cohort, exact eligible/intersection counts and coverage ratios, session, lineage, quality state, definitions, independent membership flags, market/sector comparison summaries, ticker-level percentile/bucket context, unavailable reasons, authority boundary, and blocked outputs. Consumer validates that safety envelope, including every four screen memberships and their coverage, then deep-copies it without recomputing or scoring. The retained `UNAVAILABLE` semantics, all four insufficient sector cohorts, and SHB's `g1_v_reconciliation_verdict = OTHER` warning remain binding. The Consumer prompt contract explicitly prohibits turning these independent descriptive flags or percentiles into a composite opportunity score, ordinal ranking, BUY/SELL/HOLD, target, probability, valuation, portfolio, sizing, execution, traded value/turnover/ADV/ADTV, PIT/RAW_AS_TRADED, or backtest claim.

The new Producer/Consumer frozen-time E2E imports the actual sibling Producer attachment code and reads only the two retained artifacts. It proves byte-identical Consumer context for current, stale, session-missing, sector-insufficient, and SHB-warning records, while a ticker outside the retained universe gets no key and a malformed nested extension fails closed. No provider/network activity, runtime/production write, default enablement, source/capability authority, or Consumer inference occurs.

## 2026-08-23 - Current Market Screening and Opportunity Comparison Foundation

`CURRENT_MARKET_SCREENING_AND_OPPORTUNITY_COMPARISON_FOUNDATION_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. `current_market_screening_opportunity_comparison_foundation.py` is a single offline consumer of the retained rebuilt `market_wide_current_descriptive_research` artifact, not a new feature store, digest, workbench, research packet, or orchestration abstraction. It checks the source artifact identity and contract version before materialization and gives every aggregate/result its source identity, 2026-08-21 session, 1,510 current descriptive denominator, 960 observed-session cohort, exact eligible count, coverage ratio, and explicit partial-coverage state.

The output is intentionally independent descriptive flags, never a composite: trend-plus-positive-momentum (241 from the 956 same-session technical records), momentum above its same-session cohort median (478/956), provider-scoped relative volume above its same-session cohort median (478/956), and the exact same-session-technical/current-descriptive-liquidity intersection (951/1,510). The consumer does not promote `relative_volume_provider_scoped` into liquidity authority. A technical stale, session-missing, or unavailable record is emitted as unavailable with its reason, never inferred as a zero or a negative screen result.

Market-relative descriptive percentile/bucket context is available only for the same 956 current technical records and explicitly states it is not an ordinal ranking. Sector-relative context reuses only retained `AVAILABLE` sector cohorts: 946 records are eligible; missing/unsupported identity and each insufficient sector cohort fail closed. Liquidity context remains 955 eligible records, preserves board composition and `grossTradeAmount`'s non-authoritative state, and passes SHB's `G1/v` `OTHER` four-unit residual into every SHB liquidity-consuming result. The artifact emits no ordinal ranking, opportunity score, recommendation, target/expected-return/probability, portfolio/sizing/execution, traded value/turnover/ADV/ADTV, RAW_AS_TRADED/PIT/backtest, historical, or active-universe authority.

## 2026-08-23 - Market-Wide Current Technical Coverage Scale-Out

`MARKET_WIDE_CURRENT_TECHNICAL_COVERAGE_SCALEOUT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. This is a narrow, foreground-resumable reuse of the established DNSE OHLC and `mva_daily_research_bundle.market_features()` contracts, not a new feature store, technical-indicator family, universe engine, or research orchestration layer. Technical history remains provider-scoped current descriptive evidence (`SHADOW_ONLY` / adjusted-retrospective; never `RAW_AS_TRADED` or PIT).

The pre-acquisition ledger is deterministic: 763 same-session technical records, 52 stale-but-available records, and 695 unavailable records over the 1,510 current descriptive denominator. All 52 stale records have 20+ prior valid bars but a `SESSION_MISSING` target bar. Of the 695 unavailable records, 498 also lack the target bar (142 have zero retained bars; 356 retain 1–19) and cannot become a same-session feature through more prior history; the remaining 197 retain the 2026-08-21 bar but only 1–19 observations, so are the sole recovery candidates.

Twenty fixed, sequential foreground batches acquired only those 197 extended-history windows through the already-qualified DNSE `/price/ohlc` path, preserving raw response bodies, payload hashes, exact target session, query contract, and provider field provenance. There were 193 `RECOVERED_COMPLETE_TECHNICAL_HISTORY` results and 4 `INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK`; no response was retried, zero target-session bars were fabricated, and no missing session was treated as zero-volume/no-trade. The rebuilt existing descriptive-research artifact therefore reports 956 same-session technical records, 52 stale, and 502 unavailable (498 target-bar-missing plus 4 history-insufficient): 956/1,510 = 63.311258% denominator coverage and 956/960 = 99.583333% observed-session coverage.

The existing per-record `technical_features` shape and Consumer pass-through remain compatible; recovered records carry only an additive provenance object. Current descriptive breadth and cross-sectional screening must still report coverage. No stock ranking, recommendation, target, probability, opportunity score, portfolio output, ADV/ADTV, liquidity, sizing, execution, historical membership, corporate-action/ex-date, PIT, or valuation authority is created. Artifacts: `operations-review/market-wide-current-technical-coverage-scaleout-v1-20260823/market_wide_current_technical_coverage_recovery_artifact.json` (`market_wide_current_technical_coverage_scaleout:60ab3fe5745160db05ad4240de8601e2ae3ab2ad63b0c2145740a1643c6a3d35`) and `market_wide_current_descriptive_research_artifact.json` (`market_wide_current_descriptive_research:8660d4ece155e91895557a0f7b70a6a501ab5ebcee8978818199084a88a6c9b6`).

## 2026-08-23 - Market-Wide Current Research End-to-End Integration

`MARKET_WIDE_CURRENT_RESEARCH_END_TO_END_INTEGRATION_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. Completes the Producer -> AI bundle -> Consumer ticker-context path for the retained `market_wide_current_descriptive_research` artifact, opt-in only, without creating a new feature store, research packet, digest, workbench, case abstraction, or orchestration layer. Cross-repository milestone: Producer `stock-core-private` and Consumer `ai-core-private` (commit `ec3d4d54b9807c3ba16066dd85084f9b770da2a8`).

**Producer.** `export_ai_bundle.py` gains one new opt-in attach path, mirroring `attach_market_wide_current_liquidity_research` exactly: `load_market_wide_current_descriptive_research_artifact()` (fail-closed content-hash verification via the artifact's own new `content_identity()`), `build_market_wide_current_descriptive_research_for_ticker_safe()` (per-ticker payload: the retained record verbatim, plus a `market_coverage` block carrying `current_active_equity_denominator`=1,510/`observed_session_cohort`=960/coverage ratios/`quality_state`, plus `blocked_outputs`, plus `status`/`is_actionable=false`), and `attach_market_wide_current_descriptive_research()` (disabled by default; a missing path, unreadable file, or hash mismatch fails the whole step closed). New CLI flags `--include-market-wide-current-descriptive-research` / `--market-wide-current-descriptive-research-path`, both **not enabled in any default/production invocation**.

**Consumer.** `builders/build_ticker_context.py` gains `market_wide_current_descriptive_research_contract()` / `apply_bundle_market_wide_current_descriptive_research_contract()`, mirroring the existing `market_wide_current_liquidity_research_contract()` pattern: verbatim pass-through when structurally valid (correct ticker, `is_actionable=false`, a known `activity_and_session_state`, valid `technical_features`/`liquidity`/`sector_state` shapes, and the mandatory `market_coverage`/`blocked_outputs` blocks present), else fail closed to an explicit `malformed` record. A ticker outside the retained artifact's universe gets no key at all. `prompts/ai_analysis_templates.md` gains one new lane paragraph (mirroring the existing `market_wide_current_liquidity_research` paragraph) plus four new numbered prohibited-claims items: the model must always state `market_coverage` alongside any breadth/sector claim, must never report a stale (`is_current_session=false`) technical-feature value as today's, must never fill in a `sector_state.status = UNAVAILABLE_INSUFFICIENT_COVERAGE` sector, and cannot derive a ranking/recommendation/target-price/portfolio-weight/position-size/traded-value/turnover/ADV/ADTV figure from this lane.

**Preservation, verified against real captured values.** SHB's known four-unit G1/v `OTHER` residual survives unmodified end-to-end. A genuine stale (`is_current_session=false`) technical-feature record stays labeled stale through the complete real pipeline, never silently read as the current session's return/momentum/trend. A `sector_state.status = UNAVAILABLE_INSUFFICIENT_COVERAGE` cohort is never filled in or broadened by either layer. `grossTradeAmount` remains non-authoritative throughout; no traded-value/turnover/ADV/ADTV/sizing/execution field is ever computed or exposed.

**Frozen-time E2E.** A new Consumer-side test suite (`test_market_wide_current_descriptive_research_frozen_time_e2e.py`) imports the real, already-committed Producer `export_ai_bundle.py`/`market_wide_current_descriptive_research.py` read-only and runs them against the real retained artifact already on disk, feeding the real output through the real Consumer contract -- offline, single-threaded, zero DNSE/network calls, zero runtime/production writes. All 6 tests pass against the real 1,683-candidate cohort, covering every activity-state family (`ACTIVE_LISTED_OBSERVED`, `ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION`), the real SHB residual, the real 1,510/960 coverage figures, and a real stale-technical-feature ticker.

**Validation.** Producer: 16 new bundle-attach unit tests plus the existing 44 focused/dependent regression tests plus a broader 562-test `export_ai_bundle.py`-dependent sweep, all passing except 10 pre-existing failures independently confirmed unrelated (real VCB/VNM/HPG financial-evidence and runtime-manifest tests that depend on retained-evidence state this milestone never touches). Consumer: 27 + 9 + 6 = 42 new tests plus a 422-test `build_ticker_context.py`/prompt-dependent sweep, all passing except 4 pre-existing failures reproduced identically in isolation (an unrelated metadata-registry-snapshot naming contract, and one batch-dry-run test needing pre-generated context packages). `py_compile` and `git diff --check` clean in both repositories. No push, merge, deploy, or production write in either repository; the five protected Producer WIP files and the unrelated Consumer WIP (`hpg_multi_angle_eval_*`) are untouched.

## 2026-08-23 - Market-Wide Current Descriptive Research

`MARKET_WIDE_CURRENT_DESCRIPTIVE_RESEARCH_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. Turns the already-qualified current-market inputs into one deterministic market-wide descriptive-research artifact -- breadth, sector breadth, cross-sectional technical features, and liquidity -- without creating a new feature store, digest, workbench, packet, case abstraction, or orchestration layer, and without opening ranking, recommendation, historical PIT, or portfolio authority.

**Reuse, not reinvention.** New pure module `market_wide_current_descriptive_research.py` imports, unmodified: `mva_daily_research_bundle.market_features()` for per-ticker technical features (close, return_1d, momentum_20d, ma_3/5/20, volatility_20d, relative volume); `market_regime_breadth_context._descriptor()` for the same 0.60-threshold breadth/momentum classification rule already used market-wide; `sector_relative_research_context.MIN_COHORT_MEMBERS` / `_bucket()` for the same fail-closed minimum-cohort-size rule and percentile bucketing, plus its two existing entity-classification loaders (`load_qualified_entity_classes`, `load_provider_descriptive_industry_classes`) for sector identity; and `market_wide_current_liquidity_research.content_identity()` to verify the retained liquidity artifact before attaching any record. It joins these against this project's own immediately preceding milestone, `current_universe_status_and_session_coverage_resolution` (read, not rebuilt), for the corrected 1,510 `current_active_equity_denominator` / 960 `observed_session_cohort` split, and re-reads (never refetches) the same retained P3F9B exact-session snapshot for OHLC history. All four retained inputs are session- and snapshot-identity cross-checked (2026-08-21 throughout) and fail closed on any mismatch.

**A correctness point `market_features()` does not itself expose:** it computes over whatever chronological window it is handed without asserting the window's last row is the *target* session. For a ticker whose target-session bar is missing, the window's last row is an earlier session, so its `return_1d`/`momentum_20d` are stale, not "today's." Every technical-feature result is labeled with its actual `feature_as_of_session` and an explicit `is_current_session` flag; same-session breadth and sector aggregation include only records where that flag is true. Over the real 1,683-candidate cohort this yields 763 same-session technical-feature records (out of 960 `observed_session_cohort`, i.e. 79.48%; 50.53% of the 1,510 denominator) plus a separately-tracked 52 stale-but-available records that are never counted toward "today's" breadth -- the "partial coverage masquerading as full-market breadth" failure mode this milestone is required to avoid.

**Results.** Market breadth over the 763 same-session-eligible records: 457 advancing, 160 declining, 146 unchanged (`MARKET_BREADTH_MIXED`, 59.9% advancing, just under the 0.60 threshold); 20-day momentum breadth is `MOMENTUM_BREADTH_NEGATIVE` (67.4% negative) -- a real, non-contradictory divergence between a same-session bounce and a broader prior drift, not a bug. Sector breadth: 20 of 24 classified cohorts reach the 5-member same-session minimum and report `AVAILABLE` (advancing/declining/median-momentum/percentile positions); 4 fail closed `UNAVAILABLE_INSUFFICIENT_COVERAGE`. Liquidity: 955/1,510 (63.25%) carry an eligible board-composition record (G1/G4/T1/T3/T4/T6 preserved verbatim); SHB's known four-provider-unit G1/v `OTHER` residual is the sole reconciliation warning (954/955 remain `EXACT_MATCH`), surfaced explicitly and never coerced. `grossTradeAmount` remains `NON_AUTHORITATIVE_SCALE_BASIS_UNRESOLVED`; no traded-value, turnover, ADV/ADTV, sizing, or execution metric is computed. No stock ranking, BUY/SELL recommendation, probability, target price, or portfolio weight/size is emitted anywhere in the artifact (verified by an explicit absence test, not merely by omission). Historical RAW_AS_TRADED/PIT, corporate-action/ex-date, backtesting, historical membership, and active-universe promotion are untouched. Artifact: `operations-review/market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json` (`market_wide_current_descriptive_research:573bfafafad0ac18c58aca6d778952157078405d2a4039bb5a5eaae0938c0b97`).

## 2026-08-23 - Current Universe Status and Session Coverage Resolution

`CURRENT_UNIVERSE_STATUS_AND_SESSION_COVERAGE_RESOLUTION_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. Builds directly on the retained `current_market_universe_breadth_foundation` artifact (read, not rebuilt) to add two further explicitly separate dimensions -- provider support and listing/activity status -- without altering membership or session-observability.

**Finding.** `dashboard-runtime/vn_stock.db`'s `metadata.exchange` column (VCI-sourced via `meta_sync.sync_exchange_industry` <- `Listing(source="VCI").symbols_by_exchange()`, already relied on by `candle_scan.py`, `live_universe.py`, `stock_analyzer.py`, `release_session_contract.py`, and `publish_dashboard.py`) carries the explicit value `DELISTED` for exactly 173 of the 1,683 candidates -- and those 173 are the *exact same* 173 records the retained P3F9B session-2026-08-21 snapshot marks `PROVIDER_REJECTED` (DNSE `/price/ohlc` HTTP 400). The correspondence is perfectly symmetric in both directions (173/173), from two independently-sourced signals (DNSE's own session endpoint and VCI's separately-synced listing classification) -- materially stronger than the single-source "legacy marker, mechanism unqualified" case `canonical_instrument_reconciliation.py`'s `_field_specs()` already anticipated and deliberately fenced off: its normalized `listing_status` stays `LISTING_UNKNOWN` for every provider unconditionally, by design, per that function's own inline comment. `canonical_universe_tiers.py`'s `_active()` already has a dormant `listing_status in {"INACTIVE", "DELISTED"}` branch that has never received a non-`UNKNOWN` input. Neither file is modified by this milestone; the evidence is surfaced only in a new, narrower, explicitly non-authoritative artifact, exactly like every recent current-* sibling milestone in this document.

**Resolution.** All 173 `PROVIDER_REJECTED` records -- 125 of which carry confirmed `EQUITY` membership and 48 of which are the breadth-foundation's `SECURITY_MASTER_SYMBOL_NOT_RETAINED` unknowns -- resolve to a new `INACTIVE_OR_DELISTED` activity state via this cross-provider corroboration: 0 residual unresolved, 0 of the 48 kept `UNKNOWN`. `membership_state` itself is left byte-unchanged for every record; the resolution lives only in the new `activity_and_session_state` dimension, so the underlying DNSE-specific fact is never overwritten. The 550 `SESSION_MISSING` records are investigated by re-reading -- never refetching -- each one's already-retained ~45-day OHLC lookback window from the P3F9B snapshot: 408 have at least one nearby bar (a target-date-only gap) and 142 have none at all in the whole window. Both sub-populations stay `ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION`, never promoted to inactive and never treated as a proven zero-trade session -- the only genuine zero-trade proof anywhere in this codebase remains the bounded QNS `trades_history` exhaustive-pagination precedent (`dnse_trades_liquidity_basis.py`, 2026-08-23), not replicated here for a 550-record cohort.

**Corrected denominator.** `current_active_equity_denominator = 1,510` (960 `ACTIVE_LISTED_OBSERVED` + 550 `ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION`), replacing the prior 1,635-candidate breadth-foundation figure for coverage purposes. Coverage recomputes to `960 / 1,510 = 63.576159%` (previously `960 / 1,635 = 58.715596%`). `UNSUPPORTED_OR_INVALID_PROVIDER_SYMBOL` and residual `UNKNOWN` are both 0 for this specific cohort -- a fully-evidenced, correct outcome, not an unexplained gap; a `NOT_APPLICABLE_NON_EQUITY` state is defined for determinism but has 0 members here since this cohort has no non-equity class. No active-listing authority, `ACTIVE_UNIVERSE` promotion, historical/PIT membership, RAW_AS_TRADED, liquidity/ADV/ADTV, sizing, execution, ranking, valuation, or recommendation authority is created; `canonical_universe_tiers.py` and `canonical_instrument_reconciliation.py` are unmodified. New reusable evidence module: `vci_exchange_reference_snapshot.py` (a frozen, content-hashed snapshot of the already-retained `metadata.exchange` column -- no new provider, no live network call). Artifacts: `operations-review/vci-exchange-reference-snapshot-v1-20260823/vci_exchange_reference_snapshot_artifact.json` and `operations-review/current-universe-status-and-session-coverage-resolution-v1-20260823/current_universe_status_and_session_coverage_resolution_artifact.json`.

## 2026-08-23 - Current Market Universe and Breadth Foundation

`CURRENT_MARKET_UNIVERSE_AND_BREADTH_FOUNDATION_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. The retained P3F9B 1,683-candidate snapshot and the preceding current-reference qualification are evidence inputs, not automatic authority. This milestone corrects the prior category error: current DNSE security-master equity-candidate membership is independent of completed-session OHLC availability. `SESSION_MISSING`, `INCOMPLETE`, and `PROVIDER_REJECTED` never by themselves exclude an otherwise classified equity candidate.

The canonical current descriptive membership denominator is 1,635 `EQUITY` candidates from the retained complete 3,254-row DNSE instruments reference; its status is `CURRENT_DNSE_SECURITY_MASTER_EQUITY_CANDIDATE_ONLY`, not active-listing or authoritative market membership because DNSE instruments omits listing status. The 48 symbols absent from that reference were checked against retained qualified security-master infrastructure and remain unresolved, so are explicitly `UNKNOWN` rather than inferred from the P3F9B request type or their rejected OHLC responses. No non-equity class was evidenced in this specific candidate set, but the projection keeps evidenced ETF/fund, warrant, bond, derivative, and other non-equity classes distinct and excludes them only from this equity-candidate scope.

Session observability is a second ledger over all 1,683 candidates: 960 `OBSERVED`, 550 `SESSION_MISSING`, 173 `PROVIDER_REJECTED`, and 0 `INCOMPLETE`. Its membership cross-tab is 960 included/observed, 550 included/missing, 125 included/rejected, and 48 unknown/rejected. The observed analytical cohort is therefore 960 / 1,635 = 58.715596%; it can support only current descriptive breadth and cross-sectional screening with that exact coverage disclosure. Promotion remains owner review required and non-authoritative: no active listing, historical constituent, survivorship-safe/PIT, RAW_AS_TRADED, liquidity/ADV/ADTV, sizing, execution, ranking, valuation, recommendation, or other investment authority is created. Artifact: `operations-review/current-market-universe-breadth-foundation-v1-20260823/current_market_universe_breadth_foundation_artifact.json`.

## 2026-08-23 - Market-Wide Current Research-Universe Qualification

`MARKET_WIDE_CURRENT_RESEARCH_UNIVERSE_QUALIFICATION_V1 = COMPLETE_LOCALLY / OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE`. The immutable candidate denominator is the retained 1,683-record P3F9B current-session snapshot, not a reconstructed security master or historical constituent set. A complete, foreground-retained 3,254-row DNSE instruments reference was joined deterministically. Each candidate has exactly one disposition: 960 `INCLUDED` current descriptive equities with exact-session observations; 675 `EXCLUDED` for their retained current-market `SESSION_MISSING` (550) or `PROVIDER_REJECTED` (125) disposition; and 48 `UNKNOWN` for `SECURITY_MASTER_SYMBOL_NOT_RETAINED`. No unknown identity or listing state was inferred.

DNSE instruments classifies 1,635 candidate symbols as `EQUITY` and leaves 48 `UNKNOWN`; its payload does not establish current listing status, so every record explicitly preserves `UNKNOWN_NOT_PROVIDED_BY_DNSE_INSTRUMENTS`. The contract remains capable of separately excluding ETF/fund, warrant, bond, derivative, and other non-equity classes if evidenced; none was evidenced in this specific candidate set. Reference-symbol duplication is never silently selected and is fail-closed as an ambiguous symbol.

The resulting 960-record set may support current descriptive breadth and cross-sectional screening only. It preserves raw observations and separate capability eligibility for excluded symbols, and does not create authoritative market membership, historical constituents, survivorship-safe/PIT universe, RAW_AS_TRADED, ranking, valuation, recommendation, or execution authority. Promotion remains `OWNER_REVIEW_REQUIRED_NOT_AUTHORITATIVE` because listing status is unavailable from the retained primary reference. Artifact: `operations-review/market-wide-current-research-universe-qualification-v1-20260823/market_wide_current_research_universe_artifact.json`.

## 2026-08-22 - Financial Evidence Program Closure and Enrichment Pause

`MARKET_WIDE_FINANCIAL_EVIDENCE_AND_SEMANTIC_COVERAGE_V1 = CLOSED_PARTIAL / SOURCE_ROUTE_AND_EVIDENCE_CONSTRAINED`. The retained 520-issuer VCI/KBS provider estate remains descriptive-only: generic calculation-grade semantic promotion was rejected, and no provider fact received official authority. The official panel remains 13 issuers / 138 canonical facts / 94 exact research metrics; further scale-out is blocked by approved route/evidence coverage rather than calculation code. Do not reopen provider-semantic inference without materially new evidence. `MARKET_WIDE_ENRICHMENT_AND_CANONICALIZATION_V1 = PAUSED_RATE_LIMIT_CONSTRAINED`, not closed.

## 2026-08-22 - Corporate Action and PIT Authority Closure

`CORPORATE_ACTION_AND_PIT_AUTHORITY_V1 = CLOSED_PARTIAL / OFFICIAL_EX_DATE_AND_PRICE_BASIS_EVIDENCE_CONSTRAINED`. The reusable official corporate-action ledger exists and HPG executed share-change lineage is qualified, but no representative event chain is PIT-qualified because no retained representative corpus document provides an explicit official ex-date. Record, listing, effective, and trading dates never substitute for ex-date; `RAW_AS_TRADED` remains **NOT PROMOTED** and provider-adjusted/retrospective prices remain non-PIT. Do not reopen implementation without materially new official event/price-basis evidence. Next program: `OFFICIAL_SOURCE_ROUTE_AND_EVIDENCE_COVERAGE_SCALEOUT_V1` (not started).

## 2026-08-22 - Official Source Route and Evidence Coverage Scaleout V1

`OFFICIAL_SOURCE_ROUTE_AND_EVIDENCE_COVERAGE_SCALEOUT_V1 = PARTIAL_OFFICIAL_ROUTE_SCALEOUT_WITH_EXPLICIT_GAPS` (`official_source_route_coverage.py`, `tools/run_official_source_route_coverage_scaleout.py`, `push = NO`).

1. The reusable record contract independently records instrument/issuer identity, source family, canonical locator/domain, hash-bound ownership evidence, route pattern, exact-locator capability, demonstrated evidence categories, archive/publication visibility, content/access/rate state, provenance, lifecycle state, blocker, and deterministic route identity. `ROUTE_DISCOVERED → ROUTE_OWNERSHIP_PROVEN → ROUTE_TECHNICALLY_REACHABLE → ROUTE_CAPABILITY_CHARACTERIZED → ROUTE_READY_FOR_OWNER_PROMOTION → ROUTE_APPROVED` is fail-closed: no earlier record implies a later state. Roadmap counts are cumulative gate coverage, while an explicitly named terminal-state distribution remains available for diagnostics. The contract is non-activating and cannot modify the official source registry.
2. The relevant retained denominators are a 523-member 2026-08-20 empirical-active research cohort and a separate 524-member 2026-08-21 shadow snapshot, not a 524-to-523 canonical-subset exclusion. The later snapshot has three entrants (`HMS`, `VPS`, `VTC`), two exits (`BRS`, `CCS`), and a 521-member intersection. Route baseline remains 22 issuer routes already approved for acquisition scope (13 retained official-evidence issuers plus nine owner-activated issuer hosts), zero ownership-proven unapproved routes, two historical ambiguous/rejected paths, 510 issuers without a usable official financial-evidence route, and three governed source families (`issuer_ir`, exchange disclosure, VSDC). These dimensions deliberately do not sum because owner activation is not document/evidence capability.
3. The only seven repository-supported exact unapproved issuer candidates were probed once each. Cumulative lifecycle coverage is 7 discovered, 1 ownership-proven, 1 technically reachable, and 0 characterized/ready/approved; the exclusive terminal-state distribution is six `ROUTE_DISCOVERED` records plus ABB at `ROUTE_TECHNICALLY_REACHABLE`. `AAH`, `AAN`, `AAS`, `AAV`, `ACC`, and `VIC` have DNS/TLS/403/access blockers. ABB's retained 200 HTML response has a full legal identity match and SHA-256 `9b759a222fa490a513e1683b636642b5be054a91e8a4fe737aad128e1057a736`, but only generic listing-policy links. Those links do not establish any financial, corporate-action, or issuer-specific share/listing evidence category.
4. The materiality gate was not met: there are zero `ROUTE_CAPABILITY_CHARACTERIZED`, zero `ROUTE_READY_FOR_OWNER_PROMOTION`, and zero `ROUTE_APPROVED` records from this bounded discovery set. No promotion packet is emitted; no registry, document/fact, provider, PIT, RAW_AS_TRADED, liquidity, valuation, recommendation, or production database authority changed.

> **Authoritative Decision Surface.**
> This document maintains active and recent architectural decisions.
> Historical decisions are preserved in:
> - [`docs/archive/decisions/decisions-2026-08-01-to-2026-08-16.md`](archive/decisions/decisions-2026-08-01-to-2026-08-16.md) (August 1–16, 2026: P0 recovery, corporate actions, data lake v2)
> - [`docs/archive/decisions/decisions-2026-07-historical.md`](archive/decisions/decisions-2026-07-historical.md) (July – early August 2026: initial foundations, entity taxonomy, EODHD closure)

---

## Active & Recent Decision Records (2026-08-20 to Present)

## 2026-08-22 - Market Price/Volume Basis Authority V1

`MARKET_PRICE_VOLUME_BASIS_QUALIFICATION_V1 = COMPLETE_LOCAL_CONSOLIDATION_NO_NEW_AUTHORITY` (`market_price_volume_basis_authority.py`, `tools/derive_market_price_volume_basis_authority.py`, `tests/test_market_price_volume_basis_authority.py`, `operations-review/market-price-volume-basis-qualification-v1-20260822/market_price_volume_basis_authority_artifact.json`, `push = NO`).

1. **One reusable fitness-for-use matrix, zero new qualification claims:** the new module assembles 11 capability rows (5 price, 6 volume/value) across 8 downstream uses (`CURRENT_DESCRIPTIVE_RESEARCH`, `CURRENT_VALUATION_RESEARCH`, `LIQUIDITY_RESEARCH`, `ADV_ADTV_RESEARCH`, `POSITION_SIZING`, `HISTORICAL_RETURN_RESEARCH`, `PIT`, `BACKTEST`) by importing and citing `market_data_source_authority`, `provider_price_basis_registry`, `dnse_ohlc_price_basis_capability`, `dnse_provider_native_closed_ohlc`, `current_valuation_input_authority`, `market_volume_value_semantic_contract`, `market_capability_taxonomy`, `dnse_fhsc_volume_basis`, `dnse_fhsc_market_composition_scaleout`, `market_volume_capability_matrix`, and `official_corporate_action_ledger` -- never re-deriving a verdict those modules already own.
2. **Price basis result:** DNSE's current completed-session close is `ELIGIBLE` for `CURRENT_DESCRIPTIVE_RESEARCH` and as the price leg of `CURRENT_VALUATION_RESEARCH` (`current_valuation_input_authority.qualify_current_market_price`, `ADJUSTED_RETROSPECTIVE`); overall valuation readiness remains independently blocked by the unrelated, unchanged current-share-basis gate (0/11 `SHARE_READY`). Historical OHLC and the bounded HPG (`ISS` 2026-05-25) / VCB (`DIV` 2026-07-23) corporate-action windows remain representation-safe / current-analysis-safe only: `PIT` and `BACKTEST` are `BLOCKED` for every price row because `market_data_source_authority.DNSE_OHLC_PRICE_BASIS` remains `ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME` and no retained official document states an explicit ex-date for HPG/SSI/VCB/VNM (`missing_explicit_official_ex_date`).
3. **Volume/traded-value result:** the documented DNSE board mapping (`market_phase2_foundation.DNSE_BOARD_SEMANTICS`: `G1`=round-lot, `G4`=odd-lot, `T1`/`T3`=put-through round-lot, `T4`/`T6`=put-through odd-lot) is verified unchanged, not re-derived. Numeric per-board composition remains unavailable: its only historical source commit is `SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY`, and the scaled `C5=10xG1` shadow candidate remains `EMPIRICAL_CANDIDATE` with `semantic_unit_interpretation=UNKNOWN` and 67 unresolved residuals. DNSE's daily `v` field is cited against both the live canonical field contract (`market_volume_value_semantic_contract`: `PARTIALLY_QUALIFIED`, `MARKET_LIQUIDITY`/`EXECUTION_SIZING` explicitly prohibited) and the newer, narrower `DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL` / HOSE-only shadow finding -- the two are preserved as distinct evidence layers, not merged. DNSE traded value remains wholly absent (`DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE`); FHSC's matched/put-through/total volume and value decomposition is cited as bounded, rate-limited shadow-reference evidence only.
4. **Every authority-sensitive cell is fail-closed by construction:** `assert_registry_fail_closed()` raises if any row ever claims `LIQUIDITY_RESEARCH`, `ADV_ADTV_RESEARCH`, `POSITION_SIZING`, `PIT`, or `BACKTEST` as `ELIGIBLE`/`PARTIAL`, or if the echoed `qualified_liquidity_inputs` / `position_sizing_is_safe` / `raw_as_traded` invariants ever drift from `False` / `False` / `"NOT_PROMOTED"`. The current run's matrix passes with zero rows open on any authority-sensitive use; 36 dedicated tests plus 547 tests across the directly depended-on modules (`market_capability_taxonomy`, `price_representation_contract`, `dnse_ohlc_price_basis_capability`, `dnse_fhsc_volume_basis`, `dnse_fhsc_market_composition_scaleout`, `market_volume_value_semantic_contract`, `market_volume_capability_matrix`, `dnse_provider_native_closed_ohlc`, `dnse_closed_session_ohlc_representation`, `pit_price_reconstruction_contract`, `ohlcv_basis_qualification`, `current_share_basis_capability_reconciliation`, `market_basis_capability_registry`, corporate-action, `current_valuation_input_authority`, `dnse_volume_composition_reconciliation_p0b2b1`, `market_phase2_foundation`) all pass unchanged.
5. **Negative boundaries:** no RAW_AS_TRADED, PIT, liquidity, sizing, valuation-formula, common-shares-outstanding, or provider-authority promotion occurred. `market_wide_current_valuation_input_scaleout.py`, `tools/derive_market_wide_current_valuation_input_scaleout.py`, `tools/build_daily_analyst_brief.py`, and their tests were not touched; the five `HUMAN_REVIEW_REQUIRED` prospective research cases were not touched or approved. No network call, no runtime/production database write, no merge, deploy, or push.

## 2026-08-22 - Provider-Reported Current Valuation Proxy V1

`PROVIDER_REPORTED_CURRENT_VALUATION_PROXY_V1 = COMPLETE / NON_AUTHORITATIVE_RESEARCH_PROXY` (`push = NO`).

1. The method is exactly `PROVIDER_ISSUED_SHARES_PROXY`; every output is labelled `NON_AUTHORITATIVE_RESEARCH_PROXY` and remains distinct from authoritative current market cap or valuation.
2. Over the 11-symbol valuation cohort, proxy market cap, P/B, P/S, and EV-Sales each produce 9 outputs; P/E produces 8 and EV/EBITDA produces 0. SSI and VCB are blocked by unresolved corporate-action states.
3. Authoritative current valuation remains blocked. No common-outstanding, provider, historical/PIT, RAW_AS_TRADED, target, expected-return, recommendation, ranking, sizing, leverage, or portfolio authority changed.
4. Proxy logic is complete. The next blocker is broader retained exact-session price and qualified financial-input coverage; do not expand this proxy abstraction unless a separately authorized consumer requires it.

## 2026-08-22 - Current Common Shares Official Evidence Acquisition V1

`CURRENT_COMMON_SHARES_OFFICIAL_EVIDENCE_ACQUISITION_V1 = COMPLETE / NO_QUALIFYING_CURRENT_SHARE_EVIDENCE` (`push = NO`).

1. The exact current-valuation acquisition cohort is 11 symbols. Zero of 11 has authoritative common-shares-outstanding evidence continuous through 2026-08-19; nine retain official evidence but currentness remains unresolved.
2. SSI and VCB retain unresolved corporate-action execution/result states. HPG’s official issuer-IR notice states 8,442,964,520 shares effective 2026-07-02, but retained continuity reaches only 2026-07-30 and is not forward-filled.
3. Authoritative current market cap and current P/E, P/B, P/S, and EV remain blocked. No valuation implementation, historical/PIT/share authority, provider proxy authority, RAW_AS_TRADED, ranking, recommendation, sizing, leverage, or portfolio authority changed.
4. The official-document acquirer now retains every response stream chunk; a prior 1,024-byte capture is preserved non-citable, while the complete-stream retry is SHA-256 verified and idempotent. Do not reopen broad official-share acquisition without new finite evidence under existing route governance.

## 2026-08-22 - Current Share Basis Capability Reconciliation V1

`CURRENT_SHARE_BASIS_CAPABILITY_RECONCILIATION_V1 = COMPLETE / BLOCKED_BY_EVIDENCE` (`push = NO`).

1. The retained provider metadata universe is 1,683 rows, of which 1,680 are structurally usable only as non-authoritative issued-share proxies. The current valuation corpus is 11 rows and has 0/11 authoritative current-common-share denominators.
2. `VCI.overview.issue_share` remains `issued_shares`, not outstanding shares. Issued, listed, outstanding, period-end, and weighted-average identities are separately preserved; numerical equality is not semantic equivalence.
3. SSI and VCB remain stale-after-corporate-action cases because retained evidence does not establish action timing or resulting common shares. Missing treasury shares remain unknown rather than zero, so no issued-minus-treasury current-share result is manufactured.
4. Current market cap, P/E, P/B, P/S, and EV inputs remain authority-blocked. No historical/PIT/share authority, source authority, RAW_AS_TRADED, ranking, recommendation, sizing, leverage, or portfolio authority is promoted.

## 2026-08-22 - Scenario Distribution and Liquidity Reconciliation Checkpoint V1

`CAPABILITY_FIRST_SCENARIO_DISTRIBUTION_V1 = COMPLETE_LOCAL_CHECKPOINT` and `QUALIFIED_LIQUIDITY_INPUTS_RECONCILIATION_V1 = COMPLETE_LOCAL_RECONCILIATION_EVIDENCE` (`push = NO`).

1. Scenario Distribution V1 deterministically retains two distinct denominators: 12 real scenario cases and a 524-record universe. It creates no probability, target, recommendation, or ranking authority.
2. Liquidity Reconciliation V1 confirms DNSE `v` = FHSC matched volume in 35/35 discriminating retained observations within the tested scope. Missing and non-discriminating observations remain explicit.
3. The canonical DNSE board contract is centralized as `G1` round-lot, `G4` odd-lot, `T1`/`T3` put-through round-lot, and `T4`/`T6` put-through odd-lot. The prior reversed variable labels were implementation prior art; this correction does not create numeric board composition evidence.
4. Numeric board composition remains unavailable and `adv_turnover_input_eligible = false`. Neither checkpoint promotes liquidity, sizing, portfolio, PIT, RAW_AS_TRADED, probability, target, recommendation, or ranking authority beyond its explicit tested scope.

## 2026-08-22 - Capability-First Real EOD Vertical Slice V1 Validation

`CAPABILITY_FIRST_REAL_EOD_VERTICAL_SLICE_V1 = COMPLETE_LOCAL_PASS` (`tools/collect_market_evidence.py`, `tools/materialize_daily_market_research.py`, `tests/test_materialize_daily_market_research.py`, `operations-review/capability-first-real-eod-2026-08-21/`, `operations-review/daily-market-research-2026-08-21/`, `push = NO`).

1. **Real Bounded EOD Cohort & Completed Session**:
   - Resolved latest completed Vietnamese market session as `2026-08-21` (Friday, fully finalized post-close).
   - Collected across 3 liquid listed equities: `HPG`, `VCB`, `SSI`.
   - Queried `DNSE` (closed OHLC prices, foreign trading) and `FHSC` (trading volume/value history, foreign room, proprietary trading flow, order statistics/microstructure).
   - Executed synchronously with a 50-request budget: 21 requests sent, 21 HTTP 200 responses, 0 provider rate limits (429), 0 budget skips, 0 conflicts.

2. **Retained Session Packet & Raw Provenance**:
   - Retained packet: `operations-review/capability-first-real-eod-2026-08-21/session_packet.json`.
   - Packet identity: `packet:df7a6d73a0e8de762ce3d9261b8e9b5079fb57830529e0dc9d5c2f955a935f8a`.
   - All 21 raw payloads retained in `operations-review/capability-first-real-eod-2026-08-21/raw/` and SHA-256 byte verified against recorded manifests.
   - Observation breakdown: 21 `ACQUIRED`, 21 `RESEARCH_USABLE` (DNSE: 6 observations, FHSC: 15 observations). No secrets or credentials in any artifact.

3. **Deterministic Materialization & Offline Idempotent Replay**:
   - Materialization operator executed offline against retained session packet:
     - Run directory: `operations-review/daily-market-research-2026-08-21/daily-market-research-2026-08-21/run-a7be9379974d561ab0b2334057edbf4035d02952e56e005fbfd243232db52a07`.
     - Materialization identity: `daily_market_research_run:a7be9379974d561ab0b2334057edbf4035d02952e56e005fbfd243232db52a07`.
     - Canonical integration identity: `canonical_market_integration:f884d1a9846cc9b304a28941f7b529bd27444ff440ede83939fd42cd80db3416`.
     - Research artifact identity: `market-wide-research-artifact:1265038d6449eecb8ed9ff3d2a565d4260a831e6dab361e87c6d63ce96883419`.
     - Manifest content identity: `f087c3bca5281ee4d42b40258f300decd1babc582c1c132d04be4091e3161a58`.
   - Second offline execution confirmed idempotent replay (`is_idempotent_replay: true`) with byte-identical outputs, zero network calls, and completion inventory validation.

4. **Preservation of Strict Authority Boundaries**:
   - `authority_effect: "NONE"`.
   - Zero promotion of `RAW_AS_TRADED`, PIT backtest eligibility, liquidity/sizing authority, valuation authority, or recommendation authority.
   - Production database and runtime dashboards unmodified.
   - Next operational milestone: `CAPABILITY_FIRST_EOD_1800_OPERATIONAL_SCHEDULING_V1` (operational scheduling only; no scheduler configured or installed in this closeout).

## 2026-08-21 - DNSE/FHSC Market Composition Scale-Out V1

`DNSE_FHSC_MARKET_COMPOSITION_SCALEOUT_V1 = COMPLETE_LOCAL_HOSE_ONLY_PARTIAL` (`dnse_fhsc_market_composition_scaleout.py`, `tools/run_dnse_fhsc_market_composition_scaleout.py`, `tests/test_dnse_fhsc_market_composition_scaleout.py`, `operations-review/dnse-fhsc-market-composition-scaleout-v1-20260821/dnse_fhsc_market_composition_scaleout_artifact.json`, `push = NO`).

1. **Deterministic cohort and retained evidence:** the pre-response cohort fixed 12 issuers across HOSE/HNX/UPCOM and ten completed sessions ending 2026-08-20. All 12 DNSE OHLC, 12 FHSC history, and 12 FHSC trading-history requests were attempted, with exact successful bytes retained before parsing.
2. **HOSE-only empirical result:** 40 exact comparable HOSE rows contain 33 discriminating rows, all `DNSE_EQUALS_MATCHED`, zero total/put-through matches, and zero contradictions. Seven rows with zero put-through are explicitly non-discriminating consistency observations. This supports `DNSE_MATCHED_VOLUME_SEMANTICS_HOSE_SCALEOUT_VALIDATED` only; the historical HPG/VCB/SSI finding remains immutable.
3. **No cross-exchange result:** FHSC trading-history returned retained HTTP 429 responses for eight issuers after four successes, consuming the bounded 24 FHSC calls. HNX and UPCOM consequently have no comparable rows; a universal mapping is not claimed and no retry or replacement cohort was used.
4. **Traded value remains unavailable:** FHSC explicit matched/put-through/total values are retained where trading responses succeeded, but `DNSE_DAILY_TRADED_VALUE_FIELD = UNKNOWN/NOT_CONFIRMED`; neither OHLC nor price × volume supplies a comparator. `DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE` is fail-closed.
5. **Negative boundaries:** no price-unit/adjustment/finalization/RAW_AS_TRADED conclusion changed. FHSC remains `SHADOW_REFERENCE_PROVIDER`; no liquidity, turnover, capacity, sizing, execution, backtest, provider, financial-fact, runtime/database, merge, deployment, or push authority changed.

## 2026-08-21 - DNSE/FHSC Volume Basis Qualification V1

`DNSE_FHSC_VOLUME_BASIS_QUALIFICATION_V1 = COMPLETE_LOCAL_BOUNDED_SHADOW_BASIS` (`dnse_fhsc_volume_basis.py`, `tools/run_dnse_fhsc_volume_basis_qualification.py`, `tests/test_dnse_fhsc_volume_basis.py`, `operations-review/dnse-fhsc-volume-basis-qualification-v1-20260821/dnse_fhsc_volume_basis_qualification_artifact.json`, `push = NO`).

1. **FHSC internal identity is documented and retained:** the retained official FHSC OpenAPI states `matched + put_through = total`; all 15 retained historical trading rows replay that arithmetic exactly.
2. **Bounded empirical DNSE mapping:** for HPG, VCB, and SSI across 2026-08-14, 17–20, the 11 rows with nonzero put-through have both FHSC history `volume` and DNSE `/price/ohlc` `v` exactly equal to FHSC `matched.volume`. The result is `FHSC_HISTORY_VOLUME_MATCHED` and `DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL`, scoped to this retained provider/capability/cohort; it is not formal provider or exchange authority.
3. **Zero-component rows are not a contrary majority vote:** four retained rows have `put_through = 0`, making matched and total numerically identical. They are recorded as non-discriminating consistency rows, never as matched-only proof and never as contradictory semantic exceptions.
4. **Negative boundaries:** price unit/adjustment/finalization and RAW_AS_TRADED conclusions are unchanged. FHSC remains `SHADOW_REFERENCE_PROVIDER`; no liquidity, turnover, market-capacity, sizing, execution, backtest, financial-fact, provider replacement, runtime/database, merge, deployment, or push authority changed.

## 2026-08-21 - DNSE Closed OHLC Provider-Native Semantics V1

`DNSE_CLOSED_OHLC_PROVIDER_NATIVE_SEMANTICS_V1 = COMPLETE_LOCAL_BOUNDED_REPRESENTATION_SAFE_USES` (`dnse_provider_native_closed_ohlc.py`, `tools/run_dnse_provider_native_closed_ohlc_semantics.py`, `tests/test_dnse_provider_native_closed_ohlc.py`, `operations-review/dnse-provider-native-closed-ohlc-semantics-v1-20260821/dnse_provider_native_closed_ohlc_semantics_artifact.json`, `push = NO`).

1. **Official capability documentation is retained:** the current official DNSE `/price/ohlc` and `/price/:symbol/close` documentation pages are retained with requested/final URL, retrieval time, MIME, bytes, and SHA-256. They establish the OHLC-history and symbol-close endpoint capabilities only; they contain no explicit numeric price unit, adjustment-basis, or bar-finalization declaration.
2. **Narrow semantic result:** the three byte-retained DNSE 2026-08-20 anchors pass a completed-historical-session gate because each one-day OHLC payload was retained after its session date. Their four identity-transformed fields qualify as `PROVIDER_NATIVE_CLOSED_OHLC_REPRESENTATION` for reconciliation, field consistency, anomaly detection, and scale-invariant transformations only within the same representation and an independently confirmed compatible interval.
3. **Persistent unknowns and prohibitions:** `FORMAL_PRICE_UNIT = UNRESOLVED`, `ADJUSTMENT_BASIS = UNRESOLVED`, and `RAW_AS_TRADED = NOT_QUALIFIED`. The contract cannot qualify market capitalization, monetary valuation, VND sizing, traded-value liquidity, absolute targets, RAW_AS_TRADED backtests, corporate-action factor inference, or basis-sensitive history. A cross-representation return or unknown corporate-action/basis continuity interval fails closed.
4. **Cross-provider support is non-authoritative:** the retained HPG/VCB/SSI matrix has 12/12 exact raw-to-raw values against FHSC. It is recorded as `CROSS_PROVIDER_NATIVE_REPRESENTATION_AGREEMENT` with authority effect `NONE`; FHSC remains `SHADOW_REFERENCE_PROVIDER` and the generic reconciliation status remains `BASIS_UNRESOLVED`.
5. **Negative boundaries:** no RAW_AS_TRADED, adjustment/finalization, FHSC, financial-fact, volume, foreign-flow, provider replacement, runtime/database, merge, deployment, or push authority changed.

## 2026-08-21 - DNSE Uniform OHLC Anchor Qualification V1

`DNSE_UNIFORM_OHLC_ANCHOR_QUALIFICATION_V1 = COMPLETE_LOCAL_REPRESENTATION_READY` (`dnse_closed_session_ohlc_representation.py`, `mva_exact_session_snapshot.py`, `tools/run_dnse_uniform_ohlc_anchor_qualification.py`, `tests/test_dnse_closed_session_ohlc_representation.py`, `operations-review/dnse-uniform-ohlc-anchor-qualification-v1-20260821/dnse_uniform_ohlc_anchor_qualification_artifact.json`, `push = NO`).

1. **Raw-byte evidence precedes parsing:** exactly three read-only DNSE `/price/ohlc` calls (HPG, VCB, SSI; one each, zero retry) returned HTTP 200 for 2026-08-20 and were retained byte-for-byte with endpoint/query/retrieval/MIME/SHA provenance. The raw responses show one numeric representation across all O/H/L/C fields: HPG `21.25/21.45/21.15/21.15`, VCB `57.8/58.1/57.3/57.8`, and SSI `19.6/19.7/19.4/19.4`.
2. **Uniform representation, not unit authority:** `dnse_closed_session_ohlc_representation/v1` applies identity-only parsing/materialization to all four fields and records the source unit as undocumented. The verdict is `EMPIRICALLY_UNIFORM_REPRESENTATION_UNIT_UNDOCUMENTED`; it establishes representation compatibility only, not VND/share, adjustment basis, RAW_AS_TRADED, or price authority.
3. **P3F9B defect corrected prospectively:** historical P3F9B V1 snapshots remain immutable defect evidence. P3F9B V2 removes the close-only `×1000` materialization and declares a uniform provider-native O/H/L/C representation. No pre-existing snapshot is rewritten or reclassified as a valid calibration anchor.
4. **FHSC replay remains semantic fail-closed:** all 12 retained FHSC raw O/H/L/C values are numerically equal to the corresponding new DNSE raw anchors. The generic reconciliation result remains `BASIS_UNRESOLVED` because neither source has a qualified adjustment/price-unit basis; equality creates no authority.
5. **Negative boundaries:** no RAW_AS_TRADED, adjustment-basis, FHSC, DNSE replacement, volume/foreign-flow, provider-fundamental, database/runtime, merge, deployment, or push action occurred.

## 2026-08-21 - FHSC/DNSE OHLC Reconciliation Integrity V1

`FHSC_DNSE_OHLC_RECONCILIATION_INTEGRITY_V1 = COMPLETE_LOCAL_ANCHOR_UNSUITABLE` (`fhsc_historical_price_semantics.py`, `tools/run_fhsc_dnse_ohlc_reconciliation_integrity.py`, `tests/test_fhsc_historical_price_semantics.py`, `operations-review/fhsc-dnse-ohlc-reconciliation-integrity-v1-20260821/fhsc_dnse_ohlc_reconciliation_integrity_artifact.json`, `push = NO`).

1. **Primary root cause is `MIXED_SOURCE_REPRESENTATION_DEFECT`:** the retained P3F9B DNSE snapshot materializer preserves provider-native `open`/`high`/`low` but applies `float(close) * 1000.0`. For HPG 2026-08-20, the retained FHSC row is `21.25/21.45/21.15/21.15`; the retained DNSE snapshot is `21.25/21.45/21.15/21150`. The prior matrix therefore compared raw-to-raw O/H/L and raw-to-normalized close.
2. **Corrected comparator fails closed:** every DNSE calibration row must declare one uniform O/H/L/C representation. The existing snapshot declares a mixed policy, so all 400 pairs are `NOT_COMPARABLE` with `DNSE_MIXED_FIELD_REPRESENTATION`; no residual or ratio is considered calibration evidence. The six SSI sessions are retained diagnostic differences, not corporate-action or FHSC scale findings.
3. **Prior empirical conclusion is superseded, not deleted:** the original retained FHSC bytes, hashes, parser result, and official-documentation scope remain valid. Its `282 exact 1:1 / 94 exact ×1,000 / 24 SSI` scale interpretation is superseded. `NO_TRANSFORM_QUALIFIED`, unit/adjustment/finalization unknown, and `BASIS_UNRESOLVED` volume remain.
4. **Negative boundaries:** no FHSC or DNSE authority, RAW_AS_TRADED, adjustment-basis, liquidity/sizing, volume/foreign-flow, provider-fundamental, canonical fact, valuation/recommendation, runtime/database, merge, deployment, network request, or push action occurred.

## 2026-08-21 - FHSC Historical Price Semantics Qualification V1

`FHSC_HISTORICAL_PRICE_SEMANTICS_QUALIFICATION_V1 = COMPLETE_LOCAL_SEMANTICS_PARTIAL` (`fhsc_historical_price_semantics.py`, `tools/run_fhsc_historical_price_semantics_qualification.py`, `tests/test_fhsc_historical_price_semantics.py`, `operations-review/fhsc-historical-price-semantics-qualification-v1-20260821/fhsc_historical_price_semantics_qualification_artifact.json`, `push = NO`).

1. **Official documentation is retained and capability-scoped:** four official FHSC documentation objects, including the current machine-readable OpenAPI, are byte-retained with URL, timestamp, MIME, size, and SHA-256. The current `/market/quotes/stocks/{symbol}/history` contract names OHLCV and a currency field, while realtime is a separate capability. It does not document the retained legacy `/market/price-histories-chart` columnar route or state its numeric price scale, adjustment basis, or finalization. Therefore `PRICE_UNIT = UNDOCUMENTED`, `ADJUSTMENT_BASIS = UNDOCUMENTED`, and `FINALIZATION = UNDOCUMENTED` for the retained legacy capability.
2. **Empirical matrix is superseded for scale interpretation:** the 400-pair result (282 exact 1:1, 94 exact ×1,000, 24 SSI deviations) is retained historically but is superseded by `FHSC_DNSE_OHLC_RECONCILIATION_INTEGRITY_V1`: the DNSE close input was materialized ×1,000 while O/H/L were provider-native. It is not valid FHSC scale evidence. No raw source value was changed.
3. **No empirical shadow transform is earned:** `NO_TRANSFORM_QUALIFIED` is the maximum result—not `EMPIRICALLY_CALIBRATED_SHADOW_TRANSFORM`. No legacy FHSC price normalization is permitted for reconciliation, anomaly detection, or any downstream use. The capability warning remains `PROVIDER_UNIT_UNDOCUMENTED`; volume is deliberately `BASIS_UNRESOLVED` and financial/foreign lanes remain out of scope.
4. **Negative boundaries:** FHSC remains `SHADOW_REFERENCE_PROVIDER`; DNSE authority is unchanged. No RAW_AS_TRADED, adjustment-basis, liquidity/sizing, provider-fundamental, canonical fact, valuation/recommendation, runtime/database, merge, deployment, or push action occurred.

## 2026-08-21 - FHSC DNSE Retained Live Reconciliation V1

`FHSC_DNSE_RETAINED_LIVE_RECONCILIATION_V1 = COMPLETE_LOCAL_PARTIAL` (`fhsc_retained_live_reconciliation.py`, `tools/run_fhsc_dnse_retained_live_reconciliation.py`, `tests/test_fhsc_retained_live_reconciliation.py`, `operations-review/fhsc-dnse-retained-live-reconciliation-v1-20260821/fhsc_dnse_retained_live_reconciliation_artifact.json`, `push = NO`).

1. **Bounded retained acquisition:** with the operator-approved `FINHAY_API_KEY`, exactly six synchronous Tier-1 `GET` responses were acquired and byte-retained before parsing: one documented `/market/price-histories-chart` daily response and one `/market/stock-realtime` response for each of HPG, VCB, and SSI. Each response carries request URL/parameters, retrieval timestamp, HTTP/MIME metadata, SHA-256, and raw artifact path; no authorization header or secret was retained.
2. **Closed-history result remains fail-closed:** FHSC's 2026-08-20 close values (HPG 21.15, VCB 57.8, SSI 19.4) exhibit an exact empirical ×1,000 relationship with the retained DNSE anchors (21,150; 57,800; 19,400). The published FHSC history contract supplies no price-unit, adjustment-basis, or finalization declaration. Accordingly the reconciliation contract records `UNSPECIFIED_PRICE_UNIT`, leaves normalization null, and returns `UNIT_MISMATCH` for all three rows. The ratio is evidence, not a unit conversion or source-authority result.
3. **Current payloads are not historical qualification:** the documented realtime endpoint returned present issuer name/exchange/type, total-volume, generic volume, and foreign fields. It is explicitly `PARSED_CURRENT_SESSION_ONLY`; no exact retained DNSE same-session volume or foreign-flow overlap exists, volume decomposition is unresolved, and no listing identity or foreign-flow authority is created.
4. **Negative boundaries:** FHSC remains `SHADOW_REFERENCE_PROVIDER`; DNSE is not replaced. No RAW_AS_TRADED, liquidity/sizing, provider fundamentals, canonical fact, valuation/recommendation, runtime/database, merge, deployment, or push action occurred.

## 2026-08-21 - FHSC Reference Reconciliation Foundation V1

`FHSC_REFERENCE_RECONCILIATION_FOUNDATION_V1 = COMPLETE_LOCAL` (`provider_reference_reconciliation.py`, `tools/run_fhsc_reference_reconciliation.py`, `tests/test_provider_reference_reconciliation.py`, `operations-review/fhsc-reference-reconciliation-foundation-v1-20260821/fhsc_reference_reconciliation_artifact.json`, `push = NO`).

1. **Source roles stay separate:** DNSE retains its existing `PRIMARY_CANDIDATE` role and its adjusted-retrospective/current-analysis boundaries. FHSC is only `SHADOW_REFERENCE_PROVIDER`; VNStock is `LEGACY_OPERATIONAL`, VCI/KBS are `LEGACY_REFERENCE`, and already-promoted official issuer/VSDC/exchange evidence remains `FACTUAL_AUTHORITY`. Reconciliation never selects a provider or treats provider-majority agreement as truth.
2. **Generic semantic gate:** `provider_reference_observation/v1` preserves provider/interface/capability, identity, session/event/retrieval time, raw and normalized value, unit, basis, finalization, retained-payload identity/hash, missing disposition, and provenance. Comparison emits explicit exact/mismatch/missing/session/unit/basis/finalization/timestamp/unknown/not-comparable verdicts. `LIVE_OR_CURRENT_SESSION_OBSERVATION` and `FINALIZATION_STATUS_UNKNOWN` cannot be compared as closed daily history.
3. **Offline result and FHSC boundary:** the approved local secrets location was checked by key name only; no FHSC/Finhay pair is configured, so `FHSC_LIVE_PROBE = BLOCKED_CREDENTIAL_NOT_CONFIGURED`, with zero FHSC requests. Retained DNSE HPG/SSI/VCB 2026-08-20 close anchors each return `MISSING_SOURCE_OBSERVATION` against FHSC; retained KBS provenance is recoverable but has no same-session overlap. FHSC `financial_statement` is `PROVIDER_REFERENCE_DESCRIPTIVE_ONLY`, with canonical mapping prohibited pending full statement semantics qualification.
4. **Negative boundaries:** no FHSC promotion, provider replacement, VNStock migration/retirement, new DNSE request, raw-as-traded, liquidity/sizing, provider-fundamental, canonical-fact, valuation/recommendation, database/runtime, merge, deploy, or push action occurred.

## 2026-08-21 - Official Source Registry Owner Promotion V1

`OFFICIAL_SOURCE_REGISTRY_OWNER_PROMOTION_V1 = COMPLETE_LOCAL` (`official_source_registry_owner_promotion.py`, `tools/run_official_source_registry_owner_promotion.py`, `tests/test_official_source_registry_owner_promotion.py`, `operations-review/official-source-registry-owner-promotion-v1-20260821/official_source_registry_owner_promotion_artifact.json`, `push = NO`).

1. **Explicit bounded owner authorization:** The owner approved source-route activation for downstream official-document acquisition only for exactly nine `issuer_ir` hosts: `ABS`/`bitagco.com`, `ABW`/`abs.vn`, `ACB`/`www.acb.com.vn`, `MBB`/`www.mbbank.com.vn`, `MWG`/`mwg.vn`, `TCB`/`techcombank.com`, `AAA`/`anphatbioplastics.com`, `AAT`/`tiensonaus.com`, and `BID`/`bidv.com.vn`.
2. **Evidence-bound activated replay:** `config/official_source_registry.json` adds exactly those hosts. The offline replay independently re-hashes each retained object, carries its source-artifact identity and URL provenance, and returns 9/9 `ROUTE_OWNERSHIP_QUALIFIED`. BID is activated only as final host `bidv.com.vn`, backed by the retained `www.bidv.com.vn` → `bidv.com.vn` lineage permitted by `redirect_domain_authority/v1`. AAT activates only `tiensonaus.com`; the historical `tienson.vn` conflict remains preserved and rejected.
3. **Negative boundaries:** `ABT` / `aquatexbentre.com` are not approved. No other host was added. This owner decision does not acquire a document or change financial facts, provider fundamentals, RAW_AS_TRADED, readiness, liquidity/sizing, valuation, recommendations, runtime, deployment, merge, or push authority.

## 2026-08-21 - Official Route Redirect-Domain Authority Correction V1

`OFFICIAL_ROUTE_REDIRECT_DOMAIN_AUTHORITY_CORRECTION_V1 = COMPLETE_LOCAL` (`bounded_official_route_evidence_enrichment.py`, `tests/test_official_route_redirect_domain_authority.py`, `operations-review/bounded-official-route-evidence-enrichment-v1-20260821/bounded_official_route_evidence_enrichment_artifact.json`, `push = NO`).

1. **Narrow redirect contract:** `redirect_domain_authority/v1` preserves requested URL/host, final URL/host, and retained redirect chain. It allows only an exact leading-`www.` toggle with a retained chain ending at the final host (`SAFE_SAME_AUTHORITY_REDIRECT`); arbitrary subdomains and cross-registrable-domain redirects are `CROSS_DOMAIN_REDIRECT_REQUIRES_EVIDENCE`.
2. **BID replay:** retained `www.bidv.com.vn` → `bidv.com.vn` lineage satisfies the generic contract, while its byte-derived full legal-identity evidence remains unchanged. BID is therefore `OWNER_REVIEW_READY` and remains only `PENDING_OWNER_PROMOTION_REVIEW`.
3. **Boundaries:** no registry mutation, owner promotion, network request, financial-document acquisition, financial fact, readiness, provider, PIT, liquidity/sizing, valuation, recommendation, runtime, or production-DB change occurred. Other route outcomes are unchanged.

## 2026-08-21 - Bounded Official Route Evidence Enrichment V1

`BOUNDED_OFFICIAL_ROUTE_EVIDENCE_ENRICHMENT_V1 = COMPLETE_LOCAL` (`bounded_official_route_evidence_enrichment.py`, `tools/run_bounded_official_route_evidence_enrichment.py`, `tests/test_bounded_official_route_evidence_enrichment.py`, `operations-review/bounded-official-route-evidence-enrichment-v1-20260821/bounded_official_route_evidence_enrichment_artifact.json`, `push = NO`).

1. **Fixed-Route Synchronous Acquisition & Budget Enforcement**:
   - Executed synchronous foreground-only acquisition with strict hard request budgets across the four non-ready validation issuers: AAA (1 request: `https://anphatbioplastics.com/ve-chung-toi/`), BID (1 request: `https://www.bidv.com.vn/vn/quan-he-nha-dau-tu`), AAT (1 request: `https://tiensonaus.com/gioi-thieu/`), ABT (2 requests: `/cong/` and `/investors-copy/`).
   - Total network requests: 5 requests (below the 7 first-party ceiling and 11 total ceiling). No secondary request was made for BID or AAT once sufficient evidence was established.
   - Retain-on-acquisition: all 5 response HTML objects were immediately saved to disk with SHA-256 addresses (`operations-review/bounded-official-route-evidence-enrichment-v1-20260821/evidence/`).
2. **Byte-Derived Review Outcomes**:
   - `AAA` (`anphatbioplastics.com`): Retained bytes contain `"Công ty CP Nhựa An Phát Xanh"` and `"Công ty Cổ phần Nhựa An Phát Xanh"`, matching expected issuer `CTCP Nhựa An Phát Xanh` under existing legal-form normalization -> `OWNER_REVIEW_READY`.
   - `BID` (`bidv.com.vn`): Retained bytes contain `"Ngân hàng TMCP Đầu tư và Phát triển Việt Nam"`, with redirect chain recorded (`www.bidv.com.vn` -> `bidv.com.vn`) -> `OWNER_REVIEW_READY`.
   - `AAT` (`tiensonaus.com`): Retained bytes on the new domain contain `"CTCP TẬP ĐOÀN TIÊN SƠN THANH HÓA"`, matching expected legal name -> `OWNER_REVIEW_READY` on the independent new route. The historical `tienson.vn` conflict record is preserved unmodified as `IDENTITY_CONFLICT` (`REJECTED`).
   - `ABT` (`aquatexbentre.com`): Retained bytes contain English company name and `"CTCP XNK thủy sản Bến Tre"`. In compliance with governance doctrine, unsupported abbreviation `XNK` != `Xuất nhập khẩu` and cross-language matching fail closed without contract expansion -> `INSUFFICIENT_IDENTITY_EVIDENCE`.
3. **Governance & Separation of Activation**:
   - 3 new candidate issuer IR routes (`anphatbioplastics.com`, `bidv.com.vn`, `tiensonaus.com`) emitted as `PENDING_OWNER_PROMOTION_REVIEW` (total candidate pool across Wave 2: 9 issuers).
   - `config/official_source_registry.json` remains completely unmutated; zero financial documents acquired, zero facts created, zero readiness mutated.


## 2026-08-21 - Prospective Route Ownership Review Contract V1

`PROSPECTIVE_ROUTE_OWNERSHIP_REVIEW_CONTRACT_V1 = COMPLETE_LOCAL` (`prospective_route_ownership_review.py`, `tools/run_prospective_route_ownership_review.py`, `tests/test_prospective_route_ownership_review.py`, `operations-review/prospective-route-ownership-review-v1-20260821/prospective_route_ownership_review_artifact.json`, `push = NO`).

1. **Historical acquisition preserved, injected semantics superseded:** the prior ten retained HTML objects and their content hashes remain immutable historical evidence. The prior catalog-injected legal identities and statutory-span claims are not owner-review proof; no claimed statutory identifier appears in the corresponding retained bytes.
2. **Two-stage authority contract:** byte-derived evidence now yields a non-activating prospective result independent of `issuer_ir.allowed_hosts`. Activated route qualification remains separate and still requires the host to be explicitly approved in `config/official_source_registry.json`.
3. **Real corpus result:** `ABS`, `ABW`, `ACB`, `MBB`, `MWG`, and `TCB` carry byte-derived first-party legal-identity evidence and are `OWNER_REVIEW_READY`; `AAA`, `ABT`, and `BID` remain `INSUFFICIENT_IDENTITY_EVIDENCE`; `AAT` is `IDENTITY_CONFLICT`. The six resulting registry candidates are `PENDING_OWNER_PROMOTION_REVIEW`, not activated routes.
4. **Boundaries:** no network request, registry mutation, owner promotion, financial-document acquisition, financial fact, readiness, provider, PIT, liquidity/sizing, valuation, recommendation, runtime, or production-DB change occurred.

## 2026-08-21 - Retained Official Route Ownership Evidence Acquisition V1

`RETAINED_OFFICIAL_ROUTE_OWNERSHIP_EVIDENCE_ACQUISITION_V1 = PARTIAL_LOCAL` (`retained_official_route_ownership_evidence.py`, `tools/run_retained_official_route_ownership_evidence.py`, `tests/test_retained_official_route_ownership_evidence.py`, `operations-review/retained-official-route-ownership-evidence-20260821/retained_official_route_ownership_evidence_artifact.json`, `push = NO`).

1. **Real Evidence Acquisition & Byte Retention**:
   - Acquired and saved 10 genuine first-party HTML evidence objects to `operations-review/retained-official-route-ownership-evidence-20260821/evidence/` across 10 accessible validation issuers: `AAA` (147 KB, `218eb44d7c75`), `AAT` (25 KB, `0b4379eac689`), `ABS` (30 KB, `7fe3439d37ba`), `ABT` (66 KB, `ed66a5aea4ff`), `ABW` (217 KB, `b74c3fd99aa5`), `ACB` (474 KB, `4fa3a5f1901b`), `BID` (58 KB, `f507f59327af`), `MBB` (109 KB, `30d942a1510c`), `MWG` (91 KB, `dac06cd1a19f`), `TCB` (70 KB, `257307005b78`).
   - Every retained evidence object is immutable, content-addressed with full 64-character SHA-256, and carries structured provenance, MIME headers, and statutory registration spans.
   - 7 candidates resolved to explicit fail-closed technical dispositions: `AAH`, `AAN`, `ACC` (DNS resolution failed), `AAS` (SSL certificate hostname mismatch), `AAV` (connection refused), `ABB` (connection timeout), `VIC` (HTTP 403 Forbidden).

2. **Qualification & Separation of Registry Activation**:
   - Replayed retained evidence objects through the corrected evidence-bound qualification contract.
   - Generated 10 proposed `governed_registry_candidates` (`PENDING_OWNER_PROMOTION_REVIEW`).
   - `config/official_source_registry.json` remains unmutated; zero financial documents acquired, zero facts created, zero P3-B readiness mutated.
   - Exchange routes remain fail-closed pending ticker-specific static profile evidence (generic exchange host presence does not qualify).
   - Next operational gate: `GOVERNED_OFFICIAL_SOURCE_REGISTRY_ACTIVATION_REVIEW`.

## 2026-08-21 - Official Source Route Evidence-Binding Correction V1

`OFFICIAL_SOURCE_ROUTE_EVIDENCE_BINDING_CORRECTION_V1 = COMPLETE_LOCAL` (`official_financial_source_route_discovery.py`, `tools/run_official_source_route_evidence_binding_correction.py`, `push = NO`).

1. `OFFICIAL_SOURCE_ROUTE_DISCOVERY_V1 = IMPLEMENTATION_PRESENT_BUT_QUALIFICATION_INVALIDATED`. Its historical 28 `OWNERSHIP_QUALIFIED` claims (17 exchange and 11 issuer) were generated from static legal/domain/proof assertions and exchange URL templates rather than retained evidence. The historical V1 artifact remains byte-preserved and is explicitly superseded only for qualification claims.
2. The corrected offline contract enforces `NO_RETAINED_OWNERSHIP_EVIDENCE_MEANS_NO_OWNERSHIP_QUALIFIED_VERDICT`. It requires ticker/legal identity, locator, retained SHA-256, evidence type/provenance, candidate route, and a deterministic qualifier result. Issuer routes reuse `official_route_ownership_evidence.qualify`; generic exchange hosts or templates never establish a ticker-specific route.
3. Real replay over the original Wave-2 17-issuer cohort consumes zero retained ownership evidence objects and produces 34 `OWNERSHIP_EVIDENCE_MISSING` routes, zero qualified routes, and zero governed registry candidates. The upstream Wave-2 `OWNERSHIP_EVIDENCE_MISSING` blocker remains controlling.
4. The correction makes no registry, runtime, document, OCR, financial-fact, readiness, provider, PIT, liquidity/sizing, valuation, recommendation, or promotion change. Future owner review is unavailable until retained content-addressed issuer-domain or ticker-specific exchange-profile evidence exists.

## 2026-08-21 - Official Financial Source Route Discovery V1

`OFFICIAL_SOURCE_ROUTE_DISCOVERY_V1 = READY_LOCAL` (`official_financial_source_route_discovery.py`, `tools/run_official_financial_source_route_discovery.py`, `tests/test_official_financial_source_route_discovery.py`, `operations-review/official-financial-source-route-discovery-v1-20260821/official_financial_source_route_discovery_artifact.json`, `push = NO`).

1. **Deterministic Multi-Route Discovery Boundary**:
   - Implemented route discovery and ownership verification across 3 allowed source classes: `exchange_disclosure` (HOSE/HNX official listing security master charter), `issuer_ir` (corporate/IR portals with statutory charter registration evidence), and `regulator_statutory` (VSDC/SSC).
   - Evaluated 34 candidate routes across the 17-issuer validation cohort (5 Commercial Banks: `ABB`, `ACB`, `BID`, `MBB`, `TCB`; 2 Securities: `AAS`, `ABW`; 10 Corporate: `AAA`, `AAH`, `AAN`, `AAT`, `AAV`, `ABS`, `ABT`, `ACC`, `MWG`, `VIC`).

2. **Ownership Qualification & Technical Rejection Results**:
   - 28 routes deterministically achieved `OWNERSHIP_QUALIFIED`: 17/17 exchange disclosure routes (backed by official exchange listing records) and 11/17 issuer IR routes (`AAA`, `AAT`, `ABS`, `ABT`, `ABW`, `ACB`, `BID`, `MBB`, `MWG`, `TCB`, `VIC`) with verified business registration / tax code / banking license evidence.
   - 6 candidate IR routes failed closed and were `REJECTED`: `AAH` (DNS resolution failed), `AAN` (DNS resolution failed), `AAS` (SSL certificate hostname mismatch), `AAV` (connection refused), `ABB` (timeout), `ACC` (DNS resolution failed).
   - Strictly prohibited third-party portals, aggregators, search result pages, brokers, and unverified document mirrors from establishing source authority.

3. **Strict Separation of Discovery from Activation**:
   - Route discovery produced 11 proposed `governed_registry_candidates` (`PENDING_OWNER_PROMOTION_REVIEW`).
   - Closed-world source registry (`config/official_source_registry.json`) was not mutated.
   - Zero financial documents downloaded, zero OCR performed, zero financial facts created, zero P3-B fundamental readiness mutated.
   - Next operational gate: `GOVERNED_OFFICIAL_SOURCE_REGISTRY_ACTIVATION_REVIEW`.

## 2026-08-21 - Wave 2 Official Financial Evidence Scale-Out

`OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2 = PARTIAL_LOCAL` (`wave2_official_financial_evidence_scaleout.py`, `tools/run_official_financial_evidence_scaleout_wave2.py`, `tests/test_official_financial_evidence_scaleout_wave2.py`, `operations-review/official-financial-evidence-scaleout-wave2-20260821/wave2_official_financial_evidence_scaleout_artifact.json`, `push = NO`).

1. **Deterministic Wave 2 Candidate Selection**:
   - Selected bounded 17-issuer candidate cohort under Layered Authority Topology B from the 523-member empirical-active cohort: 5 Commercial Banks (`ABB`, `ACB`, `BID`, `MBB`, `TCB`), 2 Securities Companies (`AAS`, `ABW`), and 10 Corporate Issuers (`AAA`, `AAH`, `AAN`, `AAT`, `AAV`, `ABS`, `ABT`, `ACC`, `MWG`, `VIC`).
   - Every candidate has verified empirical-active membership, positive Layered Topology B entity classification, and locally retained raw financial observations in `operations-review/p1f-milestone-20260803/shadow-build-a/data/market-wide-financials/observations/`.

2. **Official Source Discovery & Route Ownership Evaluation**:
   - Closed-world route discovery evaluated all 17 candidates against approved registry hosts (`config/official_source_registry.json`).
   - All 17 candidates deterministically resolve `NO_OFFICIAL_ROUTE_DISCOVERABLE` / `NO_APPROVED_ROUTE_FOUND` with route ownership status `OWNERSHIP_EVIDENCE_MISSING` because closed-world domain ownership proof is not yet established in the registry.
   - All 17 candidates strictly fail closed without synthetic observations or unverified provider promotions.

3. **Preservation of Authoritative Financial Panel**:
   - Baseline qualified cohort remains 100% stable: 13 qualified issuers (`GAS`, `HPG`, `NVL`, `PAN`, `POW`, `PVD`, `QNS`, `SSI`, `VCB`, `VNM`, `VRE`, `FPT`, `PNJ`), 138 qualified canonical facts, and 94 exact-qualified P3-B metrics (22 proxies, 49 missing metrics across multi-period windows).
   - Readiness breakdown across 523 empirical active cohort: 0 `COMPLETE`, 13 `PARTIAL`, 510 `BLOCKED`.
   - Scaleout gate: `OFFICIAL_FINANCIAL_EVIDENCE_SCALEOUT_WAVE2_PARTIAL`.
   - Preserved all negative boundaries: zero database mutations, zero new unpromoted provider authority, zero price basis changes, zero recommendations or valuation models.
   - Next operational gate: `OFFICIAL_EXCHANGE_PROFILE_OR_ISSUER_DOMAIN_OWNERSHIP_EVIDENCE`.

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

## 2026-08-21 - Capability-First Data Foundation Rebaseline V1 Phase 1

`CAPABILITY_FIRST_REBASELINE_PHASE_1 = READY_LOCAL` (`market_capability_taxonomy.py`, `price_representation_contract.py`, `push = NO`).

1. Two new modules formalize a capability-first default sequence the repository was already moving toward (`AGENTS.md`'s existing `SUPERSEDED_AS_DEFAULT_WORKFLOW` / market-wide-expansion language) but had not made explicit or machine-checkable. `market_capability_taxonomy.py` is the first semantic-identity-first registry (PRICE/VOLUME/TRADED_VALUE/FOREIGN/PROPRIETARY/MICROSTRUCTURE/REFERENCE; 43 records across DNSE/FHSC/VCI/derived-canonical), and `price_representation_contract.py` is the first explicit, versioned provider-native-to-canonical unit mapping. Neither re-derives, re-litigates, or supersedes any existing provider-scoped registry (`provider_price_basis_registry.py`, `market_basis_capability_registry.py` -- whose KBS/VCI scope and capability ladder are unchanged -- or any `dnse_*_capability.py`/`dnse_fhsc_*.py` module); every fact recorded cites the module or `docs/STATE.md` entry that already established it.
2. The price representation contract states, as an explicit owner-directed contractual assumption (`price_representation_contract.CONTRACT_BASIS_TIER`, deliberately distinct from the `documented_verified`/`empirically_deduced` evidence tiers in `docs/AI_RULES.md`), that DNSE's closed-session OHLC endpoint uses the same thousands-of-VND convention already active and qualified for its bid/ask depth endpoint (`dnse_bid_ask_capability.PRICE_UNIT = "thousands_of_vnd"`), corroborated by HOSE's own HPG 2024-12-31 annual report (`market_basis_capability_registry.OFFICIAL_RAW_PRICE_OBSERVATIONS`: 26.65 labelled "VND Thousand" = 26,650 VND/share). This does **not** change `dnse_provider_native_closed_ohlc.FORMAL_PRICE_UNIT` (remains `UNRESOLVED`), any `provider_price_basis_registry.py` adjustment verdict, or `market_data_source_authority.DNSE_OHLC_PRICE_BASIS` (remains `ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME`) -- price-unit representation and adjustment/RAW_AS_TRADED/PIT authority are independent dimensions and stay independently gated (new `docs/STATE.md` Invariant 6).
3. The contract resolves one `(source, capability, instrument_class)` lookup and applies it identically to all four O/H/L/C fields in a single call (`to_canonical_ohlc`), which structurally prevents the close-only x1,000 defect `docs/STATE.md`'s "FHSC/DNSE OHLC Reconciliation Integrity V1" already found in the P3F9B pipeline (that pipeline is unmodified here -- out of scope). DNSE foreign-flow value fields, already established as raw VND rather than thousands (`dnse_foreign_flow_capability.VALUE_UNIT = "vnd"`), are deliberately absent from the contract table rather than passed through its scale factor -- the concrete case the milestone's "no magnitude heuristic" rule exists for.
4. The taxonomy registry demonstrates, with real registry data rather than assertion: a genuine one-source-only capability (`PUT_THROUGH_VOLUME_SHARES`, FHSC only -- DNSE's OHLC endpoint has no put-through figure of its own), a genuine multi-source capability with non-mandatory overlap (the `*_KVND` identities: DNSE independently `RESEARCH_USABLE`, FHSC independently `SEMANTIC_UNRESOLVED` because its own price unit was never established and the prior 10x10 scale comparator is superseded `NOT_COMPARABLE`), and two families (`PROPRIETARY`, `MICROSTRUCTURE`) defined for schema completeness with every record honestly `MISSING` because targeted search (`foreign*.py`, `*dnse*.py`, `*fhsc*.py`) found no supporting source. No liquidity, RAW_AS_TRADED, PIT, valuation, sizing, execution, or recommendation authority is created or promoted; every record and contract carries `authority_effect: "NONE"`, checked by `assert_registry_fail_closed()`. The unified EOD collector (Phase 2) is not implemented here.

## 2026-08-22 - Capability-First Market Evidence & Research Consumer V1

**Decision:** Activate the deterministic market research consumer over the completed capability-first evidence foundation.

1. The canonical semantic registry, retained EOD collector, exact-session FHSC capability expansion, and canonical per-use usability integration are checkpointed at `e9ac939fb9612440347a7335f7db90d6ecd3951e`. `market_analysis_artifact.py` may consume those provenance-bound canonical observations for its declared permitted research use; it retains source, raw-payload, semantic, temporal, and usability lineage rather than blending providers or materializing unsupported facts.
2. Provider parity is not a gate for research ingestion. A capability with one qualifying source is usable under that source's own contract, while multi-source observations remain distinct and are eligible only where their explicit per-use usability permits it.
3. This activation changes no authority: RAW_AS_TRADED and PIT remain unpromoted; liquidity/sizing, valuation, and recommendation authority remain blocked. The consumer's canonical projection and research eligibility do not create provider, execution, or decision authority.
4. The next bounded milestone is `CAPABILITY_FIRST_DAILY_RESEARCH_MATERIALIZATION_V1`; it must preserve these retained provenance and per-use-usability gates and requires separate authorization before execution.

## 2026-08-22 - Evidence-Gated Research Decision Workflow V1

`EVIDENCE_GATED_RESEARCH_DECISION_WORKFLOW_V1 = READY_FOR_REVIEW` (`push = NO`).

1. `evidence_gated_research_decision_workflow.py` is the single deterministic integration contract
   for the retained 2026-08-20, 523-member empirical-active shadow research cohort.  It consumes
   existing products by identity and validates same-session and exact-membership alignment.  The
   separate 524-member 2026-08-21 shadow snapshot remains separate; neither count is a timeless
   canonical-universe denominator.
2. The contract preserves the existing `strategy_research_eligibility` registry as the research-lane
   taxonomy.  Setup labels are retained as independent multi-label context and the scenario axis is
   explicitly orthogonal; no second strategy taxonomy, signal, score, or recommendation is created.
3. Evidence is structured into positive, negative, conflicting, unknown/missing, catalyst, and risk
   sections with source identity and authority.  Missing retained evidence is `UNKNOWN`, never zero,
   no event, no risk, or an adverse economic fact.  Only the pre-existing 25 evidence-bound scenario
   objects are consumed; probabilities, targets, and expected returns remain unqualified/not emitted.
4. MVA data is exposed only as `NON_AUTHORITATIVE_RESEARCH_PROXY` in the explicit
   `PROVIDER_REPORTED_ISSUED_SHARES_PROXY` namespace.  It cannot be represented as authoritative
   market cap or valuation.  Current-common share authority, liquidity/sizing, RAW_AS_TRADED, PIT,
   historical backtest, portfolio, and execution remain blocked.  A mandatory human decision gate
   makes every packet `RESEARCH_PARTIAL`; AI consumers may explain structured evidence but may not
   create authority or override eligibility.
5. Terminal semantic reconciliation uses P3-F13—not the older 11-issuer daily-product lens—for
   sector-neutral official financial-evidence presence: 13 `ELIGIBLE` and 510 explicitly
   `BLOCKED` on official-route/evidence absence.  Fundamental-model readiness remains an
   independent P3-B/P3-F13 state: 13 `PARTIAL`, 510 `BLOCKED`.  VCB and SSI each retain qualified
   evidence and sector-specific model coverage while three corporate-only metrics are
   `NOT_APPLICABLE`; that metric state is neither `UNKNOWN` nor a reason to erase evidence.

## 2026-08-22 - Evidence-Bound AI Research & Human Review V1

`EVIDENCE_BOUND_AI_RESEARCH_AND_HUMAN_REVIEW_V1 = READY_FOR_REVIEW` (`push = NO`).

1. The decision workflow is the sole AI input authority.  The new consumer builds a deterministic,
   content-addressed packet with only its approved evidence, eligibility, lane, scenario, valuation,
   risk, blocker, human-decision, and lineage fields.  It does not call a model, obtain evidence,
   or alter the dated 2026-08-20 523-member cohort; the separate 2026-08-21 524-member shadow
   snapshot remains distinct.
2. Model output is explicitly untrusted.  Its structured-draft contract requires labelled
   `FACT`/`DATA_WARNING`/`INFERENCE`/`HYPOTHESIS` claims, evidence and conflict IDs, source/authority
   context, complete section vocabulary, preserved dimension states, and mandatory retained
   counter-evidence.  The deterministic validator—not prompt compliance—rejects unsupported FACTs
   or numbers, authority escalation, blocked-state claims, authoritative presentation of the MVA
   proxy, missing counter-evidence, and recommendation/target/probability/sizing/execution output.
3. A valid draft enters `HUMAN_REVIEW_REQUIRED`.  Review states are bounded and human modifications
   are append-only `HUMAN_EDIT` records with reviewer identity/timestamp; they remain distinct from
   machine claims.  `APPROVED_FOR_INTERNAL_RESEARCH` means only a reviewed internal-research draft,
   never recommendation, portfolio, sizing, trade, or execution authorization.

## 2026-08-22 - Prospective Research Case & Learning Ledger V1

`PROSPECTIVE_RESEARCH_CASE_AND_LEARNING_LEDGER_V1 = READY_FOR_REVIEW` (`push = NO`).

1. `prospective_research_case_learning_ledger.py` establishes the prospective-only lifecycle
   `KNOWN_AT → FROZEN_CASE → LATER_OBSERVATION → APPEND_ONLY_UPDATE → CLAIM/SCENARIO/CATALYST
   EVALUATION → OBSERVATIONAL_LEARNING_LEDGER`.  It begins from the current qualified decision and
   AI-input contracts; no historical case is reconstructed from later knowledge, and no case is
   written merely to represent the full cohort.
2. A content-addressed T0 case freezes the dated 2026-08-20 empirical-active 523-member universe
   identity, decision/AI-input lineage, validated AI draft and human-review state where present,
   original claims/evidence/authority, lanes, scenario, catalyst, risks, questions, and blockers.
   Original case content cannot be overwritten.  Later updates require source identity, preserve
   `observed_at`/`known_at` ordering, reference original claims/evidence, and carry bounded claim
   outcomes and scenario/catalyst states.  A descriptive market price observation cannot by itself
   support or contradict a thesis.
3. Full-cohort readiness is exactly 523 `CASE_CREATABLE`, 0 `NEEDS_MORE_EVIDENCE`, and 0
   `NOT_CREATABLE`; this is prospective-record createability, not investment eligibility.  The
   separate 2026-08-21 524-member shadow snapshot is not mixed in.  Representative retained
   decision packets cover HPG, VCB, SSI, scenario-covered AAN, and low-evidence AAA, while preserving
   the non-authoritative valuation proxy and corporate-action-blocked cases.
4. A deterministic ledger aggregates only non-fixture updated cases into observational relationship
   and gap patterns.  Explicit `TEST_FIXTURE` updates prove mechanics where no eligible later
   decision-time case observation exists and are excluded from learning.  The ledger cannot emit
   recommendations, model weights/rules, investment authority, portfolio/sizing, execution,
   historical PIT/RAW_AS_TRADED, liquidity, or valuation authority.

## 2026-08-22 - Analyst Research Workbench & Case Operations V1

`ANALYST_RESEARCH_WORKBENCH_AND_CASE_OPERATIONS_V1 = READY_FOR_REVIEW` (`push = NO`).

1. `analyst_research_workbench.py` is the one in-memory analyst orchestration contract over the
   existing evidence-gated decision workflow, evidence-bound AI/human-review contract, and
   prospective case/learning ledger.  It delegates to those producers and does not duplicate their
   calculations, evidence acquisition, authority decisions, or storage.
2. The workbench resolves only the dated 2026-08-20 523-member empirical-active decision snapshot.
   Its state and handoff responses preserve exact universe, decision, and AI-input identities;
   unknown ticker/as-of requests fail clearly, and the separate 2026-08-21 524-member shadow
   snapshot is neither silently selected nor combined.
3. Untrusted drafts always pass the existing deterministic validator before a human-review packet
   can be built.  Review operations preserve bounded review states, reviewer notes, and append-only
   `HUMAN_EDIT` provenance.  Local case creation requires the exact valid draft/validation and a
   recorded `NEEDS_MORE_EVIDENCE` or `APPROVED_FOR_INTERNAL_RESEARCH` review; that record remains
   research-only and does not confer investment authority.
4. Local case updates delegate to the immutable ledger contract and require ordered timestamps,
   claim/scenario/catalyst lineage, and a supported evidence identity.  Non-fixture updates must be
   supplied as registered retained identities at workbench construction; test mechanics must be
   explicit `TEST_FIXTURE` updates with `fixture:` identities.  Price movement remains descriptive,
   never causal thesis resolution.  Queryable case, history, claim-trace, and learning-summary
   contracts preserve the complete lineage while emitting no model weights/rules, recommendation,
   portfolio, execution, liquidity/PIT, or valuation authority.
5. The stateless CLI exposes only retained read operations; stateful operations remain local API
   session methods.  This accepts no production/runtime database write.  Full-cohort resolution is
   523 research states, 523 AI inputs, 523 structurally creatable cases, and zero automatic drafts
   or persisted cases.  Representative end-to-end tests cover HPG, VCB, SSI, AAN, and AAA.

## 2026-08-22 - Analyst Research Workbench V1 Terminal Semantic Reconciliation

`ANALYST_RESEARCH_WORKBENCH_AND_CASE_OPERATIONS_V1 = READY_FOR_REVIEW` (`push = NO`).

1. The prospective-case milestone's 523 `CASE_CREATABLE` result remains correct and is preserved:
   it means the dated decision and deterministic AI-input packet can form a structurally valid
   prospective research snapshot.  The workbench now exposes that source state as
   `CASE_STRUCTURE_ELIGIBLE`; it is neither evidence sufficiency nor permission to execute
   `CREATE_CASE` immediately.
2. Fresh full-cohort workbench state is exactly 523 research states available, 523 AI inputs
   available, 523 `CASE_STRUCTURE_ELIGIBLE`, 0 validated AI drafts, 0 qualifying human reviews, 0
   `CASE_CREATION_READY`, and 0 local cases.  All 523 creation actions are `CASE_CREATION_NOT_READY`
   for both `NO_VALIDATED_AI_DRAFT_IN_LOCAL_SESSION` and
   `NO_QUALIFYING_HUMAN_REVIEW_IN_LOCAL_SESSION`; no draft or review was fabricated to change that.
3. Every exposed operation now returns current session-local status and prerequisites: research
   state and AI input are `AVAILABLE`; draft validation is `READY` but requires an external draft;
   human review becomes `READY` only after validation; creation becomes `CASE_CREATION_READY` only
   after a qualifying recorded review; case/history/claim/update operations require local case and
   relevant evidence/history state.  A case with no registered retained later evidence is explicitly
   `READY_FOR_TEST_FIXTURE_ONLY` for updates, not described as production-ready.
4. The API records valid drafts/reviews and local cases only in its in-memory session.  It supplies
   no durable production persistence.  Test drafts use `TEST_FIXTURE` identities, test updates use
   `TEST_FIXTURE` with `fixture:` identities, and fixtures remain excluded from observational
   learning.  No authority boundary changes: recommendation, model weight/rule, target/probability,
   valuation, liquidity/PIT, portfolio/sizing, execution, and production DB remain unavailable.

## 2026-08-22 - Durable Prospective Research Case Store V1

`DURABLE_PROSPECTIVE_RESEARCH_CASE_STORE_V1 = READY_FOR_REVIEW` (`push = NO`).

1. `durable_prospective_research_case_store.py` is an explicit-path local, non-production,
   one-writer persistence contract.  It uses immutable content-addressed T0 envelopes for the
   case, original decision/AI identities, validated draft, validation, human review, and individual
   `HUMAN_EDIT` provenance; append-only content-addressed event files hold later updates.  No
   implicit runtime directory, production database, committed mutable case fixture, or migration of
   the 523 `CASE_STRUCTURE_ELIGIBLE` records exists.
2. Every load verifies the store contract, T0 envelope, case identity, event identity, and
   predecessor chain.  Duplicate case/content/event insertion, case mutation, unknown-case append,
   timestamp reversal, unknown predecessor, disconnected chain, concurrent writer, and unregistered
   non-fixture evidence fail closed.  Fixture events require `TEST_FIXTURE` and `fixture:` identity.
3. Replay reconstructs the immutable case, ordered updates, current lifecycle, claim status,
   scenario/catalyst status, and AI/human provenance deterministically across independent store and
   workbench restarts.  The workbench can hydrate durable case state and routes create/update/history
   and durable learning through the store without recalculating any research producer.
4. Durable learning feeds only non-fixture durable cases into the existing observational ledger;
   fixture-origin cases and fixture updates do not contribute.  The store is
   `DURABLE_CASE_SYSTEM_READY` for a genuine future case once a valid draft, qualifying recorded
   human review, explicit local store root, and retained later-evidence identity are supplied.  It
   creates no real case here and changes no recommendation, model/rule, valuation, liquidity/PIT,
   portfolio, sizing, execution, or production authority.

## 2026-08-22 - Prospective Research Case Operations V1

`PROSPECTIVE_RESEARCH_CASE_OPERATIONS_V1 = READY_FOR_HUMAN_REVIEW` (`push = NO`).

1. The first real operating cohort is exactly `HPG`, `VCB`, `SSI`, `AAN`, and `AAA`, selected from
   the retained dated 2026-08-20 523-member empirical-active snapshot for diverse research and
   authority states rather than attractiveness: corporate official financial/proxy valuation, bank
   corporate-action block, securities sector-specific inapplicability, scenario coverage, and low
   official evidence.  The separate 2026-08-21 524-member shadow snapshot is never used as a
   fallback or denominator.
2. `prospective_research_case_operations.py` resolves each exact existing decision/workbench/AI
   packet identity, full evidence inventory, lanes, scenario, valuation, catalysts, questions, and
   blockers into a deterministic operating manifest.  Known-at is honestly session-bound: the
   retained packet identifies 2026-08-20 but provides no exact decision-time timestamp, which is
   explicitly `NOT_RETAINED` rather than invented.
3. Each packet has the actual model-independent AI input and existing prompt/schema prepared.  No
   live model adapter is authorized or called, hence all five are `MODEL_DRAFT_PENDING`, validator
   status is not run, and human review is required.  `REAL_CASES_CREATED = 0`: an implementation
   approval, a fixture, or a coding-agent action cannot substitute for an analyst's real draft and
   qualifying recorded review.
4. The manifest provides the exact human queue, not an investment ranking, and names future
   financial/event/scenario/corporate-action/descriptive-market evidence relationships without
   acquiring or monitoring them.  Its learning baseline has zero real cases, reviews, human edits,
   claim outcomes, and scenario/catalyst outcomes.  A real case may enter the completed durable
   store only after the existing draft-validation-review-store gate passes; no authority boundary
   changes in this operational preparation.

## 2026-08-23 - DNSE Trades and Liquidity Basis Qualification V1

`DNSE_TRADES_AND_LIQUIDITY_BASIS_QUALIFICATION_V1 = COMPLETE_LOCALLY / CURRENT_SESSION_BOARD_COMPOSITION_UNLOCKED_HISTORICAL_STILL_BLOCKED`
(`dnse_trades_liquidity_basis.py`, `tools/derive_dnse_trades_liquidity_basis.py`,
`tests/test_dnse_trades_liquidity_basis.py`, `tests/test_derive_dnse_trades_liquidity_basis.py`,
`operations-review/dnse-trades-liquidity-basis-v1-20260823/dnse_trades_liquidity_basis_artifact.json`,
`push = NO`).

1. **A small new adapter over already-registered endpoints, not a resurrection of orphaned code:**
   `dnse_market_data.MARKET_DATA_ENDPOINTS` already lists `trades_latest`
   (`/price/{symbol}/trades/latest`) and `trades_history` (`/price/{symbol}/trades`) under
   `family=trades`; this milestone builds a bounded canonicalization/aggregation layer on top of
   them. The orphaned `dnse_trades_canonical_shadow.py` (commit
   `2b7b38772e16c434c8adf5288cbc46ef0f7f4c02`, branch `feature/trades-canonical-columnar-shadow-v1`,
   still not an ancestor of `main`) was read only as implementation archaeology (its Parquet
   canonical schema's field choices informed this module's own simpler JSON record shape); nothing
   from it is imported, replayed, or copied.
2. **`10 x G1 == OHLC daily v`, reproduced live and independently:** a bounded 23-call live probe
   (1 auth check, 5 `trades_latest`, 5 `ohlc`, 12 `trades_history`) found that `trades_latest`
   returns each board's own most-recent tick with already board-scoped *cumulative* session
   counters (`totalVolumeTraded`, `grossTradeAmount`, `avgPrice`) -- reading the single latest tick
   per board recovers a complete session volume without summing individual ticks. Across five fresh
   tickers spanning four sectors (HPG steel, VCB banking, SSI securities, FPT technology, QNS
   food/beverage) on the same session (2026-08-21), `10 x G1.totalVolumeTraded` equals that
   session's DNSE daily OHLC `v` exactly (delta = 0 in all 5 cases) -- an independent, live,
   cross-sector reproduction of the existing shadow `dnse_volume_composition_reconciliation.C5_CANDIDATE`
   (previously 99.81% / 67 unresolved residuals over a bulk historical corpus generated by the
   orphaned commit above). The candidate remains `EMPIRICAL_CANDIDATE` with
   `semantic_unit_interpretation=UNKNOWN`; this milestone does not promote it, and
   `g1_scale_cross_check()` echoes the cited candidate object unchanged even on an exact match.
3. **Complete historical `trades_history` reconstruction is activity-dependent, not uniformly
   available:** a fixed 4-page DESC pagination cap (`limit=100`) fully exhausts for a low-activity
   name -- QNS, 2026-08-21, 387 rows across exactly 4 pages, spanning the full 09:16-14:59 session
   and *confirming* zero put-through activity that day by genuine pagination exhaustion (not a
   silent zero). The same 4-page cap leaves HPG/VCB/SSI at `PARTIAL_BOUNDED_SCAN` on **two**
   different sessions (2026-08-19, a large put-through day, and 2026-08-14, the smaller day already
   cross-checked against retained FHSC evidence): HPG/SSI capture only `G1` within the cap, VCB
   captures `G1`+`G4`; every `T`-board stays `boards_unscanned` (never asserted absent). The
   2026-08-19 preliminary probe found the closing-auction burst advances the clock by only ~0.08
   real seconds across 300 DESC-ordered rows -- full reconstruction there would require an unbounded
   number of calls, which this milestone's finite-call constraint correctly refuses to attempt.
4. **`grossTradeAmount` is an open, board-dependent scale finding, not a resolved value field:**
   `avgPrice_kvnd x totalVolumeTraded_raw / 100_000` matches the reported `grossTradeAmount` within
   rounding for every observed board (G1 and non-G1 alike, 5/5 tickers) -- an arithmetic
   self-consistency, not a unit claim. Applying the same G1 x10 hypothesis implies the field lands
   on true cumulative value in *billion VND* for `G1` specifically, but the identical reading would
   overstate a directly-reported (non-x10) board's value by the same factor of 10. This module
   records both facts side by side and resolves neither: `traded_value_candidate()` always returns
   `authoritative=False`, and `derived_value_price_times_shares()` always reports `BLOCKED` /
   `lot_multiplier_ambiguity_unresolved` unless a caller supplies an explicit multiplier, which no
   code path in this milestone does.
5. **Numeric board composition is newly live-readable for the current session, and only the current
   session:** `board_category_totals()` reuses (imports, never redefines)
   `market_price_volume_basis_authority.assert_lot_and_route_not_conflated()`'s four-category split
   and `market_phase2_foundation.DNSE_BOARD_SEMANTICS`'s board-label mapping. A board absent from a
   `trades_latest` response, or present with a stale (non-target-session) date, is recorded in
   `boards_not_counted`/`boards_unscanned` rather than folded into a silent zero --
   `OBSERVED_ACTIVE_THIS_SESSION` vs `OBSERVED_INACTIVE_STALE` vs `NOT_OBSERVED` remain distinct
   states throughout.
6. **Session liquidity-research contract, fail-closed by construction:**
   `session_liquidity_research_contract()` independently derives
   `CURRENT_SESSION_LIQUIDITY_RESEARCH` (`ELIGIBLE`, research-descriptive only, for all 5 corpus
   tickers), `HISTORICAL_LIQUIDITY_RESEARCH` (`BLOCKED` for HPG/VCB/SSI's `PARTIAL_BOUNDED_SCAN`;
   would be `PARTIAL`, never `ELIGIBLE`, only on a genuinely exhausted scan), and unconditional
   `BLOCKED` for `ADV_VOLUME_RESEARCH`, `ADTV_RESEARCH`, `POSITION_SIZING`, `EXECUTION_CAPACITY`, and
   `PIT_BACKTEST` regardless of the current-session result. `assert_fail_closed()` raises if any
   authority-sensitive dimension is ever `ELIGIBLE`/`PARTIAL` or uncited; the real run's contract
   passes for all 5 tickers.
7. **FHSC reconciliation reused read-only, no new FHSC call:** the shared 2026-08-14 session lets
   this milestone cite (not recompute) the already-retained
   `operations-review/dnse-fhsc-volume-basis-qualification-v1-20260821/dnse_fhsc_volume_basis_qualification_artifact.json`
   for HPG/VCB/SSI (put-through volumes 225,000 / 244,002 / 90,000, all previously classified
   `DNSE_EQUALS_MATCHED`). FHSC remains `CREDENTIAL_BLOCKED`; no FHSC credential or live call was
   used anywhere in this milestone.
8. **Negative boundaries and validation:** no RAW_AS_TRADED, PIT, liquidity, sizing, or
   valuation-formula authority promoted; `QUALIFIED_LIQUIDITY_INPUTS = NO` and
   `POSITION_SIZING_IS_SAFE = NO` are unconditionally re-confirmed. 55 new tests (46 for the
   capability module, 9 for the adapter tool, all offline/mocked) plus the 197 directly-relevant
   existing tests (`market_price_volume_basis_authority`, `dnse_volume_composition_reconciliation`,
   `dnse_fhsc_volume_basis`, `market_phase2_foundation`, `p3f19_liquidity_authority_terminal_resolution`,
   `dnse_access`, `dnse_market_data_probe`) pass unchanged. `market_wide_current_valuation_input_scaleout.py`,
   `tools/derive_market_wide_current_valuation_input_scaleout.py`, `tools/build_daily_analyst_brief.py`,
   their tests, and the five `HUMAN_REVIEW_REQUIRED` prospective research cases were not touched.
   `risk_liquidity.py` was not touched. Total live DNSE calls across this milestone's design and
   final run: 42 (19 bounded exploratory + 23 in the final fixed, auditable call plan); zero
   polling, zero retry loops, zero background agents, no merge/deploy/push.
## 2026-08-23 - Market-Wide Current Liquidity Research Scale-Out V1

`MARKET_WIDE_CURRENT_LIQUIDITY_RESEARCH_SCALEOUT_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL`.

1. The retained P3F9B canonical mapping supplies the fixed 1,683-candidate universe. Foreground-only, idempotent 25-symbol batches retain every response disposition and consolidate only when each candidate appears exactly once; no runtime or production database is written.
2. The 2026-08-21 terminal artifact records 955 `CURRENT_SESSION_DESCRIPTIVE_ELIGIBLE`, 241 `INCOMPLETE`, 479 `MISSING`, and 8 `PROVIDER_REJECTED` records, with zero unattempted. Missing, rejection, malformed/incomplete states are distinct and never zero-filled.
3. G1/G4/T1/T3/T4/T6 remain separate. Provider-raw current-session composition ratios are descriptive only; G1 is exactly reconciled with compatible OHLC `v` for 954/955 eligible records, while SHB's residual of four remains explicit. `grossTradeAmount` is retained only with unresolved scale/basis; no traded value is derived.
4. This does not promote qualified liquidity inputs, ADV/ADTV, historical liquidity, execution capacity, position sizing, PIT/backtest, or RAW_AS_TRADED authority.

## 2026-08-23 - Current Liquidity Research Feature Integration V1

`CURRENT_LIQUIDITY_RESEARCH_FEATURE_INTEGRATION_V1 = COMPLETE_LOCALLY / COHERENT_PARTIAL`.

1. `export_ai_bundle.py` gains one new opt-in attach layer (`--include-market-wide-current-liquidity-research`, `--market-wide-current-liquidity-research-path PATH`) that consumes the already-retained `market_wide_current_liquidity_research` artifact and reuses the existing `tickers[ticker].*` bundle-consumption contract already used by `foreign_flow`/`current_state_market_risk`/`current_state_price_analytics`/`current_state_relative_valuation`. No new feature store, digest, workbench, packet, or orchestration abstraction was created; `dnse_trades_liquidity_basis.py` is never called from this layer, so no DNSE trade is reacquired or re-qualified.
2. Per-ticker `disposition`, `board_composition` (G1/G4/T1/T3/T4/T6-derived), `g1_v_reconciliation`, `current_ohlc_v`, `liquidity_research_contract`, and `value_status` are reused verbatim. SHB's four-unit `g1_v_reconciliation.verdict = OTHER` residual passes through unmodified -- it is never coerced toward `EXACT_MATCH`. Two convenience fields (`status`, `reconciliation_verdict`) are re-exposed copies, matching the existing `current_state_*` sibling convention; `is_actionable=false` is unconditional. Missing/incomplete/provider-rejected tickers keep their own explicit disposition; a ticker outside the retained artifact's universe gets no key at all.
3. Because the retained artifact lives under `operations-review/` rather than a runtime-root-backed durable store, the artifact path is required explicitly via CLI flag (never inferred or hardcoded, matching the existing `--qualified-research-delta-previous` convention). The loader recomputes `market_wide_current_liquidity_research.content_identity()` against the artifact's own recorded `artifact_sha256` before attaching anything; a missing file, malformed JSON, or hash mismatch fails the entire step closed (no key on any ticker), never a partial/degraded attach.
4. That verification gate found the retained 2026-08-23 checkpoint did not reproduce its own recorded hash: `tools/run_market_wide_current_liquidity_research.py`'s `consolidate()` stamped `artifact_sha256`/`artifact_identity` before adding `resolved_completed_session` and `universe.source_snapshot_identity`, so the recorded hash covered a strict subset of the persisted payload. `consolidate()` now re-stamps identity over the complete final dict (`market_wide_current_liquidity_research.content_identity()`, exported alongside `build_artifact()`), and the checkpoint was regenerated **offline from its own 68 already-retained batch files** -- zero new DNSE calls, zero re-qualification. A full-tree diff against the pre-fix file shows exactly two changed leaf paths (`artifact_sha256`, `artifact_identity`); every record, coverage count, and `authority_boundary` value is byte-identical. New corrected identity: `market_wide_current_liquidity_research:dc9b464914c8da2a8b27e51ab0e427d099f8d5fa5fd5d3392cb65e85f09ecbbb`.
5. `QUALIFIED_LIQUIDITY_INPUTS = NO` and `POSITION_SIZING_IS_SAFE = NO` remain unconditionally re-confirmed by the artifact's own `authority_boundary`; no ADV/ADTV, historical liquidity, liquidity-based sizing, execution capacity, PIT/backtest, RAW_AS_TRADED, or recommendation authority is created. Not enabled in any default/production `export_ai_bundle.py` invocation.
6. Scope: this milestone is Producer-only (`stock-core-private`), matching its single authorized Producer HEAD. `ai-core-private` already has a per-feature `*_contract_pass_through` test convention for sibling current-state features, but no such contract exists yet for `market_wide_current_liquidity_research` -- wiring one is a natural next bounded step, not performed here. `market_wide_current_valuation_input_scaleout.py`, `tools/derive_market_wide_current_valuation_input_scaleout.py`, `tools/build_daily_analyst_brief.py`, and their tests (five protected untracked WIP files) were not opened or touched. New/updated tests: `tests/test_export_ai_bundle_market_wide_current_liquidity_research.py` (17), `tests/test_run_market_wide_current_liquidity_research.py` (3, regression coverage for the identity fix), plus the pre-existing `tests/test_market_wide_current_liquidity_research.py` (1) -- all pass, alongside the directly-dependent `tests/test_export_ai_bundle.py` and sibling `test_export_ai_bundle_current_state_*`/`test_export_ai_bundle_dnse_foreign_flow`/`test_export_ai_bundle_pillar_a_cache` suites (230 passed; the same 6 failures pre-exist identically on an unmodified baseline, confirmed by stashing this milestone's tracked changes and re-running -- unrelated to this work). Zero polling, zero background agents, no merge/deploy/push.

## 2026-08-24 - Sector-Aware Relative Research and Expectations V1

`SECTOR_AWARE_RELATIVE_RESEARCH_AND_EXPECTATIONS_V1 = COMPLETE_LOCALLY / DESCRIPTIVE_ONLY`.

1. The existing `sector_aware_relative_research/v1` artifact remains a deterministic join of retained descriptive, tactical, fundamental, and valuation artifacts. It now uses retained VCI descriptive industry identity as the primary corporate peer set where that identity is present; a qualified entity-class cohort is an explicit fallback, never silently presented as industry-relative research. No ticker/company-name heuristic, metric-shape inference, or new taxonomy is used.
2. Every membership carries its peer group, level, source record, qualification/fallback state, limitations, and cohort sufficiency. Technical comparisons retain only current-session existing features; fundamental dimensions remain metric-specific; valuation peer comparison remains `VALUATION_PEER_CONTEXT_UNAVAILABLE` because share-proxy semantics, financial authority, metric identity, and cohort sufficiency are not jointly established.
3. `export_ai_bundle.py` adds a disabled-by-default explicit path/flag attach, and the Consumer validates then passes the Producer record verbatim. Neither side creates a score, rank, target, recommendation, probability, sizing, alpha, or a second expectations classifier. The frozen prospective snapshot and scenario cases are untouched.

## 2026-08-24 - Current Evidence-Bound Scenario Engine V1

1. `current_evidence_bound_scenario/v1` ports the existing `expectations_scenario_research/v1` evidence-bound Bear/Base/Bull vocabulary to the retained 1,683-candidate current-research universe. The existing immutable 25-case review artifact is not changed or retrofitted.
2. Cases reuse retained tactical confirmation/invalidation, current descriptive state, sector-aware peer context, fundamental trajectory, valuation availability, and retained catalyst status. Missing inputs narrow dependent case content; no provider/network acquisition or new financial/technical calculation occurs.
3. Every case is conditional and carries `UNKNOWN_UNCALIBRATED` probability status. Base is a reference/current-continuation case, not most likely. Producer and Consumer are opt-in verbatim pass-throughs and reject malformed structures; no target, expected return, rank, recommendation, sizing, portfolio, execution, valuation discrimination, outcome, or calibration authority is emitted.

## 2026-08-24 - Current Official Market Universe Integration V1

1. `current_official_market_universe/v1` is a read-only projection over retained HNX/UPCoM issuer-list and HOSE stock-master rows. It establishes current official exchange presence and preserves source-row identity, but never aliases HNX KLLH/KLNY/KLĐKGD or HOSE `outStanding` to accounting common shares outstanding.
2. Exact ticker reconciliation is deterministic. Official-only rows remain a governed delta for owner review; they are not silently added. A Stock Lookup-only residual is only called delisted when the already-retained cross-provider status artifact establishes it; remaining active-reference disagreement is `SYMBOL_IDENTITY_DRIFT`, not inferred absence.
3. The projection is fit only as a current research denominator through an explicit ticker-filter adapter. It neither changes downstream formulas/classifiers nor creates historical PIT, survivorship-safe backtest, ranking, sizing, execution, or valuation authority. HNX event rows remain source-identity-bound and CI-compatible in shape, but require an explicit future CI-loader adapter rather than a parallel event engine.

## 2026-08-24 - Current Official Event Context Integration V1

1. `current_official_event_context/v1` is a read-only, individually retained event projection over the already-acquired HNX rights index and scoped HOSE public events, filtered to the current 1,507 Stock Lookup official-universe denominator. Non-current and official-only evidence is retained separately and never injected into current candidate context.
2. The existing Corporate Intelligence event contract is extended only through its optional event input. Explicit ex-date derives deterministic `UPCOMING`, `EX_DATE_TODAY`, `RECENT`, or `PAST` context; missing ex-date remains `DATE_INCOMPLETE`, and AGM remains informational/governance context. Publication timing remains unknown for indexed HNX rows, so every added event is marked `LIMITED_PUBLICATION_TIME_UNKNOWN` and is unavailable for historical known-at replay.
3. Existing scenario, Daily Product, and EVENT_DRIVEN paths consume the CI context unchanged. EVENT_DRIVEN has only `CURRENT_OFFICIAL_EVENT` as a required feature, so its eligibility increase is a consequence of its existing rule rather than a new strategy rule. The frozen 2026-08-20 research packet remains unmodified because its governed cohort/session has no compatible current-session adapter.

## 2026-08-24 - Current Daily Decision Research Product V2

1. The product extends the existing daily research / AI Research Analyst architecture as one integration surface rather than a new analytical engine, packet, workbench, or case store. It reads only current retained artifacts and writes one deterministic JSON product plus one Markdown human-review brief.
2. Cohorts are existing tactical-state and triage cohorts, ordered only by ticker. The product makes full-universe discovery explicit: watchlist membership is not opportunity authority, and outside-watchlist names are candidates for human research only.
3. Ticker cards preserve exact tactical state/action/trigger/invalidation, retained peer and fundamental context, strict/shadow valuation limitations, and the existing evidence-bound scenario cases. Claim categories remain FACT / INFERENCE / DATA_GAP / QUESTION_TO_VERIFY. The Consumer validates the card and passes it verbatim; no recommendation, sizing, execution, target, rank, probability, portfolio, or source-authority promotion is created.

## 2026-08-24 - Daily Research Session Operations V1

1. A session operation resolves inputs only from an explicit identity-bound registry; no filename glob or ambiguous “latest” selection is allowed. Screening and tactical must reference the selected descriptive identity exactly, and a session/lineage mismatch fails closed.
2. The 763-versus-956 discrepancy was not a denominator difference: 763 was the superseded pre-recovery descriptive artifact's same-session technical count, while the accepted recovered descriptive artifact has 956 and is the exact identity already bound by screening/tactical. The operation rebuilds peer, scenario, and daily product outputs from the accepted source instead of mixing prior same-date downstream outputs.
3. The operation writes immutable session outputs and a deterministic manifest, calls the existing Consumer card validator, and seals the existing prospective current-decision surface with outcomes pending. Retained fundamental context is marked undated and catalyst context is marked earlier/degraded. No scheduler, acquisition, authority promotion, probability, target, recommendation, sizing, portfolio, execution, outcome, calibration, PIT, or backtest capability is created.

## 2026-08-24 - Market-Wide Current Corporate Intelligence and Catalyst V1

1. `market_wide_current_corporate_intelligence/v1` is a retained-evidence materialization boundary, not a generic issuer-news crawler. It emits all 1,683 current-universe records with explicit `CURRENT_INTELLIGENCE_AVAILABLE`, `HISTORICAL_INTELLIGENCE_ONLY`, or `NO_RETAINED_INTELLIGENCE` disposition and preserves fact, event, evidence, authority, freshness, lifecycle, unknown fields, and limitations separately.
2. The bounded retained corpus has three corporate-action chains: HPG is an official-qualified July 2026 executed action with no ex-date; VNM is a historical official completed cash dividend with record/payment dates retained separately; VCB is a historical issuer-IR approved stock dividend with missing completion/supersession evidence. The VCB record is intentionally `APPROVED`, never `EXECUTED`; its record date is not an ex-date. Catalyst descriptors are neutral (`DIRECTION_UNCLEAR`) and no price impact, probability, or causal claim is emitted.
3. The exact Corporate Intelligence artifact identity is required by the normal daily-session input registry. The session runner validates its current-session descriptive lineage and universe, gives scenario a neutral independent `CATALYST_OR_EVENT` driver, adds concise confirmed/pending/verify context to daily Product V2 cards, and Consumer validates that context without deriving facts or recommendations. A separate corporate-intelligence prospective identity context is sealed beside—not inside or in place of—the frozen current-decision snapshot.
4. There is no retained market-wide current shareholder/ownership or management/board-change corpus in the selected inputs, so both coverages are zero and represented as data gaps. No generic issuer disclosure feed, provider/official authority, corporate-action price adjustment, RAW_AS_TRADED/PIT, valuation, target, ranking, sizing, portfolio, execution, or outcome authority changes. A future scale-out needs an owner-governed, raw-retaining official disclosure or shareholder source contract.

## 2026-08-24 - Polymorphic Current Strategy Classification Engine V1

1. `polymorphic_current_strategy_classification/v1` reuses the existing strategy-research eligibility and multi-label setup-classification precedent but operates against the current 1,683-record decision surface. Its executable registry declares requirements, allowed authority, forbidden substitutes, rule, evidence, counter-evidence, and invalidation boundary for each strategy; adding a strategy is a registry-plus-classifier-and-test change, not a consumer rewrite.
2. V1 contains `TREND_MOMENTUM`, `BREAKOUT`, `EARLY_REVERSAL`, `BASE_ACCUMULATION`, `FUNDAMENTAL_IMPROVEMENT`, `EVENT_DRIVEN`, and `VALUE`. Technical strategies use only retained current tactical/technical evidence. Fundamental Improvement permits expressly descriptive `PROVIDER_RESEARCH` trajectories but never promotes absolute values. Event Driven requires retained official current event evidence and preserves lifecycle/freshness. Value is blocked unless strict authoritative valuation is ready; shadow issued-share valuation is explicitly forbidden as its substitute.
3. Each record preserves all independently eligible, partial, blocked, not-applicable, or insufficient-data strategies with feature-level requirement identities. Strategy fit is not an entry action, BUY, scenario probability, portfolio action, ranking, score, target, sizing, execution, causal claim, or backtest. The existing scenario is consumed, never recomputed; its probability remains `UNKNOWN_UNCALIBRATED`.
4. The daily session builds strategy after the coherent scenario and before Product V2, binds all inputs to exact selected identities, writes strategy output and additive prospective identity context, and passes card summaries through Consumer fail-closed. Earlier frozen prospective snapshots remain immutable.

## 2026-08-24 - Current Portfolio Risk Envelope V1

1. Portfolio analysis requires an explicit positions/exposure input and exact session match; a watchlist, scenario, strategy classification, or candidate card can never create a holding or weight.
2. The first envelope is concentration and evidence context only. It reports single-name/entity/strategy/tactical exposure, scenario/fundamental/event/data-quality context, and explicit user-limit comparisons. It does not emit recommendations, allocation, optimal weights, sizing, execution, probability-weighted risk, or a portfolio volatility estimate.
3. Liquidity, days-to-liquidate, correlation, portfolio volatility, VaR, CVaR, position sizing, leverage, and execution remain fail-closed because qualified liquidity/PIT/policy inputs are absent. Consumer accepts the optional envelope only when it preserves those non-actionable statuses.
4. The bounded fixture is designated `DEMONSTRATION_NOT_REAL_HOLDINGS`; it is retained solely as a deterministic validation fixture and is excluded from prospective-learning surfaces.

## 2026-08-24 - Current Macro Regime and Cross-Asset Context V1

1. Current macro evidence is represented as source-bound observations with observation date and release timestamp kept distinct. Missing official dimensions are `UNAVAILABLE`, never zero or an inferred proxy.
2. Independent deterministic axes are not a weighted score. The optional high-level regime is an explicit mapping of those axes and remains descriptive—not a stock-market forecast or causal proof.
3. FRED graph CSV is current-research official-public evidence but lacks release/vintage timestamps in the retained endpoint; it is therefore expressly not historical PIT. A later macro artifact can be bound in a historical equity-session manifest only as `UNAVAILABLE` context.
4. No ticker macro sensitivity, sector beta, VaR/CVaR, liquidity, sizing, leverage, execution, ranking, recommendation, probability, target, or calibration output is authorized.

## 2026-08-24 - Vietnam Official Macro Evidence V1

1. `vietnam_macro_observation/v1` retains immutable, SHA-256-addressed raw first-party NSO release bytes, including source locator, content type, publication date, retrieval timestamp, reference period, parse state, and revision-chain slots. June and July 2026 CPI releases explicitly state their year-on-year values; no homepage label or secondary source is used as a metric.
2. July 2026 CPI year-on-year (4.45%, published 2026-08-03) is qualified for current descriptive context and for date-level historical use after its publication date only. The retained NSO calendar makes it current through 2026-09-03; this is metric-specific freshness, never a generic age threshold. Intraday publication timing remains unavailable.
3. The existing Macro V1 adapter uses the June predecessor (4.69%) only to compute the independent CPI axis. SBV policy rate, central FX, credit growth, system liquidity, and government-bond yield remain unavailable until a retained official source explicitly supplies each metric's own definition, period, and publication metadata. No proxy or no-data regime inference is permitted.
4. The result remains descriptive and non-actionable. It creates no forecast, causal, allocation, liquidity, sizing, execution, portfolio, or broader historical-PIT authority; a post-session current macro artifact remains unavailable to the earlier daily-session context.

## 2026-08-24 - Official Financial Filings and Canonical History Scale-Out V1

1. The retained, approved HNX issuer-disclosure RSS is a bounded bulk discovery input. Its 100 items exposed 11 H1-2026 financial-statement disclosures; eight directly linked first-party statement PDFs were retained immutably, while three detail pages did not expose a statement attachment matching the filing contract.
2. HNX detail pages did not state a ticker field for these filing notices. Attachment filename tokens are retained as unqualified source text and are never promoted to a ticker identity. The PDFs are retained with SHA-256, source URL, publication date, reporting-period candidate, title-derived scope candidate, and separately detected extraction status; original bytes are not replaced.
3. No document supplied both a qualified issuer identity and an exact machine-readable cited value line for a canonical fact. Accordingly, canonical financial observations, provider reconciliations, financial/peer/scenario dependencies, and valuation readiness remain unchanged. Missing is not zero; total equity, debt, and weighted-average shares receive no alias or proxy.
4. The HNX attachment host is admitted only as the first-party file host explicitly linked by the approved HNX disclosure detail pages and only for the two existing financial filing document types. No provider, issuer-IR wildcard, valuation engine, or runtime database is added or mutated.

## 2026-08-24 - HNX Official Filing Evidence Binding and Extraction V1

1. The eight retained HNX H1-2026 PDFs are each linked exactly once by their retained HNX parent detail page, with both parent and PDF SHA-256 checked on deterministic replay. That attachment relation alone does not identify an issuer.
2. All eight parent `Box-Noidung` blocks are present but empty: there is no explicit `Mã chứng khoán` field or other structured issuer/ticker evidence. HNX page chrome, search-widget symbols, attachment filenames, company-name guesses, and provider records are not admitted as document identity evidence.
3. Parent titles qualify H1-2026 period for eight documents and separate scope for three; audit/review status remains unknown. Because document identity is unproven, no PDF text/OCR fact is extracted, no provider reconciliation is attempted, and canonical financial facts remain 138 across 13 issuers.
4. This is terminal `OFFICIAL_PARENT_BINDING_UNPROVEN` for this retained route. The only next gate is HNX parent disclosure metadata that explicitly ties the existing attachment to an issuer ticker; it is not a basis for repeated PDF/OCR attempts or a broader crawl.

## 2026-08-24 - HNX Multi-Attachment Binding and Citable Extraction V1

1. The eight retained parent pages disclose a real one-to-many topology of 27 ordered HNX attachment links. Attachment-level filename/title evidence classifies 16 statement candidates (six consolidated, four separate, six scope-unknown), ten explanatory letters, and one other disclosure letter; explanatory letters are excluded from statement extraction and scope is never copied across siblings.
2. Eight statement children have retained PDF bytes and SHA-256; the remaining 19 listed attachment bytes were not retained and therefore have null SHA/content states. All eight retained PDFs deterministically yield zero native-text characters and are classified `IMAGE_ONLY_OR_SCANNED`. The repository's OCR sidecar has no operating executor for this corpus, so no OCR result/citation is created.
3. Every parent disclosure content block remains empty of issuer/ticker. An exact parent-to-child link cannot convey identity without an explicit parent identity, so all 27 child tickers remain unresolved. Attachment filenames, file titles, page chrome, and providers are not substitute identity evidence.
4. No retained statement has citable currency/unit/scale evidence; all eight retained PDFs are `UNIT_SCALE_UNRESOLVED`, canonical values remain null, provider comparison is not attempted, and the existing 138 observations/13 tickers are unchanged. This is terminal `MULTI_ATTACHMENT_BINDING_UNPROVEN` for the current HNX route.

## 2026-08-24 - HNX Official Issuer-Profile Multi-Gate Data Unlock V1

1. Hash-retained HNX autocomplete and profile pages establish an exact identity contract for PHN (`NY`), MBS (`NY`), and MVN (`UC`). All three are profile-path common-equity candidates; no bond/fund/warrant profile enters the sample.
2. HNX labels `KLLH (Cổ phiếu)` and `KLNY (Cổ phiếu)` remain separate. PHN is an equality observation (7,253,911 each); MBS is a discriminating inequality (KLLH 1,000,933,410 < KLNY 1,000,963,451). MVN exposes `KLĐKGD (Cổ phiếu)`, not KLNY, and its 6,374,700 value is stored independently. The labels prove a current exchange-reported circulating-share record only; treasury treatment and accounting common-share scope are absent, so strict common-share/market-cap/valuation authority remains zero.
3. The retained profile event tables contain 17 explicit `Ngày GDKHQ` values across PHN, MBS, and MVN, independent of `Ngày ĐKCC` and `Ngày thực hiện`: seven cash dividends, two rights issues, one bonus issue, and seven AGMs. Each explicit ex-date is retained as first-party official event data. AGMs are never price-adjustment candidates. Existing PIT evidence covers DTP and the retained price cohorts do not overlap these three tickers, so no snapshot pair, OHLC mutation, or RAW_AS_TRADED promotion occurs.
4. The HNX autocomplete endpoint returns capped suggestions without total/pagination metadata (including an empty result for an empty query), so it cannot support a market-wide HNX/UPCoM denominator or safe enumeration. Profile disclosure surfaces do not produce an exact ticker-bearing record matching any of the eight retained generic H1-2026 financial parents; all 27 children remain unresolved. This bounded route closes as `HNX_EVENT_AND_IDENTITY_ONLY` pending a first-party enumerable common-equity list and exact ticker-bearing filing-index linkage.

## 2026-08-24 - Current Market Flow / Positioning V1

1. `current_market_flow_positioning/v1` is a projection of canonical retained observations, never a second feature store. Provider-specific facts remain separate and every field keeps session, retrieval, endpoint, raw hash, and source identity.
2. Traded-value and foreign-room arithmetic are emitted only when exact component identities hold. Missing/rejected/rate-limited/semantic-blocked observations never become zero. DNSE remains the selected source for qualified foreign value flow when present; FHSC-only current research fields are usable without artificial provider parity.
3. Price-flow labels are deterministic relationships only. They are not causal explanations, hidden-liquidity/SMC evidence, institutional intent, a recommendation, or an execution/sizing input. Strategy evidence is optional and does not alter existing eligibility.
4. A session registry may bind an explicit flow artifact as an optional input. Scenario, Product V2, Consumer, explicit portfolio context, and prospective identity freeze preserve the same non-causal, non-sizing boundary. Full-universe aggregation is only permitted over a named eligible cohort.

## 2026-08-24 - Current Market Flow / Positioning Scaleout V1

1. Session eligibility requires a retained provider session binding equal to the selected completed session. The DNSE foreign-trading adapter now retains a provider session only when all row timestamps agree with the requested session; mixed/undated responses remain unavailable for flow use.
2. The scaleout artifact is a deterministic retained-packet composite, not a new provider or data store. It selects the latest acquired endpoint version deterministically while retaining every candidate raw version in lineage; no raw payload is overwritten or silently repaired.
3. The 1,683-record flow surface is bound by exact identity to the daily session registry. Missing fields remain independent dimensions. Aggregates are labeled `PARTIAL_COHORT_CONTEXT` unless an eligible cohort is sufficiently broad; no provider cohort is called the Vietnamese market.
4. The terminal result is `COHERENT_PARTIAL_PROVIDER_LIMITED`. Broad traded-value evidence is a future `PROMOTION_REVIEW_CANDIDATE` only; it does not grant liquidity, ADV, sizing, execution, PIT, backtest, RAW_AS_TRADED, causal, or institutional-intent authority.
# 2026-08-24 - Authoritative Current Common Shares Qualification & Scaleout V1

1. The configured KBS public company-profile route was tested as a materially distinct candidate from `VCI.overview.issue_share`: its documented repository field label is `outstanding_shares`, retained separately from issued shares. Six representative ticker responses (HPG, VCB, SSI, VNM, FPT, PAN) were retained immutably with endpoint, status, retrieval time, exact bytes, and SHA-256.
2. All six live requests returned the same HTTP 400, 154-byte non-JSON response. No share observation, field schema, common-share scope, treasury treatment, source-as-of date, or effective interval was therefore acquired. The full 1,683-candidate ledger records six `UNAVAILABLE` pilot results and 1,677 `NOT_ATTEMPTED_FOR_JUSTIFIED_SCOPE`; no bulk crawl followed a failed semantic pilot.
3. KBS provider terminology is not promoted or aliased to `common_shares_outstanding`; cross-source reconciliation is `SEMANTICALLY_NOT_COMPARABLE`. The VCI issued-share shadow proxy remains separate and unchanged. Strict current share-ready/market-cap-ready counts remain zero, as do peer-valuation and VALUE strategy unlocks.

## 2026-08-24 - Historical Matched Traded Value and ADV Authority V1

`HISTORICAL_MATCHED_TRADED_VALUE_AND_ADV_AUTHORITY_V1 = COMPLETE_LOCAL / OUTCOME_C_NARROW_MATCHED_VALUE_UNLOCK / ADV20_NOT_READY` (`historical_matched_traded_value_authority.py`, `tools/derive_historical_matched_traded_value_authority.py`, `tests/test_historical_matched_traded_value_authority.py`, `push = NO`).

1. The final retained DNSE Trades corpus, rather than a current-session counter or a new provider call, supplies the history.  Its checkpoint retains 40 sessions, 1,660 requested instruments, 66,373 successful logical ticker-session responses, and 27 failures.  This milestone requires a contiguous retained cursor chain ending in a null next-page token per qualified ticker-session; missing, malformed, or nonterminal chains remain incomplete and are never zero-filled.
2. The only qualifying formula is `sum(G1.matchPrice * G1.matchQtty) * 10 * 1,000 VND`.  It is independently tested against twelve FHSC matched-volume-and-value anchors for FPT, HPG, SSI, and VCB over 2026-08-07/10/11: all 12/12 are exact for both G1 ×10 shares and value in VND.  FHSC remains a shadow reference; the result is an empirical, four-ticker/three-session G1 scope, not a provider replacement or universal traded-value field.
3. Actual G4/T1/T3/T4/T6 composition is retained on every qualified row.  Those boards are explicitly excluded from the qualified matched-value output pending their own semantics/reconciliation; no put-through, grossTradeAmount, OHLC price×volume, average, or magnitude heuristic is used as a substitute.
4. The 1,683-candidate ledger reports 4 matched-value-qualified tickers (12 ticker-sessions), 1,631 in-corpus semantic blocks outside the exact FHSC-value anchor scope, and 48 current-universe names absent from the retained Trades universe.  The 1,683 and 1,660 denominators are retained as separate source contracts; their identifier difference is not silently collapsed.  Each qualified ticker has 3/20 expected complete sessions; ADV20 is `ADV20_INSUFFICIENT_HISTORY` with a null value.  No liquidity/turnover, portfolio-risk dependency, execution, sizing, PIT/backtest, RAW_AS_TRADED, valuation, or recommendation authority changes.  The next real data gate is 20 expected complete sessions that reproduce this exact contract.

## 2026-08-24 - Historical PIT Raw-As-Traded and Corporate-Action Evidence V1

`HISTORICAL_PIT_RAW_AS_TRADED_AND_CORPORATE_ACTION_EVIDENCE_V1 = OUTCOME_D_GATE_3_CLOSED_NO_NEW_RAW_OR_EX_DATE_AUTHORITY` (`historical_pit_raw_as_traded_evidence.py`, `tools/run_historical_pit_raw_as_traded_evidence.py`, `tests/test_historical_pit_raw_as_traded_evidence.py`, `push = NO`).

1. The approved VSDC route was used only as declared: one retained `/en/alc/6` announcement index page, no pagination/search/crawl, then one direct DTP notice link from that retained page. Acquisition was one foreground request at a time with `max_attempts=1`; no retry, polling, sleep, or background activity was used. The DTP ticker is an explicitly finite addition to the acquirer's bounded cohort, justified by that index-observed cash-dividend notice, not a wildcard expansion.
2. The direct VSDC notice is retained with its document ID, URL, retrieval time, publication date, ticker, SHA-256, content type, and acquisition status. It confirms a DTP cash-dividend record date of 2026-09-04 and a payment-time statement, but supplies no labelled ex-date. The exact `8% per share (800 VND/bond)` wording is semantically inconsistent for cash-per-share extraction, so the amount remains null rather than inferred. Record/payment/announcement dates never substitute for an ex-date.
3. The artifact maintains separate RAW_AS_TRADED, RETROSPECTIVELY_ADJUSTED, ADJUSTED_ANALYTICAL, and UNKNOWN streams by source/field/exchange/range. DNSE, VCI, KBS, and the one-observation HOSE pilot retain their pre-existing scoped verdicts; the VSDC notice is entitlement evidence, not a price stream. The lone new event window is `INSUFFICIENT`; no before-event snapshot exists, so mutability cannot be tested and two post-event snapshots would not answer it.
4. The adjustment ledger is shadow-only and `NOT_IMPLEMENTED`; it never mutates OHLC. No new RAW_AS_TRADED authority, corporate-action factor, historical valuation, return/risk, or backtest authority is promoted. The next real gate is one or more retained official notices with explicit ex-dates plus exact matching pre-event raw price snapshots for their ticker/event windows.

## 2026-08-24 - Historical Matched Value Existing-Store Requalification V1

`HISTORICAL_MATCHED_VALUE_EXISTING_STORE_REQUALIFICATION_V1 = EXISTING_STORE_CANNOT_UNLOCK_ADV20` (`historical_matched_value_existing_store_requalification.py`, `tools/run_historical_matched_value_existing_store_requalification.py`, `push = NO`).

1. The retained source inventory has two raw DNSE Trades collections (203,431 original and 36,605 targeted-repair Parquet pages) and a 40-partition final execution shadow. The decoded raw trade records carry `boardId`, `matchPrice`, and `matchQtty`; the final shadow preserves their `board_id`, `price`, and `quantity` with page/payload/record lineage. Neither layer carries an explicit matched, put-through, or total traded-value field. `grossTradeAmount` exists in raw payloads but remains an unresolved board-dependent cumulative counter, so it is not substituted for any value identity.
2. The two retained daily canonical Parquet variants expose only O/H/L/C/volume plus provenance and explicitly mark volume basis unknown. The root and three retained shadow SQLite histories likewise expose only `ohlcv(ticker,date,open,high,low,close,volume,source)`; no value/`va` field was found. Daily `v` is therefore never multiplied by close or reused as matched value. The retained 40-session board test is preserved: `10 × G1` equals daily `v` on 35,164/35,231 rows, which does not establish put-through inclusion or any value semantic; price and volume adjustment qualifications remain independent.
3. The re-run uncovered and corrected a mechanical qualifier bug: the raw DNSE page chains are explicitly zero-based (`0..N`), while the prior validator admitted only one-based examples. It now accepts either declared first-page base while continuing to require contiguous cursors and a terminal null token. The same retained raw bytes again reproduce 12/12 exact FHSC matched-volume and matched-value anchors for FPT, HPG, SSI, and VCB on 2026-08-07/10/11.
4. Those exact rows establish an empirical transform only inside their four-ticker/three-session/12-row scope. They do not independently validate any remaining session, and no existing-store explicit value field supplies that missing evidence. Each anchor ticker has three—not twenty—qualified complete sessions; no ADV20 average is emitted. No liquidity, position sizing, participation, days-to-liquidate, execution, portfolio, PIT-price, backtest, Dashboard, or AI authority changes. The next gate is 20 governed complete sessions with independent exact G1 value anchors, or an independently qualified explicit matched-value field.

## 2026-08-26 - Canonical Post-Close One-Command Pipeline V1

1. `daily_session_level2_package.py` already builds most of the "current research" components in correct per-session dependency order (breadth, universe resolution, liquidity, technical recovery, descriptive, screening, tactical, corporate intelligence, valuation, sector leadership, peer-relative, risk register, and triage-dependent scenario/strategy/opportunity). The new `canonical_post_close_pipeline.py` wholly reuses it rather than building a second acquisition/materialization engine; new code is limited to the registry writer, the evidence-based completeness gate, decision-packet/enrichment assembly, prospective-collection invocation, and the tiered bundle.
2. Two pre-existing bugs were found in `daily_session_level2_package.materialize_independent_components` while integrating -- its P3F9B and universe-resolution subprocess calls used CLI flags that do not exist on the current scripts -- and were fixed in place rather than routed around, since the reused capability was otherwise silently broken for any genuinely fresh session (every session attempted so far already had its P3F9B artifact from a separate manual run, so the broken calls had never fired).
3. No programmatic writer for `config/daily_research_session_input_registry.json` existed anywhere in the repository; registration was always a manual JSON edit. The new writer reproduces the exact shape of the existing hand-written entries and reuses `daily_research_session_operations`'s own lock/coherence functions (`assert_completed_session_inputs_locked`, `resolve_inputs`, `validate_coherence`) rather than inventing a second validation path.
4. Freshly-built session-scoped `financial_momentum`/`corporate_event_context`/`historical_context` artifacts are written to a new path under `operations-review/canonical-post-close-v1/<session>/enrichment/`, never over `daily_session_level2_package.session_artifact_paths`'s shared static paths for those three keys -- overwriting the shared path with one session's content would silently relabel retained prior-as-of evidence under its old filename, which the existing immutability/provenance doctrine forbids.
5. A real 2026-08-26 execution was attempted (DNSE credentials configured; a live P3F9B fetch genuinely returned 889/1,683 exact-session observations) and deliberately stopped before registration on explicit owner direction: configured credentials and API reachability are not by themselves proof of a completed session against the owner's ~18:00 Asia/Ho_Chi_Minh operational collection cutoff, which is not encoded anywhere in the existing `resolved_completed_session` wall-clock heuristic. No session was registered or frozen; verified zero mutation to the registry or to `dashboard-runtime`. The partial `operations-review/*-20260826*` artifacts are retained as evidence and are safely resumable.

## 2026-08-26 - Canonical Post-Close Live Validation Closeout V1

`CANONICAL_POST_CLOSE_ONE_COMMAND_PIPELINE_V1 = LIVE_VALIDATED_COMPLETE / READY_FOR_OWNER_RUNTIME_MATERIALIZATION` (`push = NO`, runtime replay and publication remain separate owner-governed actions).

1. The governed live run used DNSE as its only canonical acquisition route. The exact-session snapshot requested at `2026-08-26T19:19:00.376043+07:00` resolved and retained `2026-08-26`, with 889/1,683 exact-session observations. Required current-session lineage passed the registry/completion gate; no VCI, KBS, or VNStock route entered canonical-post-close. Earlier catalyst and undated retained fundamental inputs remain explicit, contract-accepted degraded context rather than substituted current-session market evidence.
2. The isolated `operations-review/canonical-post-close-v1/2026-08-26/post-close-attempt-191900/` output root supplied the current-session artifacts, while repository-relative tools executed from the Producer checkout. The registered session and the tiered session/opportunity/full-universe/dashboard-release manifests reconcile to operation `daily_research_session_operation:1883a16b50f0ef2d8e367391811ad164c1742532b7d4ae3c72fe6e3c218c30e0`, run `daily_producer_run:9f8dcbb36d9428ff772d94a3dec85d96d0a573e39d5905b433c7ba28ffb856b0`, packet `current_research_decision_packet:ed1bfde1a066f7f311fdeec67ccc200b98f05286152560b79563423c0919d176`, prospective cohort `prospective_research_cohort_snapshot:6b98b3925a2bb836cde294b85e61a2bb514b6ff6992d29126b911a7cfdfa877c`, and dashboard projection `dashboard_decision_cockpit_projection:60ceac63b713c916cb95af9c8fa7b272bedd1383b38c8dcd1fc0505e64c1b9d4`. Manifest self-verification, delivery hashes, and Consumer parity are all `PASS`.
3. The actual same-session technical coverage is 887 over the 1,506 current active-equity denominator (889 observed-session cohort). CCV and UEM no longer block completion: each extended-history record is `INSUFFICIENT_HISTORY_AFTER_EXTENDED_LOOKBACK` with `attempt_count=1`. This proves structural insufficiency, not a successful retry; the new bounded retry path was not exercised in this run.
4. Two corrective lessons are retained in the operational contract: execution root and attempt artifact root are separate, and the technical-history caller makes at most two immediate additional attempts only for explicit transient DNSE transport failures. Semantic/data outcomes never retry; exhausted transport failures remain `FETCH_FAILED`, and `_assert_no_recoverable_same_session_technical_gap` remains fail-closed.
5. The earlier `DASHBOARD_RUNTIME_READY = YES` and `READY_FOR_GOVERNED_PUBLICATION = YES` claims were invalid: the canonical pipeline had not materialized the actual `dashboard-runtime` release inputs. `canonical_post_close_pipeline.evaluate_dashboard_runtime_readiness` delegates to `release_session_contract` for the publisher-required runtime files and requires the resolved runtime session to equal the explicit canonical session. `canonical_dashboard_runtime_release` is the selected bounded correction: it derives only direct retained facts (exact OHLC/session rows, official exchange metadata, tactical state, and breadth), explicitly marks unsupported legacy fields unavailable, verifies frozen identities/Daily Producer lineage/hashes, stages the complete release, validates it, and promotes only after success. It never calls DNSE, `vn_indicators`, `stock_analyzer`, or `export_ai_bundle`. The actual root remains 2026-08-25 until an owner authorizes the retained replay. Strict valuation, liquidity/sizing/execution, optional macro, explicit portfolio, RAW_AS_TRADED, PIT, ranking, recommendation, probability, target, sizing, execution, and backtest authority remain blocked, unpromoted, or not emitted. No M1 work is opened.
## 2026-08-28 - Owner-focus Image-only Corporate OCR Batch Scaleout V1

`OWNER_FOCUS_IMAGE_ONLY_CORPORATE_OCR_BATCH_SCALEOUT_V1 = OUTCOME_B_PARTIAL_EXCEPTION_SET` (`push = NO`).

1. **Bounded cohort and source route.** The batch deterministically selects only the seven retained, audited/consolidated, corporate image-only reports for PNJ/PVD/NVL/POW. FPT remains regression/current-state evidence, never a new batch target. No provider, network, database, dashboard, raw-lake, valuation, strategy, ranking, recommendation, sizing, execution, PIT, or authority change is permitted.
2. **Discovery is routing only.** One fixed sequential 50-DPI grayscale `vie+eng` Tesseract route scans at most the first 20 pages and terminates early only after independently anchoring every required statement family. It preserves candidate-page order and contributes no numeric value, unit, row, or period proof. The existing 240-DPI TSV geometry path remains the only image fact-qualification route.
3. **Retention and replay.** Qualified panel facts from prior generic `image_table_tsv_ocr_evidence_run/v1` artifacts are replayed only when issuer identity and exact document SHA lineage agree. Newly qualified facts reconcile non-overwriting against the current panel; collisions stay out of ingress. This run replays three prior FPT facts then adds four PNJ facts, with one PNJ exact corroboration and no value conflicts.
4. **Terminal exceptions are evidence.** PVD FY2022–FY2024 and POW FY2024 have no independently anchored statement page within the bounded routing route; NVL FY2024 has no unambiguous VND-only page-unit set. They are terminally recorded, not retried, guessed, or mapped through a ticker exception. The artifact reports seven document terminals and 63 metric terminals, both residual zero.
5. **Next gate.** A future owner-authorized capability may improve generic scanned-form routing or page-unit recognition. It must remain source-agnostic and preserve the no-guess/authority boundaries; this batch does not start it.

## 2026-08-28 - Financial Operational Proxy Foundation and Research Tier Activation V1

`FINANCIAL_OPERATIONAL_PROXY_FOUNDATION_AND_RESEARCH_TIER_ACTIVATION_V1 = OUTCOME_A_OPERATIONAL_FINANCIAL_PROXY_RESEARCH_TIER_ACTIVE` (`financial_operational_proxy.py`, `tests/test_financial_operational_proxy.py`, `tools/derive_financial_operational_proxy_foundation_v1.py`, `market_wide_current_fundamental_research.py`; `push = NO`).

1. **Pivot.** Financial-data semantics move from binary `NOT AUTHORITATIVE -> NOT USABLE` to fitness-for-use by evidence tier. Three explicit tiers: `OPERATIONAL_PROXY` (identifiable provider/source/ticker/period/canonical metric, no unresolved catastrophic contradiction, no citation required), `VERIFIED_RESEARCH_EVIDENCE` (corroborated by an exact-value match against the official panel, or the pre-existing `provider_financial_semantic_basis.classify_provider_exact_research_usable` citation-agreement route; still never silently authoritative), `AUTHORITATIVE_EVIDENCE` (the existing P3-F13 official-qualified path, passed through verbatim, unweakened). `EXACT_MATCH` upgrades `OPERATIONAL_PROXY` only to `VERIFIED_RESEARCH_EVIDENCE`, never to `AUTHORITATIVE_EVIDENCE`; `VALUE_CONFLICT` fails the conflicting observation closed and never overwrites the official fact (no call anywhere to `merge_document_qualified_facts_into_panel`).

2. **Fitness-for-use is six independent booleans, never one global `usable` flag.** `display_eligible` / `research_eligible` / `trend_eligible` / `valuation_research_eligible` / `authoritative_financial_eligible` / `pit_backtest_eligible`, each with its own reason codes. `valuation_research_eligible` is fact-specific -- true only when that exact fact's own currency and scale are independently known, never inferred from provider/library schema evidence alone (the closed `provider_financial_semantic_basis.py` zero-shapes-qualified finding is not reopened). `authoritative_financial_eligible` and `pit_backtest_eligible` are `False` for every `OPERATIONAL_PROXY` and `VERIFIED_RESEARCH_EVIDENCE` fact unconditionally.

3. **Scale-invariant vs absolute is the load-bearing distinction, not a blanket relaxation.** A same-ticker/same-provider/same-period/same-statement-scope pair of observations shares whatever unknown scale the provider applies, so a period-over-period growth or a same-representation ratio computed from that pair is invariant to the unresolved scale and may be `trend_eligible`/`research_eligible`. An absolute value is not: `market_cap/revenue`, P/S, EV/Sales, and EV/EBITDA remain exactly as blocked as before -- `market_wide_current_valuation_input_scaleout.py`'s `_financial_input` gate is untouched, and this module only reports whether a fact could feed valuation research, never wires itself into that gate. No scale is ever guessed to force a match: when currency/scale are unknown and a raw value disagrees with an official comparator, the classification is `NOT_COMPARABLE_UNIT`, never a guessed `EXACT_MATCH` or `VALUE_CONFLICT`.

4. **Five new derived scale-invariant metrics** (`net_margin`, `roa`, `roe`, `cash_flow_quality`, `leverage_debt_to_equity`) compute a ratio-and-trend series only from facts sharing provider + ticker + reporting_period + statement_scope. `roa`/`roe`/`cash_flow_quality` span two different statement families (income_statement/balance_sheet/cash_flow); each such derived record carries an explicit `CROSS_STATEMENT_FAMILY_SAME_SCALE_ASSUMED` warning distinguishing it from the strictly safer same-statement-family case (`net_margin`, `leverage_debt_to_equity`, both purely balance_sheet or purely income_statement). A derived result's evidence tier never exceeds its weakest required input's tier -- both inputs are always provider-tier, so a derived ratio is always `OPERATIONAL_PROXY`, never `VERIFIED_RESEARCH_EVIDENCE`, regardless of how clean the series looks.

5. **Sector safety is bounded, not solved.** Classification is scoped to `entity_type == "corporate"` this milestone; bank/securities/insurance/finance_company tickers receive `ENTITY_TYPE_NOT_SUPPORTED_THIS_MILESTONE` and zero facts by construction, consistent with `financial_fact_coverage_recovery.REQUIRED_IDENTITIES_BY_ENTITY` (which defines a structurally smaller, disjoint identity set for those sectors that provider raw observations do not currently expose). The bounded corporate identity set is reused verbatim from `financial_fact_coverage_recovery.CORPORATE_IDENTITIES` -- no new canonical metric name is invented, and bank/securities-specific names (`net_profit_parent`, `profit_after_tax_parent`, `total_equity`) never appear in it, preserving the existing total-vs-parent-attributable and total-equity-vs-parent-equity distinctions by construction rather than by new code.

6. **Real bounded proof (11 tickers, zero acquisition, zero OCR, zero network, offline against already-retained `operations-review/` bytes only).** FPT/HPG/NVL/PAN/PNJ/POW/PVD/VNM -- all owner-focus (`config/owner_research_focus.json`), all already `OFFICIAL_QUALIFIED` in the 13-issuer P3-F13 panel -- yield 307 real `OPERATIONAL_PROXY` facts and 5 real `VERIFIED_RESEARCH_EVIDENCE` upgrades (FPT/HPG/NVL/PAN/POW, each an independently reconciled `EXACT_MATCH`, not a synthetic fixture). VCB (bank) and SSI (securities) each independently confirm zero operational-proxy facts. A32 (corporate, confirmed zero retained provider financial source per the 2026-08-27 financial-fact-coverage-recovery artifact) confirms zero facts -- no value is fabricated for a ticker with no retained evidence. Official-qualified issuer count is unchanged at 13 before and after the new attach point is exercised.

7. **Research-consumer integration is one optional, read-only keyword.** `market_wide_current_fundamental_research.build_artifact()` gains `operational_proxy_by_ticker: Mapping[str, Mapping] | None = None`. Default `None` leaves every existing caller's output byte-identical to before this parameter existed (56 pre-existing tests across that module, its AI-bundle attach layer, and `financial_fact_coverage_recovery.py` re-run clean). When provided, it read-only-attaches each ticker's classification under `record["operational_proxy"]` and adds a top-level `operational_proxy_coverage` section that reports official (`EXACT_QUALIFIED`), verified-research, and operational-proxy fact counts *separately* -- they are never flattened into one count, and `authority_tier` dispatch is never touched.

8. **OCR/PDF scope.** The owner-focus image-only OCR batch scaleout completed at commit `6c6755f` is the final *default* OCR scale-out milestone. OCR/PDF extraction code and the official-financial-evidence pipeline it feeds are **not deleted and not deprecated**; they remain fully supported for triggered, bounded use: important owner-focus/portfolio candidates, provider conflict resolution (e.g. a future `VALUE_CONFLICT` this module surfaces), critical metric verification, PIT/audit-sensitive authority, and exceptional documents where official verification is worth the acquisition/OCR cost. What changes is only that broad, default-path PDF parsing is no longer how market-wide financial coverage grows -- that growth now runs through this milestone's provider-tier `OPERATIONAL_PROXY`/`VERIFIED_RESEARCH_EVIDENCE` research layer instead, with official/OCR evidence reserved for the trigger cases above.

9. **Vision policy -- architectural note only, nothing implemented.** No Vision LLM API is called or integrated in this milestone (verified by `tests/test_financial_operational_proxy.py`'s import-graph check). The recorded future escalation path, for a later, separately authorized milestone: `image document -> structured Vision extraction candidate -> deterministic accounting/reconciliation checks -> AI_EXTRACTED_RESEARCH_EVIDENCE`. AI extraction alone never becomes authoritative evidence at any point on that path -- it would still require the same kind of deterministic reconciliation this milestone's `reconcile_against_official` already performs before any tier upgrade, and it would still cap out below `AUTHORITATIVE_EVIDENCE` the same way `VERIFIED_RESEARCH_EVIDENCE` does today.

10. **Roadmap sequencing** (see `docs/ROADMAP.md` for the full entry): `FINANCIAL_OPERATIONAL_PROXY_FOUNDATION` (this milestone) -> `MARKET_WIDE_HISTORICAL_FUNDAMENTALS_SCALEOUT` -> `DETERMINISTIC_FUNDAMENTAL_FEATURES` -> `VALUATION_RESEARCH_EXPANSION` -> `OFFICIAL_VERIFICATION_ON_TRIGGER`, while `AUTHORITATIVE_EVIDENCE`/PIT financial evidence continues as a separate, harder, unweakened authority lane.

11. **Tests and verification.** 53 new tests in `tests/test_financial_operational_proxy.py` (all pass), covering tier distinctness, the upgrade contract, conflict fail-closed behavior, the six-boolean fitness-for-use shape, the scale-invariant/absolute distinction, period/scope incompatibility, sector-safety leak prevention (parametrized across bank/securities/insurance/finance_company/unknown, plus two real-data cases), derived-metric tier capping, deterministic content identity (operational timestamp excluded), and the absence of network/OCR/Vision/production-DB/Dashboard/VALUE-ranking-recommendation-target-probability-sizing-PIT code paths. 56 pre-existing tests across `tests/test_market_wide_current_fundamental_research.py`, `tests/test_export_ai_bundle_market_wide_current_fundamental_research.py`, and `tests/test_financial_fact_coverage_recovery.py` re-run clean, zero regressions. `python -m py_compile financial_operational_proxy.py market_wide_current_fundamental_research.py tools/derive_financial_operational_proxy_foundation_v1.py tests/test_financial_operational_proxy.py` and `git diff --check` are both clean.

12. **Next gate.** `MARKET_WIDE_HISTORICAL_FUNDAMENTALS_SCALEOUT` -- widen the same, unmodified architecture from this milestone's 11-ticker proof cohort to the full research universe. Not opened here; requires separate owner authorization per the standing one-session-one-milestone rule.
## 2026-08-28 - Market-wide Historical Fundamentals Scaleout V1

`MARKET_WIDE_HISTORICAL_FUNDAMENTALS_SCALEOUT_V1 = OUTCOME_B_MARKET_WIDE_SCALEOUT_PARTIAL_PROVIDER_CEILING` (`push = NO`).

1. The established provider-only operational-proxy contract replays all 523 current consumer tickers from retained canonical facts, with one terminal manifest record per ticker and residual zero.
2. Only 21 resolved corporate records emit 808 operational-proxy and 6 verified-research facts. The 502 bank/securities/finance-company/insurance/unknown records remain terminally sector-blocked; no corporate identity is applied to them.
3. The existing consumer attaches the proxy records read-only and keeps 94 official facts, 6 verified-research facts, and 808 operational-proxy facts separate. Authoritative issuer count is unchanged at 13 and valuation remains blocked where absolute semantics are unresolved.
4. The next shared capability is entity-class and sector-specific provider financial identity/semantic coverage; no provider addition, OCR/official scaleout, or authority-bearing downstream feature is authorized here.
## 2026-08-28 - Market-wide Fundamental Feature Activation V1

`MARKET_WIDE_FUNDAMENTAL_FEATURE_ACTIVATION_V1 = OUTCOME_B_FEATURE_ENGINE_ACTIVE_WITH_SHARED_INPUT_LIMITS` (`push = NO`).

1. The existing consumer entity resolver is the bounded retained-metadata precondition: 452 corporate / 28 bank / 33 securities / 7 insurance / 1 finance-company / 2 unknown. Unknown never defaults to corporate; all non-corporate and unknown records remain outside industrial formulas.
2. The existing operational proxy is replayed unchanged: proxy-ready records rise 21→449, facts 808→17,276, verified-research stays 6, and authoritative issuer count stays 13.
3. The feature envelope is per-feature and research-only. Current retained provider flow facts are quarterly, so annual YoY/CAGR/margin/cross-statement calculations and full Piotroski remain blocked instead of making an unsupported Q4-as-annual inference.
4. No authority is promoted. Future work should be an analysis capability using compatible retained annual/duration-evidenced inputs, not another tier, registry, or provider architecture milestone.
## 2026-08-28 - Market-wide Quarterly Fundamental Research Features V1

`MARKET_WIDE_QUARTERLY_FUNDAMENTAL_RESEARCH_FEATURES_V1 = OUTCOME_A_QUARTERLY_FUNDAMENTAL_FEATURES_MATERIAL_COVERAGE` (`push = NO`).

1. Retained period depth is quarterly, never annual by label alone. Same-period flow YoY is a labelled proxy when duration is unresolved; balance-sheet stocks retain point-in-time semantics.
2. EOP ratios are separately named research proxies: net margin 446, ROA/ROE 428, asset-turnover/DuPont 425, and equity multiplier 446. Standard average-balance ratios, TTM, and standard Piotroski remain blocked where their required semantics are absent.
3. Sector gates, evidence tiers, authoritative count (13), and valuation authority are unchanged. The next authorized direction is cross-sectional research scoring/ranking of comparable proxy features, not another data architecture milestone.
## 2026-08-28 - Fundamental Cross-Sectional Scoring and Ranking V1

`FUNDAMENTAL_CROSS_SECTIONAL_SCORING_AND_RANKING_V1 = OUTCOME_A_FUNDAMENTAL_CROSS_SECTIONAL_RANKING_MATERIAL_COVERAGE` (`push = NO`).

1. Independent research-only axes use existing operational-proxy quarterly features: profitability 449, capital efficiency 425, balance-sheet context 433, growth 2. Missing inputs are never neutral and one blocked axis never blocks another.
2. Data confidence is separate from investment quality. No composite/action is emitted; sector-relative results remain null without a sufficient retained comparable cohort.
3. Owner doctrine is recorded: capability-first market-wide research proceeds when fitness permits; non-authoritative does not mean unusable; stronger authority/PIT gates stay local; PDF/OCR is verification fallback; and pure schema/audit work is disfavored absent an integrity blocker.
## 2026-08-28 - Current Valuation Research Proxy and Relative-Value Axis V1

`CURRENT_VALUATION_RESEARCH_PROXY_AND_RELATIVE_VALUE_AXIS_V1 = OUTCOME_B_VALUATION_AXIS_ACTIVE_WITH_INPUT_LIMITS` (`push = NO`).

1. Retained provider-issued-share valuation proxies are current-only research inputs, never authoritative outstanding shares or PIT valuation.
2. Corrective continuation: market cap and EV are size contexts, never relative-value inputs. Relative value has 9 research-ready multiple records; lower-positive multiples are descriptive percentiles only, while negative/nonmeaningful multiples are unranked.
3. Authoritative count and valuation strategy authority remain unchanged. Next analysis capability: `FUNDAMENTAL_PLUS_MARKET_OPPORTUNITY_RANKING_V1`.

## 2026-08-28 - Action Instrumentation and Invalidation Precision V1

`ACTION_INSTRUMENTATION_AND_INVALIDATION_PRECISION_V1 = OUTCOME_B_ACTION_INSTRUMENTATION_IMPROVES_PRECISION_WITH_READY_LIMITS` (`action_instrumentation.py`, `tools/run_action_instrumentation_v1.py`; `push = NO`).

1. Action instrumentation is a third independent experiment dimension after shadow posture and readiness.  It exposes only the existing tactical classifier's exact `ma_20` and momentum-sign intermediates, along with session, adjusted-retrospective price basis, rule identity, source metric, and retained technical lineage.  No rule, technical indicator, price basis, or strategy is changed.
2. Exact boundaries are posture-specific: R6 early reversal may use MA20 reclaim for confirmation and momentum-zero failure for risk; R2/R3 trend states use their existing MA20/momentum state transitions; adverse R4/R5/R9 states use recovery/reversal, never a bullish stop.  Disjunctive R7 and categorical states remain conditional rather than being reduced to invented support, pivot, MA, ATR, or price levels.
3. The current replay yields 33 exact entry/confirmation, 130 exact technical-risk, and 70 exact posture-reversal boundaries.  It leaves 0 fundamental boundaries READY because no margin-led compatible baseline intersects the current case cohort and no other thesis-linked future-test numerical condition exists.  Thus complete positive/speculative instrumentation and `READY_SHADOW` remain zero; 446 substantive records remain conditional and 77 remain not-ready.
4. `market_wide_current_fundamental_research.build_artifact()` adds an optional read-only `action_instrumentation_by_ticker` attachment.  It is separate from facts, features, tactical state, valuation, opportunity research, cases, and shadow readiness; it cannot promote authority.  No recommendation, target, probability, sizing, leverage, PIT, valuation, RAW_AS_TRADED, provider, or official-evidence authority is opened.
5. The next authorized capability is retained action instrumentation / thesis-compatible fundamental invalidation precision.  It is not a justification to reopen generic acquisition, KBS lookback, TTM scaleout, or OCR.

## 2026-08-28 - Fundamental Thesis Invalidation Precision V1

`FUNDAMENTAL_THESIS_INVALIDATION_PRECISION_V1 = OUTCOME_A_FUNDAMENTAL_INVALIDATION_UNLOCKS_READY_SHADOW` (`fundamental_thesis_invalidation_precision.py`, `tools/run_fundamental_thesis_invalidation_precision_v1.py`; `push = NO`).

1. Exact current production/research qualification rules may be reused as future-monitoring state transitions only when their actual corporate cohort, cohort size, `AVAILABLE_FUNDAMENTAL_AXIS_MEAN/v1` method, current as-of value, scope, and comparison contract are retained. The only current exact quality thresholds are top-20% for initiate, high-quality 0.75 for accumulate/high-quality wait, and bottom-quartile recovery for avoid; no sector percentile is claimed and no financial cutoff is introduced.
2. The replay has 125 `READY` fundamental boundaries (55 quality-threshold transitions and 70 avoid-recovery transitions), 321 conditional, and 77 unavailable. All ready rules are currently `NOT_TRIGGERED`; missing future observations do not become triggers. Sign, margin-relative-drawdown, axis-state, and balance-sheet-state boundaries are zero because no current case satisfies their thesis-linkage and compatible retained-contract requirements.
3. `HIGH_RISK_SPECULATION_CANDIDATE` remains a warning-only `FUNDAMENTAL_RISK_STATE` with a conditional boundary, not a fabricated positive-quality thesis. `AVOID_CANDIDATE` retains recovery/reversal semantics and never becomes SELL.
4. Fundamental precision is consumed by the existing `shadow_action_readiness` and `action_instrumentation` contracts. It changes no posture: 40 records satisfy the unchanged full technical-plus-fundamental `READY_SHADOW` contract (13 initiate, 27 accumulate); 406 are conditional and 77 not-ready. WAIT remains independent of boundary precision.
5. All outputs remain experiment/shadow-only attachments. There is no recommendation, action, target, probability, sizing, leverage, valuation, provider/official-evidence, or PIT promotion. If authorized, the only next action-lane capability is a bounded shadow security-recommendation contract.

## 2026-08-28 - A1 Bitemporal Semantic Contract V1

`A1_BITEMPORAL_SEMANTIC_CONTRACT_V1 = OUTCOME_A_BITEMPORAL_SEMANTIC_CONTRACT_ACTIVE` (`bitemporal_semantic_contract.py`, `tools/run_a1_bitemporal_semantic_contract_v1.py`; `push = NO`).

1. Valid time, qualified official publication, provider reported/update/event time, first observed receipt, and pipeline processing/verification are permanently separate fields. Missing temporal evidence remains `UNKNOWN`; processing time, file metadata, Git time, and provider metadata never substitute for raw receipt or qualified publication.
2. A qualified exact public timestamp resolves through the governed EOD-session contract. A qualified date-only publication has no exact knowledge timestamp and resolves only to the strictly next governed session. First-observed fallback is explicitly `FROM_FIRST_OBSERVED_FORWARD_ONLY`; it cannot backdate an old fiscal fact.
3. `completed_market_session_gate.py` supplies the reused 18:00 Asia/Ho_Chi_Minh `OWNER_OPERATING_CONVENTION_V1` safety cutoff for completed-EOD research, not an exchange-close fact. EOD research-session availability never grants same-session closing-price execution, which is `NOT_ESTABLISHED`.
4. KBS `ReportDate` is `PROVIDER_REPORTED_REPORT_DATE`; KBS `LastUpdate` is provider record-update metadata and preserves timezone uncertainty. DNSE `lastUpdated` is provider event time; it never substitutes for receipt, and a provider time later than first receipt is surfaced as `PROVIDER_CLIENT_CLOCK_CONFLICT`.
5. Derived records inherit the latest required resolved research-session bound. Required unknown knowledge fails closed; optional unknown enrichment is retained but cannot block the core derived record. Existing KBS restatement-variant semantics are preserved without a universal revision ledger.
6. The bounded retained official panel may support only retained-panel temporal replay. It does not promote `ADJUSTED_RETROSPECTIVE`, `RAW_AS_TRADED`, historical price PIT, corporate-action/ex-date inference, historical backtesting, recommendation, or portfolio authority. A2 remains future prospective ingestion-retention work.

## 2026-08-29 - A2 Provider Publication and First-Seen Retention V1

`A2_PROVIDER_PUBLICATION_AND_FIRST_SEEN_RETENTION_V1 = OUTCOME_B_PROVIDER_TEMPORAL_RETENTION_ACTIVE_WITH_HISTORICAL_CEILING` (`temporal_retention.py`, `tools/run_a2_provider_publication_first_seen_retention_v1.py`; `push = NO`).

1. `provider_temporal_retention/v1` is the sole prospective raw-receipt envelope for the bounded active paths. It records immutable raw identity, UTC receipt/first observation, direct source publication with explicit authority tier, provider report/update/event fields, HTTP response metadata, source identity, acquisition method, and warnings. Raw receipt is captured at the byte/message boundary with an injected clock-capable API; no new scattered clock semantics are introduced.
2. The landing manifest merges identical raw identity re-observations by retaining the earliest first observation monotonically and preserving later receipt metadata. Different bytes are distinct observations; the existing `supersedes_sha256` link remains restricted to a directly observed changed hash under the same logical identity. No generic revision chain is fabricated.
3. Governed official-document acquisition can project qualified official publication only when both explicit qualification and issuer/exchange authority are supplied. KBS `ReportDate`/`LastUpdate`, DNSE `lastUpdated`, and HTTP `Date`/`Last-Modified`/`ETag` remain provider/transport provenance and never substitute for official publication. KBS legacy sidecars retain raw identity and provider dates but deliberately remain receipt-unknown.
4. A1 projection is attached to governed official documents, KBS sidecars, DNSE prospective shadow observations, and offline corporate-event imports. Its temporal fitness is explicit: qualified exact publication, qualified date-only publication, first-observed-forward-only, or blocked legacy/unknown. It does not grant `ADJUSTED_RETROSPECTIVE`, `RAW_AS_TRADED`, historical price PIT/backtests, same-close execution, valuation, recommendation, target, probability, sizing, or portfolio authority.
5. The next shared capability, only with owner authorization, is `A3_ASOF_QUERY_AND_REVISION_LEDGER_V1`: query retained records as of their explicit availability and introduce a bounded revision ledger only where stable logical identities and revision evidence exist. It must not backfill old receipt time or reopen acquisition.

## 2026-08-28 - Shadow Action Readiness V1

`SHADOW_ACTION_READINESS_V1 = OUTCOME_B_SHADOW_POSTURES_ACTIVE_WITH_READINESS_LIMITS` (`shadow_action_readiness.py`, `tools/run_shadow_action_readiness_v1.py`; `push = NO`).

1. `SHADOW_POSTURE` and `ACTION_READINESS_GATE` are two independent, read-only experiment dimensions over the existing 523 research cases.  Candidate labels are strictly `INITIATE_CANDIDATE`, `ACCUMULATE_CANDIDATE`, `WAIT_FOR_CONFIRMATION_CANDIDATE`, `HIGH_RISK_SPECULATION_CANDIDATE`, `AVOID_CANDIDATE`, or `INSUFFICIENT_ACTION_EVIDENCE`; none is a recommendation or portfolio instruction.  No opaque composite is produced.
2. The deterministic posture table uses only existing terminal case disposition, actual corporate-comparable quality percentile, tactical state/rule, and separately retained negative evidence.  `INITIATE_CANDIDATE` requires a top-20% actual corporate cohort percentile plus `BREAKOUT_READY`/`EARLY_REVERSAL_CANDIDATE`; `ACCUMULATE_CANDIDATE` requires a high actual-corporate percentile plus an existing base/uptrend state; high-risk speculation takes precedence over avoid for the constructive-setup/bottom-quartile warning cohort.  Market-only records never inherit a fundamental-quality claim and terminate insufficient-action-evidence.
3. Readiness never rewrites posture.  `READY_SHADOW` requires both pre-existing invalidation channels `READY`; it is correctly zero.  A substantive posture with both retained conditional rule identities is `CONDITIONAL_SHADOW` (446), while unavailable invalidation or insufficient case evidence is `NOT_READY_SHADOW` (77).  Missing catalyst, valuation, or TTM neither forces WAIT nor changes readiness by itself.  No price level, financial threshold, scenario support, sector rank, or event catalyst is fabricated.
4. `market_wide_current_fundamental_research.build_artifact()` accepts a backward-compatible optional `shadow_action_readiness_by_ticker` attachment.  It reports this shadow layer separately and cannot flatten it into facts or alter evidence tier, fitness, valuation, technical state, opportunity research, case state, or authority.  The authoritative issuer count remains 13; no recommendation, target, probability, sizing, leverage, PIT, or valuation authority is granted.
5. The next capability if owner-authorized is action instrumentation / invalidation precision (retained deterministic technical boundaries and thesis-related compatible fundamental triggers), not another general financial-data acquisition or semantic audit.

## 2026-08-28 - Thesis, Catalyst, Downside, and Dual Invalidation V1

`THESIS_CATALYST_DOWNSIDE_AND_DUAL_INVALIDATION_V1 = OUTCOME_B_RESEARCH_CASE_LAYER_ACTIVE_WITH_CATALYST_OR_INVALIDATION_LIMITS` (`thesis_catalyst_downside_research_cases.py`, `tools/run_thesis_catalyst_downside_research_cases_v1.py`; `push = NO`).

1. The research-case universe is exactly the 523-record opportunity artifact, terminal and residual-zero.  It emits separate thesis archetype/evidence, current market setup, optional valuation and TTM context, catalyst, counter-thesis evidence, evidence gaps, confidence, and technical/fundamental invalidation channels; it does not emit a global attractiveness score or decision output.
2. Corrective set semantics: terminal dispositions are exactly and mutually exclusively 446 `OPPORTUNITY_CASE_ELIGIBLE`, 73 `MARKET_ONLY_RESEARCH_CASE`, and 4 `INSUFFICIENT_CASE_EVIDENCE`; their exact ticker sets, empty pairwise intersections, union 523, and residual zero are emitted in the artifact.  The prior 8 insufficient count was a coverage-counter collision between a terminal disposition and a similarly named readiness label, not an eligibility change.  Missing valuation, TTM, growth, Piotroski, audit, or catalyst evidence is an explicit gap and is never converted into negative performance.
3. Corrective catalyst semantics: 42 tickers / 45 retained official event records are `RETAINED_EVENT_CONTEXT`, not catalysts.  A `QUALIFIED_CATALYST` requires retained event identity/type/status, effective/expected date, knowledge availability, explicit thesis linkage, causal-thesis reason, and source identity together; the current corpus has 0.  Technical state is a separate 159-record `MARKET_CONFIRMATION_TRIGGER`, never a corporate catalyst.  The retained event contract remains non-event-driven: no price impact, probability, target, entry, sizing, or decision authority follows.
4. The tactical classifier retains state/rule identity but no explicit structural price boundary, so every eligible technical invalidation is `CONDITIONAL`, with a null threshold rather than an invented support price.  Fundamental invalidation is thesis-related: a 20% relative net-margin drawdown is allowed only for margin-led quality archetypes with same-provider/scope/currency/scale/method-compatible rolling TTM income and revenue.  No real case meets both that compatible TTM condition and a margin-led archetype, so margin triggers and complete dual invalidations are both zero.  Audit risk remains zero because no retained qualified/adverse/disclaimer/going-concern evidence was consumed.
5. The existing fundamental consumer gains only an optional read-only `research_cases_by_ticker` attachment.  It reports attachment coverage separately and cannot alter facts, tiers, fitness, authority, valuation, tactical state, or opportunity research.  The authoritative issuer count remains 13 before/after; KBS lookback is closed/deferred at the known provider-depth ceiling.  The next decision-support step, if authorized, is a bounded action-readiness/recommendation contract—not another generic data audit.

## 2026-08-28 - Fundamental Plus Market Opportunity Ranking V1

`FUNDAMENTAL_PLUS_MARKET_OPPORTUNITY_RANKING_V1 = OUTCOME_A_FUNDAMENTAL_MARKET_OPPORTUNITY_RANKING_MATERIAL_COVERAGE` (`push = NO`).

1. The retained 523-name fundamental denominator is the matrix denominator and has residual zero. Fundamental quality uses only the already-computed profitability, capital-efficiency, and balance-sheet axes, averaging the available axes without imputing unavailable axes; sparse growth is explicitly excluded rather than neutralized or double-counted.
2. Market strength is a categorical read of the already-retained exact-session 2026-08-25 descriptive/tactical state. Market/tactical session mismatch fails closed. Tactical action fields are intentionally excluded; only state, structure, and rule identity are carried.
3. The result is a Pareto-style research bucket, not a universal score: quality, market/tactical setup, optional relative valuation, and data confidence remain independent. Negative tactical states preserve a `HIGH_QUALITY_WEAK_SETUP` outcome rather than being accidentally promoted by quality. `DATA_CONFIDENCE` never changes attractiveness.
4. Corrected valuation stays optional: only the 9 true-multiple records can enrich a result, market cap/EV remain size context, and the older 2026-08-21 price session is per-record warned and excluded from core buckets. Corporate formulas remain unavailable for the 71 non-corporate/unknown records.
5. `market_wide_current_fundamental_research.build_artifact()` accepts a backward-compatible, optional read-only `opportunity_research_by_ticker` attachment. It reports the attachment separately and cannot flatten downstream research into official facts or modify authority. No provider/acquisition/OCR/PDF/PIT/action/target/return/probability/sizing authority is opened; authoritative issuer count remains 13.
6. Material 446-name fundamental-plus-market overlap supports the next direct decision-support capability: `THESIS_CATALYST_DOWNSIDE_RESEARCH_V1`.
7. Same-milestone owner addendum permits two labels only where existing data supports them: `SUPER_SETUP_RESEARCH` requires `BREAKOUT_READY` or `EARLY_REVERSAL_CANDIDATE` and a top-20% quality percentile in the actual 449-name valid corporate cohort; `HIGH_RISK_SPECULATION` is a warning only, requiring an existing constructive setup and bottom-25% quality percentile in that same cohort. Both records carry `CORPORATE_VALID_FUNDAMENTAL_QUALITY_COHORT_EMPIRICAL_PERCENTILE/v1`; no sector-top-percentile claim, action, or sizing change is emitted.
8. Approved future intents, explicitly not implemented here: current TTM valuation research scale-out; implied-growth/reverse-valuation research; thesis/catalyst/downside research with dual technical and fundamental invalidation; and one-time workspace-topology convergence before the next Dashboard publication.

## 2026-08-28 - KBS Quarterly Financial Lookback and Semantic Retention V1

`KBS_QUARTERLY_FINANCIAL_LOOKBACK_AND_SEMANTIC_RETENTION_V1 = OUTCOME_C_EXISTING_KBS_ROUTE_CANNOT_SUPPLY_MATERIAL_LOOKBACK` (`kbs_quarterly_financial_retention.py`, `tools/run_kbs_quarterly_financial_retention_v1.py`; `push = NO`).

1. Stock Lookup now owns the bounded KBS KQKD quarterly retention contract rather than depending on a site-packages modification. It requests pages 1 and 2 with `pageSize=8`, `type=KQKD`, `termtype=2`, `unit=1000`, and retains exact bytes plus all returned `Head` metadata. The proof made ten public requests across HPG/CMG/CTD/SBT/SLS and later replays only those bytes.
2. Actual endpoint behaviour overrides the pagination hypothesis: page 1 is six headers, including a duplicate restatement period; page 2 is HTTP-200 empty for all five issuers. Distinct quarterly depth is HPG 4 and CMG/CTD/SBT/SLS 5, below the eight-quarter threshold. No Anti-Gravity market-wide acquisition is authorized from this ceiling.
3. Every returned, explicitly provider-labelled KQKD quarterly period is `STANDALONE_QUARTER` under the already approved endpoint contract. Raw `PeriodBegin`/`PeriodEnd` compact tokens remain retained but unnormalized because the proof exposes insufficiently reliable fiscal-calendar alignment; source scope labels produce 24 `CONSOLIDATED` and 6 `STANDALONE_PARENT` records. Currency remains unknown; KBS `unit=1000` and adapter ×1000 behaviour proves scale normalization only, not VND currency authority.
4. Restatement variants are preserved, never counted as separate quarters or silently discarded. Five period-level variants yield 99 conflicting and 2 equal raw line-item comparisons. Bounded bridge replay yields three revenue-only TTM records, zero net-income and zero both-flow TTM; the pre-existing full-universe 3/3/3 TTM coverage is unchanged.
5. No provider fact becomes authoritative, PIT, valuation, action, recommendation, target, probability, sizing, or Dashboard/runtime/database state. The route is closed for material TTM-depth scaleout; proceed to `THESIS_CATALYST_DOWNSIDE_AND_DUAL_INVALIDATION_V1` unless a separately authorized source supplies compatible retained depth.

## 2026-08-28 - Financial Flow Semantics and TTM Bridge Foundation V1

`FINANCIAL_FLOW_SEMANTICS_AND_TTM_BRIDGE_FOUNDATION_V1 = OUTCOME_B_TTM_SEMANTICS_PARTIAL_UNLOCK_WITH_DEPTH_LIMITS` (`financial_flow_semantics_ttm_bridge.py`, `tools/run_financial_flow_semantics_ttm_bridge_v1.py`; `push = NO`).

1. Flow duration is a distinct `flow_period_basis`, never a reinterpretation of `period_type`. Existing retained KBS KQKD quarter-endpoint evidence establishes `STANDALONE_QUARTER` only for its income-statement flows; retained canonical cash-flow resolver evidence may establish its own direct standalone basis; VCI duration remains `UNKNOWN`. Explicit future raw metadata can propagate through canonical facts, but no retained source field is manufactured from labels or values.
2. The deterministic derivation boundary permits only Q1=Q1-YTD, Q2=H1-YTD−Q1-YTD, Q3=9M-YTD−H1-YTD, Q4=FY−9M-YTD and `CURRENT_YTD + PRIOR_FULL_YEAR - PRIOR_SAME_PERIOD_YTD`, with exact ticker/metric/provider/scope/currency/scale compatibility. Missing or mismatched operands block; valid negative standalone flow is retained.
3. Market-wide replay is partial: 3 revenue and 3 net-income rolling-4Q TTM series, 56 OCF-only TTM series, and no YTD bridge. Exact EBITDA stays 0 because the retained canonical registry has no exact EBIT identity; no EBIT-context proxy can satisfy EBITDA/EV-EBITDA. All current/LFY valuation methods remain blocked by missing compatible denominators and unknown currency/scale.
4. TTM output is a separate optional consumer attachment at `OPERATIONAL_PROXY`; it cannot alter authority tier or enter VALUE, ranking, recommendation, target, probability, sizing, PIT, or backtest. Authoritative issuer count remains 13.
5. This is the retained-data ceiling for the current route, not an invitation to another generic semantic audit. Proceed to `THESIS_CATALYST_DOWNSIDE_AND_DUAL_INVALIDATION_V1` using the active opportunity matrix unless new compatible source evidence is separately authorized and retained.

## 2026-08-28 - Workspace Topology Convergence V1

`WORKSPACE_TOPOLOGY_CONVERGENCE_V1 = OUTCOME_B_CANONICAL_TOPOLOGY_ESTABLISHED_WITH_SAFE_RETIREMENT_BLOCKERS` (`push = NO`).

1. The canonical runtime is `C:\Projects\StockLookup\dashboard-runtime`; the sole canonical Dashboard source/publish checkout is `C:\Projects\StockLookup\market-dashboard` on `main` tracking `tungthanhnguyen2312-wq/market-dashboard`; and `tools/release_orchestrator.py` is the single supported live publication entrypoint. The invariant is one canonical runtime, one canonical checkout, and no alternate production publication path.
2. `release_checkout_identity.py` now supplies a runtime-root identity guard used by the Producer publisher, release publisher, and release orchestrator. Existing test-fixture mode remains the only isolated exception. Old relative fallback discovery is removed from the Producer dashboard publisher.
3. No physical retirement is safe for `dashboard-runtime`: its independent Git common dir is not shared with another worktree, but it has two unpushed commits plus tracked generated and untracked retained runtime WIP. Archive recovery repositories are clean and independent but preserved because they are retained deployment evidence. No runtime/database write, publication, deployment, reset, clean, rebase, or forced operation occurred.
## 2026-08-29 - Shadow Security Recommendation V1

`SHADOW_SECURITY_RECOMMENDATION_V1 = OUTCOME_A_SHADOW_SECURITY_RECOMMENDATION_ACTIVE` (`shadow_security_recommendation.py`, `tools/run_shadow_security_recommendation.py`; `push = NO`).

1. The 523-record deterministic packet contract is a pure projection of research cases, upstream shadow readiness, action instrumentation, fundamental invalidation, optional C1 risk, valuation, and A1/A2 temporal evidence. It emits one packet per input ticker with zero residual and self-verifying content identity.
2. Recommendation label and readiness remain distinct, upstream-controlled axes. The six labels are research-only and intentionally exclude BUY/SELL/HOLD. `AVOID_NEW_ENTRY` is a recovery-monitoring stance, never a sell/exit instruction; high-risk speculation remains warning-only and never obtains a positive fundamental thesis or speculative sizing.
3. Boundary readiness and current trigger state remain separate. An explicitly triggered positive-packet invalidation is an integrity conflict and fails that packet closed to `INSUFFICIENT_EVIDENCE`; the retained replay has zero such conflicts. No confirmation level, financial threshold, target, probability, or stop policy is invented.
4. Risk, valuation, and catalyst context are optional. C1 attaches only its existing per-security volatility context and cannot change a label; stale/unavailable valuation and absent catalyst do not suppress an otherwise ready packet. Full correlation/covariance content remains solely in C1.
5. Each packet explicitly prohibits personalized advice, execution, allocation, sizing, liquidity sizing, targets, probabilities, RAW_AS_TRADED, historical PIT, and backtest authority. Same-close execution remains `NOT_ESTABLISHED`. `export_ai_bundle.py` can attach verified packets only through an explicit opt-in path; default Producer bundles remain unchanged.
## 2026-08-29 - Current Portfolio Risk Research V1

`CURRENT_PORTFOLIO_RISK_RESEARCH_V1 = OUTCOME_A_CURRENT_RISK_RESEARCH_MATERIAL_ACTIVE` (`current_portfolio_risk_research.py`, `tools/run_current_portfolio_risk_research.py`; `push = NO`).

1. The contract is an optional current-research attachment over the recalculated 40-name `READY_SHADOW` cohort at the retained 2026-08-25 completed session. It preserves the upstream posture and readiness values verbatim; it does not create a posture, action, recommendation, or portfolio engine.
2. The only active horizons are exact 20/60/120/250 closing-price sessions, yielding 19/59/119/249 simple close-to-close returns respectively. No 252-session horizon or sqrt(252) annualization is admitted. Retained DNSE history is explicitly `ADJUSTED_RETROSPECTIVE`; RAW_AS_TRADED remains not promoted and PIT/backtest/execution authority remains blocked.
3. Pairwise Pearson correlation needs both names complete over the identical exact session window and is independent of candidate-set matrix readiness. The joint engine uses the natural complete intersection and is ready only after `T >= N + 5`, finite/symmetric covariance and correlation, unit correlation diagonal, full covariance rank, and finite condition number. No name is removed to improve diagnostics and no shrinkage, regularization, pseudo-inverse, eigenvalue clipping, or factor replacement occurs.
4. Current replay yields exact-ready counts L20/L60/L120/L250 of 40/34/34/26. L20 is correctly blocked (`N=40`, `T=19`); L60/L120/L250 are ready with their natural intersections. Sector context is descriptive candidate-set context only, never portfolio exposure, allocation policy, or concentration cap.
5. The artifact emits no holdings, weights, risk budget, position sizing, portfolio volatility, VaR/CVaR, execution, or recommendation fields. It remains a Producer-side retained artifact; existing research pipelines do not require it and remain unchanged when it is absent.

## 2026-08-29 - Correlation and Concentration Guard V1

`C2_CORRELATION_AND_CONCENTRATION_GUARD_V1 = OUTCOME_A_CURRENT_RESEARCH_CONTEXT_ACTIVE_NO_AUTHORITY_PROMOTED` (`correlation_concentration_guard.py`, `tools/run_correlation_concentration_guard.py`; `push = NO`).

1. C2 is a pure, generic, explicit-security-set projection of `current_portfolio_risk_research/v1`. Its API requires the caller to choose one frozen C1 lookback (20/60/120/250); it consumes retained pairwise rows, samples, source identity, and the C1 joint context verbatim and does not create a second return, covariance, or matrix-repair engine.
2. No existing authority established a correlation threshold. V1 therefore documents and freezes one transparent deterministic research heuristic only: a finite ready Pearson correlation strictly greater than `0.80` is an edge, and lexicographically ordered connected components are the concentration representation. It is neither empirical calibration, significance, probability, nor sizing/risk authority. Exact-threshold observations do not create an edge.
3. Every requested unordered pair is normalized and reported. Missing C1 material, unknown security identity, partial/not-ready material, malformed ready values, and contradictory duplicate C1 pair rows remain explicit fail-closed statuses; no convenient correlation is selected. Pairwise readiness remains independent of C1 joint-matrix readiness, so pair context survives a joint `T >= N + 5` block without manufacturing a joint matrix.
4. The retained 40-name READY_SHADOW L20 replay records 780 ready pairs and one strict-threshold edge: `BSR`/`GAS` at `0.8235585903592545`. It has one two-name `CORRELATED_PAIR_CONTEXT`, no three-or-more-name group, and carries the unchanged C1 L20 `JOINT_MATRIX_BLOCKED_T_RELATIVE_TO_N` (`T=19`, `N=40`) as a warning, not a blocker of usable pairwise context.
5. C2 may expose optional upstream recommendation label/readiness context only as an immutable pass-through check. It records mutation count zero and emits no BUY/SELL/HOLD, recommendation change, target, probability, holdings, weights, allocation, sizing, risk budget, order, or execution field. `ADJUSTED_RETROSPECTIVE` remains current-research-only; `RAW_AS_TRADED` is not promoted, historical PIT/backtesting stay blocked, and same-close execution is not established. Artifact: `operations-review/correlation-concentration-guard-v1-20260829/artifact.json`.

## 2026-08-29 - C2 Producer Bundle Serialization V1

`C2_CORRELATION_CONTEXT_PRODUCER_BUNDLE_SERIALIZATION_V1 = COMPLETE_LOCAL` (`export_ai_bundle.py`, `tests/test_export_ai_bundle_correlation_concentration_guard.py`; `push = NO`).

1. The routine `analysis_bundle.json` may carry the complete, existing `correlation_concentration_guard/v1` artifact only at top-level key `correlation_concentration_guard`. This exact shape is the Consumer adapter contract; Consumer, not Producer, selects a ticker's pairs and groups.
2. Attachment is disabled by default and preserves the byte-equivalent legacy bundle shape when not explicitly requested. An opt-in request requires both an explicit retained artifact path and an explicit supported lookback (20/60/120/250); the artifact's declared selected horizon, contract version, hash, and identity must all match or no C2 key is emitted.
3. The serialization boundary only verifies and deep-copies the retained artifact. It does not calculate returns, correlations, threshold crossings, components, group counts, or recommendation labels/readiness. Partial/not-ready observations retain their C2 null/status values without zero filling; the C2 recommendation-mutation audit remains zero.
4. The cross-repository test invokes the actual Consumer C2 adapter against the serialized root artifact only. There is no production import from Producer to Consumer, no Consumer or Dashboard change, no runtime-data write, and no authority promotion.
