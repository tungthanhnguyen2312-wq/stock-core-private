# Stock Lookup — Operational State

> **Authoritative Operational Entrypoint.** Read this file in full before starting any implementation milestone.
> This document represents the cached current truth of the Producer repository.
> Historical troubleshooting details, run logs, and session-by-session forensics are preserved in `operations-review/`.

---

## 1. Executive Program State

- **Current Program**: Universal Market Data & Feature Foundation V1
- **Program Phase**: Foundation Complete → First Market-Wide Deterministic Analysis Artifact
- **Target Pipeline**:
  `Market Universe → Raw Ingest Lake → Quality / Canonical / PIT → Vectorized Feature Store → Feature-Level Eligibility → Strategy → Portfolio / Risk → AI Synthesis → Dashboard / Decision`

---

## 2. Program Priority & Foundation Status

| Program / Milestone | Description | Status | Key Governance Constraints |
|---------------------|-------------|--------|----------------------------|
| **P0-RECOVERY** | Canonical Trades Materialization & Task 160 | **CLOSED** | `TERMINAL_SUCCESS_QUALITY_RESTRICTED`. 18,109,141 canonical trades across 40 sessions. |
| **P0-A.1** | Market-Wide OHLC Raw Ingestion | **COMPLETE** | 1,528/1,660 successful (92.05%), 132 `PERMANENT` provider-rejected failures classified. |
| **P0-A.2** | Corporate Action Evidence Scale-Out | **COMPLETE** | Document-authority coverage & multi-event extraction integrated locally (`official_corporate_action_ledger.py`). |
| **P0-A.3** | Market-Wide PIT Price Reconstruction | **IN PROGRESS (Part A Complete / Part B Blocked)** | `P0-A.3A` contract, `P0-A.3B` read-only review, `P0-A.3C` payload acquisition, `P0-A.3D` collector hardening complete locally.<br>• `P0-A.3E` Part A (multi-session WebSocket collection) = **COMPLETE_EVIDENCE_ACQUIRED** (Sessions 1–4 retained; no further capture needed).<br>• `P0-A.3E` Part B (event-window price qualification) = **BLOCKED_PENDING_QUALIFIED_EX_DATE**.<br>• **`RAW_AS_TRADED = NOT_PROMOTED`**. |
| **P0-A.4** | Scoped Price-Basis Promotion | **DEFERRED** | Dependent on qualified event-window corporate-action notices. |
| **P0-B** | Qualified Volume/Liquidity Basis & Turnover | **CLOSED (NO_AUTHORITY_PROMOTION)** | `TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION`.<br>• $C_5 = 10 \times G_1$ shadow empirical candidate (99.81%), unit `UNKNOWN`.<br>• 67 residuals unresolved.<br>• Traded value `OBSERVED_ABSENT` from daily OHLC.<br>• **`QUALIFIED_LIQUIDITY_INPUTS = NO`**, **`POSITION_SIZING_IS_SAFE = NO`**. |
| **P0-C.1** | Canonical Instrument-Master Reconciliation | **COMPLETE** | Reconciled across 3,250 instruments (1,660 listed equity candidates, 1,590 unclassified). |
| **P0-C.2** | Universe-Tier Hierarchy & Exclusion Ledger | **COMPLETE** | `ACTIVE_UNIVERSE` fails closed as `UNKNOWN` pending verified exchange/listing-status evidence. |
| **P0-C.3** | Field-Level Freshness / As-Of Retrofit | **COMPLETE** | Pure deterministic contract ([field_temporal_contract.py](field_temporal_contract.py)); 6 explicit states; bound `TemporalField` containers on `CanonicalRecord` and `market_feature_store`. |
| **P1** | Feature Store Normalization & Multi-Session Export | **COMPLETE** | `cross_sectional_export.py` normalized semantic taxonomy, multi-session export contract, fail-closed PIT/liquidity boundaries, validated across 10 retained sessions (`bb0cafa4417471b0`). |
| **P2** | Multi-Period Fundamentals & Sector Normalization | **COMPLETE (`P2_CLOSEOUT_COMPLETE`)** | `multi_period_financial_panel.py` deterministic panel & `generic_financial_canonicalizer.py` dictionary-driven scale-out.<br>• Integrates all authoritative Phase 2 financial fact cohorts: promoted corporate facts (`GAS`, `VRE`, `HPG`, `VNM`, `PAN`, `PVD`, `NVL`, `POW`, `QNS`), promoted VCB FY2024 bank scope (15 facts), promoted SSI FY2024 securities scope (16 facts), Layered Entity Classification Topology B (40 positive, 1,620 unpromoted fail-closed as UNKNOWN).<br>• Enforces strict sector boundaries, intermediary corporate debt ratio inapplicability (`NOT_APPLICABLE`), normalized `ENDING_EQUITY_ROE_PROXY`, zero synthetic observations, zero forward-fill, zero scope/currency mixing.<br>• Deterministic closeout artifact emitted: `p2_closeout_financial_panel_artifact.json` (`p2_closeout_financial_panel:46335e0b527ed39cbbcc8082508c85e86892f83137bf205f416e9d0bbbbc8eed`).<br>• Phase 3 entry evaluated: `PHASE3_ENTRY_READY_FOR_BOUNDED_REVIEW` with strict negative gates (`RAW_AS_TRADED = NOT_PROMOTED`, `QUALIFIED_LIQUIDITY_INPUTS = NO`, `POSITION_SIZING_IS_SAFE = NO`). |
| **P3** | Portfolio Sizing, Execution, Backtest | **FAIL-CLOSED (`P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE`)** | Strictly blocked until upstream price/liquidity authorities pass.<br>• `P3-A` evaluated: No retained official document in the corpus contains an explicit official ex-date (HPG, SSI, VCB, VNM state only record dates, payment dates, approval dates, or new-shares listing dates). Fail-closed invariant strictly prohibits inferring ex-dates from record dates or settlement rules.<br>• `RAW_AS_TRADED = NOT_PROMOTED`, `QUALIFIED_LIQUIDITY_INPUTS = NO`, `POSITION_SIZING_IS_SAFE = NO`. |
| **P3-B** | Sector-Aware Fundamental Quality & Research Readiness | **COMPLETE (`P3_FUNDAMENTAL_RESEARCH_ENGINE_COMPLETE`)** | Independent price/liquidity-free lane over the 11-issuer authoritative P2 cohort. `fundamental_research_readiness.py` emits metric-level lineage, sector gates, exact/proxy status, data gaps, and `READY`/`PARTIAL`/`BLOCKED` fundamental-only readiness. It unlocks neither valuation nor strategy/ranking, price/liquidity, sizing, execution, or backtesting. Artifact: `operations-review/p3b-fundamental-research-readiness-20260820/p3b_fundamental_research_readiness_artifact.json`. |
| **P3-C** | Multi-Period Comparative Financial Evidence Scale-Out | **PARTIAL (`P3C_COMPARATIVE_EVIDENCE_SCALEOUT_PARTIAL`)** | Bounded official SSI FY2023 audited consolidated filing retained and SHA-256-verified; six generic-recognizer facts promoted (FVTPL assets, loans, total assets/equity, total/parent profit after tax). The refreshed panel rises from 102 to 108 qualified facts; SSI FY2024 ROA/ROE move from ending-balance proxies to exact average-denominator results. VCB FY2023 remains unacquired because the discovered host is not approved; corporate residual gaps and CapEx remain fail-closed. Artifact: `operations-review/p3c-comparative-financial-evidence-20260820/p3c_comparative_evidence_scaleout_artifact.json`. |
| **P3-D** | Residual Comparative Financial Evidence Scale-Out & Gap Reconciliation | **PARTIAL (`P3D_RESIDUAL_EVIDENCE_SCALEOUT_PARTIAL`)** | Reconciliation confirms P3-C's 55 gaps were correct by definition. Five retained, approved, audited consolidated HPG/PVD reports replay through the generic statement recognizer; ten exact facts (FY2022–23 HPG and FY2022–24 PVD revenue/total assets) raise the panel 108→118 and P3-B exact results 75→86. Gaps fall 55→42; HPG/PVD FY2022 ROE move from proxy to exact. VCB FY2023 is explicitly `VCB_FY2023_BLOCKED_SOURCE_NOT_APPROVED`; no registry mutation or CapEx proxy. Artifact: `operations-review/p3d-residual-comparative-financial-evidence-20260820/p3d_residual_comparative_evidence_scaleout_artifact.json`. |
| **P3-E** | Fundamental Coverage Closeout & Valuation-Input Readiness Gate | **COMPLETE (`P3E_FUNDAMENTAL_COVERAGE_CLOSEOUT_COMPLETE`)** | The comparative evidence lane is **CLOSED**. Six retained approved FY2024 reports (HPG, NVL, PAN, POW, QNS, VNM) supply twelve exact revenue/total-assets facts, lifting the panel 118→130 and exact P3-B outputs 86→94. The 29 remaining gaps are 28 structural history boundaries and one VCB FY2023 source-authority block. `valuation_input_readiness.py` is factual readiness only: market/PIT/share authority remains blocked, and no valuation was calculated. Artifact: `operations-review/p3e-fundamental-coverage-closeout-20260820/p3e_fundamental_coverage_closeout_artifact.json`. |
| **P3-F** | Current Market Valuation Basis Activation & Sector-Aware Valuation MVP | **PARTIAL (`P3F_VALUATION_RESEARCH_PARTIAL`)** | `p3f_current_market_valuation.py` freezes the latest retained DNSE `CURRENT_MARKET` session with explicit official share coverage: HPG on 2026-07-30. It activates descriptive-only HPG P/E, P/B, P/S, and EV/Sales from current adjusted-retrospective DNSE close × official current shares and qualified FY2024 financial facts. No price is promoted as `RAW_AS_TRADED` or historical PIT. The other ten issuers remain independently blocked by price/share evidence; VCB's retained DNSE payload is malformed. Bank/securities EV methods are not applicable, EBITDA/DCF remain blocked, and no recommendation, target, ranking, portfolio, or backtest is authorized. Artifact: `operations-review/p3f-current-market-valuation-20260820/p3f_current_market_valuation_artifact.json`. |
| **P3-F2** | Current Valuation Input Authority Foundation | **COMPLETE (`P3F2_CURRENT_VALUATION_INPUT_FOUNDATION_COMPLETE`)** | `current_valuation_input_authority.py` establishes generic DNSE current-price, explicit current-common-share, completed-session, corporate-action invalidation, valuation-input resolver, and read-only coverage-scanner contracts. It contains no ticker-specific production qualification branch and does not promote all DNSE instruments or share records. The cohort scan remains instance-scoped (1 current price ready, 0 current shares ready at the latest retained session); HPG is retained as a representative positive historical-current proof only. P3-F owns formulas and P3-G remains unchanged. Artifact: `operations-review/p3f2-current-valuation-input-authority-20260820/p3f2_current_valuation_input_authority_artifact.json`. |
| **P3-F3** | Operational Current Valuation Input Scale-Out | **PARTIAL (`P3F3_OPERATIONAL_VALUATION_INPUT_SCALEOUT_PARTIAL`)** | `tools/run_p3f3_operational_valuation_input_scaleout.py` executes data-driven materialization and qualification over the 11-issuer authoritative P3 cohort at session 2026-08-19. Price qualification lifts 1→11 (`PRICE_READY = 11`, `PRICE_BLOCKED = 0`, `ADJUSTED_RETROSPECTIVE`, `NOT_PROMOTED`). Share basis remains fail-closed (0/11 `SHARE_READY`, 11/11 `SHARE_BLOCKED`) because no issuer possesses verified official common-shares-outstanding coverage through 2026-08-19. Valuation rerun emits 0/11 valuation-ready issuers and 0 activated multiples for this session. Artifact: `operations-review/p3f3-operational-valuation-input-scaleout-20260820/p3f3_operational_valuation_input_scaleout_artifact.json`. |
| **P3-F4** | Generic Current Share Authority Root-Cause & Enablement | **COMPLETE (`P3F4_CURRENT_SHARE_FOUNDATION_COMPLETE`)** | `current_share_authority.py` makes the generic, evidence-driven effective-date timeline explicit and is integrated at P3-F2’s share boundary. Root cause is a combination: no scalable approved current-common source, provider `issue_share` is issued rather than outstanding and remains `NOT_PROMOTED`, legacy citation/manifest linkage cannot be safely remapped, and coverage/corporate-action proof ends before the valuation session. The read-only rescan remains `SHARE_READY = 0/11`, `BOTH_READY = 0/11`; P3-G remains reserved. Artifact: `operations-review/p3f4-generic-current-share-authority-20260820/p3f4_generic_current_share_authority_artifact.json`. |

---

## 3. Active Blockers & Invariant Governance Rules

1. **Price Basis Invariant**: `RAW_AS_TRADED` is **NOT PROMOTED**. Bounded REST OHLC remains `ADJUSTED_RETROSPECTIVE`. Unpromoted price fields fail closed for point-in-time backtesting.
2. **Liquidity & Turnover Invariant**: `QUALIFIED_LIQUIDITY_INPUTS = NO` and `POSITION_SIZING_IS_SAFE = NO`. Volume data is restricted to display and within-series analytics (`legacy.rel_vol`); it must never drive execution sizing or market liquidity metrics.
3. **Active Universe Invariant**: `ACTIVE_UNIVERSE` remains `UNKNOWN` for all instruments because DNSE feeds do not carry official exchange or listing-status proof.
4. **Temporal Freshness Invariant**: Freshness is determined by domain rules and market session calendars (`freshness_history.py`); naive `date < today => stale` is strictly prohibited.
5. **No Speculative Inference**: Ex-dates must never be inferred from record dates; debt fields must never be invented; missing independent measurements cannot be turned into evidence.

### 3.1 Global Readiness Rebaseline

- **`MINIMUM_VIABLE_ANALYSIS_SHADOW`** is available only for deterministic, current descriptive research with retained lineage. Every MVA artifact must carry: `is_actionable_for_execution=false`, `pit_backtest_eligible=false`, `liquidity_sizing_authority=BLOCKED`, and `valuation_scope=CURRENT_DESCRIPTIVE_ONLY`. It may operate while historical PIT, liquidity, and sizing remain blocked.
- **`FULL_DECISION_SUPPORT_READY`** requires all of the following, not merely an MVA artifact: current-share authority, canonical-universe authority, qualified volume/traded-value composition, historical RAW_AS_TRADED/PIT price and corporate-action authority, historical universe/entity PIT, liquidity/risk/sizing authority, and validated PIT backtesting.
- Any empirical active cohort is a **derived shadow denominator**, never `ACTIVE_UNIVERSE` authority. It must declare as-of date, lookback/window, source completeness, inclusion rule, and deterministic identity; no fixed count is governance truth.
- Current DNSE prices support bounded `CURRENT_DESCRIPTIVE_ONLY` use. Historical `RAW_AS_TRADED`/PIT remains unpromoted, and volume/traded-value composition remains insufficient for liquidity or sizing.
- `interbank_on_rate`, `sbv_net_injection_20d`, and `vn30f1m_basis` are source-qualification backlog fields only. No source authority or acquisition path is activated here.

---

## 4. Current Critical Path & Exact Next Action

### Rebaselined Active Gates

1. **P3-F5 current-share source-promotion review** — review only `VCI.overview.issue_share` (`ISSUED_SHARES`, `AUTHORITY=NOT_PROMOTED`) for semantic, effective-date, freshness, corporate-action, retention, and permitted-use evidence; no side-effect promotion.
2. **Minimum Viable Analysis shadow operating mode** — dual-mode artifact envelope and current descriptive research only.
3. **Canonical-universe / empirical-active shadow denominator** — derive a documented denominator without promoting it to canonical-universe authority.
4. **Volume/traded-value semantic authority** — establish market-composition semantics before any liquidity or sizing use.
5. **Current relative valuation/scenario** — future P3-G remains reserved; preserve sector-aware applicability (industrial CapEx/FCFF/EV does not gate bank/securities, which require their own P/B-ROE/residual-income-style contracts).
6. **Corporate-action plus historical RAW_AS_TRADED/PIT** — qualify event windows and historical price authority.
7. **Historical universe/entity PIT** — establish point-in-time inclusion and classification authority.
8. **Liquidity/risk/sizing** — only after volume/traded-value and PIT prerequisites qualify.
9. **PIT backtesting** — only after historical price, universe, entity, and liquidity authorities qualify.
10. **Deeper valuation/financial/sector/macro expansion** — subsequent bounded work; macro-liquidity fields remain qualification backlog.

The detailed historical critical path below is retained as implementation history; the ordered gates above govern new work.

### Ordered Critical Path:
1. `CANONICAL_TRADES_MATERIALIZATION` / P0-RECOVERY — **Closed** (`TERMINAL_SUCCESS_QUALITY_RESTRICTED`).
2. Canonical Universe Boundary (`P0-C.1` / `P0-C.2`) — **Complete Locally**.
3. Corporate Action Evidence (`P0-A.2`) — **Complete Locally**.
4. Prospective Price Evidence (`P0-A.3E` Part A) — **Complete**; Part B **Blocked Fail-Closed**.
5. Volume/Liquidity Scoped Review (`P0-B.2D` / P0-B) — **Closed** (`NO_AUTHORITY_PROMOTION`).
6. Field-Level Freshness & PIT Retrofit (`P0-C.3`) — **Complete Locally**.
7. First Market-Wide Deterministic Analysis/Research Artifact — **Complete Locally**.
8. **Phase 1 Feature Store Normalization & Multi-Session Export** — **COMPLETE LOCALLY** (`cross_sectional_export.py`, `bb0cafa4417471b0`).
9. **Phase 2-A Multi-Period Financial Fact Panel & Sector Applicability** — **COMPLETE LOCALLY** (`multi_period_financial_panel.py`, `33cfa0a4e5ee114e`).
10. **Phase 2-B Generic Financial Canonicalization & Retained Scale-Out** — **COMPLETE LOCALLY** (`generic_financial_canonicalizer.py`, `256f374c08df327b`).
11. **Phase 2-C Official Financial Evidence Scale-Out / First Corporate Acquisition Wave** — **COMPLETE LOCALLY** (`tools/run_p2c_corporate_evidence_scale_out.py`, `f9ab8e98d2e691d8`).
12. **Phase 2-D2/D2C Bounded Official Source Registry Promotion & Host Narrowing (GAS + VRE)** — **COMPLETE LOCALLY** (`config/official_source_registry.json`, `official_source_registry.py`).
13. **Phase 2-C2 Bounded Financial Evidence Onboarding (GAS + VRE)** — **SUPERSEDED** (Manual fact lineage replaced by P2-C2C).
14. **Phase 2-C2C Governed Financial Evidence Lineage Correction (GAS + VRE)** — **COMPLETE LOCALLY** (`tools/run_p2c2_corporate_evidence_onboarding.py`, `p2c2_governed_onboarding_report.json`).
15. **Phase 2-D Generic Financial Statement Template Recognition & Extraction Contract** — **COMPLETE LOCALLY** (`financial_statement_template_recognizer.py`, `p2d_generic_onboarding_report.json`).
16. **Phase 2-E Evidence-Backed Entity Classification Scale-Out Foundation** — **COMPLETE LOCALLY** (`evidence_backed_entity_classifier.py`, `p2e_entity_classification_artifact.json`).
17. **Phase 2-E3 Bounded Current-State Entity Classification Authority Promotion** — **COMPLETE LOCALLY** (`config/promoted_entity_classifications.json`, `p2e3_entity_classification_promotion_artifact.json`).
18. **Phase 2-F1 Sector Financial Taxonomy & Disclosure Parsing Foundation** — **COMPLETE LOCALLY** (`sector_financial_taxonomy.py`, `financial_disclosure_recognizer.py`, `p2f1_sector_financial_taxonomy_artifact.json`).
19. **Phase 2-F2 Sector Financial Authority Promotion Review** — **COMPLETE LOCALLY** (`P2F2_PROMOTION_RECOMMENDED`).
20. **Phase 2-F3 Bounded Generic Sector Extraction Authority Promotion** — **COMPLETE LOCALLY** (`config/promoted_sector_extractions.json`, `p2f3_sector_extraction_promotion_artifact.json`).
21. **Phase 2 Closeout & Market-Wide Financial Fact Panel Integration** — **COMPLETE LOCALLY** (`p2_closeout_financial_panel_artifact.json`, `p2_closeout_financial_panel:46335e0b527ed39cbbcc8082508c85e86892f83137bf205f416e9d0bbbbc8eed`).
22. **Phase 3-A Bounded Price Adjustment & Dividend Ex-Date Event Window Qualification** — **BLOCKED FAIL-CLOSED (`P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE`)**.
23. **Phase 3-B Sector-Aware Fundamental Quality & Research Readiness** — **COMPLETE LOCALLY** (`fundamental_research_readiness.py`, `p3b_fundamental_research_readiness_artifact.json`). P3-A remains independently blocked; this lane authorizes fundamental research readiness only.
24. **Phase 3-C Multi-Period Comparative Financial Evidence Scale-Out** — **PARTIAL LOCALLY** (`p3c_comparative_financial_evidence.py`, `tools/run_p3c_comparative_financial_evidence.py`, `p3c_comparative_evidence_scaleout_artifact.json`).
25. **Phase 3-D Residual Comparative Financial Evidence Scale-Out & Gap Reconciliation** — **PARTIAL LOCALLY** (`p3d_residual_comparative_financial_evidence.py`, `tools/run_p3d_residual_comparative_financial_evidence.py`, `p3d_residual_comparative_evidence_scaleout_artifact.json`). The authority remains annual, audited, consolidated, existing-cohort-only; it does not authorize price, liquidity, valuation, ranking, execution, or backtesting.
26. **Phase 3-E Fundamental Coverage Closeout & Valuation-Input Readiness Gate** — **COMPLETE LOCALLY** (`p3e_fundamental_coverage_closeout.py`, `valuation_input_readiness.py`, `tools/run_p3e_fundamental_coverage_closeout.py`). Comparative evidence is closed: no actionable current-window revenue/assets gap remains. This gate authorizes neither market-price/share basis, valuation calculation, scenarios, ranking, execution, nor backtesting.
27. **Phase 3-F Current Market Valuation Basis Activation & Sector-Aware Valuation MVP** — **PARTIAL LOCALLY** (`p3f_current_market_valuation.py`, `tools/run_p3f_current_market_valuation.py`, `operations-review/p3f-current-market-valuation-20260820/`). Exactly one current-market snapshot lane (HPG, 2026-07-30) is qualified; it does not alter P3-A or historical valuation authority.
28. **Phase 3-F2 Current Valuation Input Authority Foundation** — **COMPLETE LOCALLY** (`current_valuation_input_authority.py`, `tools/run_p3f2_current_valuation_input_authority.py`, `operations-review/p3f2-current-valuation-input-authority-20260820/`). This is an enablement gate under P3-F, not P3-G: generic contracts exist while evidence-instance qualification remains fail-closed.
29. **Phase 3-F3 Operational Current Valuation Input Scale-Out** — **PARTIAL LOCALLY** (`tools/run_p3f3_operational_valuation_input_scaleout.py`, `operations-review/p3f3-operational-valuation-input-scaleout-20260820/`). DNSE prices scale out 1→11 PRICE_READY at session 2026-08-19; shares fail closed 11/11 SHARE_BLOCKED.

### Exact Next Bounded Action:
P3-A remains blocked pending qualified ex-date evidence. The single recommended next gate is **P3-G — bounded scenario/relative-valuation research over the P3-F current-market artifact**, restricted to observed metrics and explicit unsupported states; it must not create target prices, probabilities, or portfolio output. Phase 3 execution and strategy layers remain fail-closed.

---

## 5. Operations & Evidence Reference Map

For historical investigation logs, forensic reports, and raw capture manifests, consult:
- **A3E Multi-Session Closeout**: [operations-review/p0-a3e-multi-session-closeout-20260819.md](../operations-review/p0-a3e-multi-session-closeout-20260819.md)
- **P0-B.2D Volume Review & Closeout**: [operations-review/p0-b2d-scoped-promotion-review-and-closeout-20260819.md](../operations-review/p0-b2d-scoped-promotion-review-and-closeout-20260819.md)
- **P0-B.2B1 Scale Validation**: [operations-review/p0-b2b1-scaled-g1-validation-residual-classification-v1-20260818.md](../operations-review/p0-b2b1-scaled-g1-validation-residual-classification-v1-20260818.md)
- **P0-B.2C Value Authority Gate**: [operations-review/p0-b2c-trading-value-input-authority-gate-v1-20260818.md](../operations-review/p0-b2c-trading-value-input-authority-gate-v1-20260818.md)
- **Task 160 Canonical Materialization**: [operations-review/task-160-canonical-materialization-v1-20260817/](../operations-review/task-160-canonical-materialization-v1-20260817/)
