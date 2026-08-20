# Stock Lookup — Architecture & Roadmap

> **Authoritative Technical Roadmap.** This document defines the engineering phases, milestone matrix, dependency contracts, and acceptance gates for Stock Lookup.
> Current operational state and immediate milestones are tracked in [STATE.md](STATE.md).

---

## 1. Architectural Phases

```
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 0: DATA FOUNDATION & PROVENANCE (P0-RECOVERY, P0-A, P0-B, P0-C)   │
│  - Raw lake ingestion, canonical universe, corporate actions, PIT price, │
│    volume semantics, and field-level temporal provenance contracts.      │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: RESEARCH EVIDENCE & FEATURE STORE EXPANSION (P1)               │
│  - Vectorized feature store, market internals, foreign flow scale-out,   │
│    and deterministic research evidence artifact generation.              │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: FUNDAMENTAL & VALUATION FOUNDATION (P2)                        │
│  - Sector-specific taxonomy packs, official filing multi-period OCR      │
│    materialization, and structured financial statement analysis.         │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: STRATEGY ENGINES, PORTFOLIO RISK & BACKTESTING (P3)            │
│  - Polymorphic strategy evaluation, cross-sectional ranking, calibrated │
│    scenarios, portfolio sizing, and point-in-time alpha validation.      │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Milestone Matrix & Status

| Program / Milestone | Description | Status | Acceptance Gate & Authority Constraints |
|---|---|:---:|---|
| **P0-RECOVERY** | Canonical Trades Materialization & Task 160 | **CLOSED** | `TERMINAL_SUCCESS_QUALITY_RESTRICTED`. 18.1M trades across 40 sessions. |
| **P0-A.1** | OHLC Raw Coverage Completion | **COMPLETE** | 1,528/1,660 successful; 132 `PERMANENT` provider-rejected failures classified. |
| **P0-A.2** | Corporate Action Evidence Scale-Out | **COMPLETE** | Official document authority & multi-event extraction integrated (`official_corporate_action_ledger.py`). |
| **P0-A.3** | Market-Wide PIT Price Reconstruction | **PART A COMPLETE / PART B BLOCKED** | • Part A: Multi-session WebSocket collection is `COMPLETE_EVIDENCE_ACQUIRED` (Sessions 1–4).<br>• Part B: Event-window qualification is `BLOCKED_PENDING_QUALIFIED_EX_DATE`.<br>• **`RAW_AS_TRADED = NOT_PROMOTED`**. |
| **P0-A.4** | Scoped Price-Basis Promotion | **DEFERRED** | Dependent on verified official ex-date notices. |
| **P0-B** | Qualified Volume/Liquidity Basis & Turnover | **CLOSED** | `TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION`.<br>• $C_5 = 10 \times G_1$ shadow empirical candidate (99.81%), unit `UNKNOWN`.<br>• 67 residuals unresolved.<br>• Traded value `OBSERVED_ABSENT`.<br>• **`QUALIFIED_LIQUIDITY_INPUTS = NO`**, **`POSITION_SIZING_IS_SAFE = NO`**. |
| **P0-C.1** | Canonical Instrument-Master Reconciliation | **COMPLETE** | Reconciled across 3,250 instruments (1,660 listed equity candidates, 1,590 unclassified). |
| **P0-C.2** | Universe-Tier Hierarchy & Exclusion Ledger | **COMPLETE** | `ACTIVE_UNIVERSE` fails closed as `UNKNOWN` pending verified exchange/listing evidence. |
| **P1** | Feature Store Normalization & Multi-Session Export | **COMPLETE** | `cross_sectional_export.py` normalized semantic taxonomy, multi-session export contract, fail-closed PIT/liquidity boundaries (`bb0cafa4417471b0`). |
| **P2** | Multi-Period Fundamentals & Sector Normalization | **COMPLETE (`P2_CLOSEOUT_COMPLETE`)** | `multi_period_financial_panel.py` deterministic panel & `generic_financial_canonicalizer.py` dictionary-driven scale-out.<br>• Integrates all authoritative Phase 2 financial fact cohorts: promoted corporate facts (`GAS`, `VRE`, `HPG`, `VNM`, `PAN`, `PVD`, `NVL`, `POW`, `QNS`), promoted VCB FY2024 bank scope (15 facts), promoted SSI FY2024 securities scope (16 facts), Layered Entity Classification Topology B (40 positive, 1,620 unpromoted fail-closed as UNKNOWN).<br>• Enforces strict sector boundaries, intermediary corporate debt ratio inapplicability (`NOT_APPLICABLE`), normalized `ENDING_EQUITY_ROE_PROXY`, zero synthetic observations, zero forward-fill, zero scope/currency mixing.<br>• Deterministic closeout artifact emitted: `p2_closeout_financial_panel_artifact.json` (`p2_closeout_financial_panel:46335e0b527ed39cbbcc8082508c85e86892f83137bf205f416e9d0bbbbc8eed`).<br>• Phase 3 entry evaluated: `PHASE3_ENTRY_READY_FOR_BOUNDED_REVIEW` with strict negative gates (`RAW_AS_TRADED = NOT_PROMOTED`, `QUALIFIED_LIQUIDITY_INPUTS = NO`, `POSITION_SIZING_IS_SAFE = NO`). |
| **P3** | Portfolio Sizing, Execution, Backtest | **FAIL-CLOSED (`P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE`)** | Blocked until upstream price and liquidity qualifications are complete.<br>• `P3-A` evaluated: No retained official document contains an explicit official ex-date (HPG, SSI, VCB, VNM state only record dates, payment dates, approval dates, or new-shares listing dates). Fail-closed invariant strictly prohibits inferring ex-dates from record dates or settlement rules.<br>• `RAW_AS_TRADED = NOT_PROMOTED`, `QUALIFIED_LIQUIDITY_INPUTS = NO`, `POSITION_SIZING_IS_SAFE = NO`. |
| **P3-B** | Sector-Aware Fundamental Quality & Research Readiness | **COMPLETE** | Independent price/liquidity-free research lane. The deterministic engine consumes only P2 authoritative facts, preserves calculation/evidence lineage and scope/currency/PIT gates, distinguishes exact results from ending-balance proxies, and applies corporate/bank/securities-specific metrics. It produces no score, ranking, valuation, strategy, or portfolio output. |
| **P3-C** | Multi-Period Comparative Financial Evidence Scale-Out | **PARTIAL** | SSI FY2023 audited consolidated filing is retained, SHA-256-verified, and replayed through the generic sector recognizer. Six facts were promoted, taking the panel from 102 to 108 qualified facts and upgrading SSI FY2024 ROA/ROE to exact average-denominator results. VCB FY2023 and corporate residuals remain unqualified; no CapEx proxy was introduced. |

---

## 3. Active Critical Path Sequence

Execution focus strictly follows the ordered critical path:

1. **P0-RECOVERY** — Canonical Trades Materialization: **CLOSED**.
2. **P0-C.1 / P0-C.2** — Canonical Universe Foundation & Hierarchy: **COMPLETE LOCALLY**.
3. **P0-A.2** — Corporate Action Official Evidence Ledger: **COMPLETE LOCALLY**.
4. **P0-A.3E** — Prospective Price Basis: Part A **COMPLETE**; Part B **BLOCKED FAIL-CLOSED**.
5. **P0-B.2D / P0-B** — Volume/Liquidity Scoped Review: **CLOSED (NO_AUTHORITY_PROMOTION)**.
6. **P0-C.3** — Field-Level Freshness & PIT Retrofit: **COMPLETE LOCALLY**.
7. **First Market-Wide Deterministic Analysis/Research Artifact** — **COMPLETE LOCALLY** (`market_analysis_artifact.py`).
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
23. **Phase 3-B Sector-Aware Fundamental Quality & Research Readiness** — **COMPLETE LOCALLY** (`fundamental_research_readiness.py`, `tools/run_p3b_fundamental_research_readiness.py`, `operations-review/p3b-fundamental-research-readiness-20260820/`). This does not relax P3-A or any price/liquidity gate.
24. **Phase 3-C Multi-Period Comparative Financial Evidence Scale-Out** — **PARTIAL LOCALLY** (`p3c_comparative_financial_evidence.py`, `tools/run_p3c_comparative_financial_evidence.py`, `operations-review/p3c-comparative-financial-evidence-20260820/`). Next bounded fundamental gate: P3-D official VCB FY2023 and residual corporate comparative facts, subject to registry approval and owner authorization.

---

## 4. Acceptance Gates for Subsequent Phases

### Opening Phase 1 (Research Evidence Layer):
- First market-wide deterministic analysis artifact generated and verified offline.
- Explicit schema declarations for all derived technical indicators.
- Vectorized cross-sectional snapshots preserve bound `TemporalField` envelopes.

### Opening Phase 2 (Fundamental & Multi-Period Accounting):
- Explicit taxonomy mappings for Banking (`BANK`), Securities (`SEC`), and Corporate (`CORP`).
- Verified audit and statement scope metadata (`consolidated` vs `parent_only`).
- Immutable page-level bounding box and OCR evidence provenance.

### Opening Phase 3 (Strategy & Backtesting):
- Unconditional fail-closed enforcement of `QUALIFIED_LIQUIDITY_INPUTS` and `POSITION_SIZING_IS_SAFE`.
- Complete separation between `PIT_AS_KNOWN` historical simulation and retrospective restatements.
- Point-in-time adjusted price series derived strictly from verified official dividend ex-date event windows (`P0-A.3E Part B` / `P3-A`).
