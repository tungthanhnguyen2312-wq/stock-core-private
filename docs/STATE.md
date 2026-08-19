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
| **P2** | Multi-Period Fundamentals & Sector Normalization | **IN PROGRESS (P2-A, P2-B, P2-C, P2-D2/D2C, P2-C2, P2-C2C, P2-D, P2-E & P2-E3 Complete)** | `multi_period_financial_panel.py` deterministic panel & `generic_financial_canonicalizer.py` dictionary-driven scale-out.<br>• `P2-C` corporate evidence scale-out wave executed with authority-safe cohort (`GAS`, `MWG`, `VIC`, `VRE`), zero ticker-specific code (`f9ab8e98d2e691d8`).<br>• `P2-D2/D2C` official source registry promotion: `GAS` (`www.pvgas.com.vn`) and `VRE` (`ir.vincom.com.vn`) promoted under `issuer_ir` strictly for `audited_annual_financial_statements` via generic `host_document_types` narrowing; `MWG` (`NOT_READY_REDIRECT_CHAIN`) and `VIC` (`NOT_READY_REPRODUCIBILITY`) remain unpromoted / blocked.<br>• `P2-C2C` governed financial evidence lineage correction: fully qualified and retained official documents, persisted qualification records (`official_document_qualification.py`), governed OCR sidecars (`annual_financial_ocr_materialization.py`), dynamic evidence extraction (`governed_financial_evidence_extraction.py`), generic canonicalization, multi-period panel integration with `ENDING_EQUITY_ROE_PROXY`, zero hardcoded facts, 100% verified citation lineage (`p2c2_governed_onboarding_report.json`).<br>• `P2-D` generic financial statement template recognition: pure deterministic recognition engine (`financial_statement_template_recognizer.py`), structure parsing (BS, IS, CF), period-column semantics, unit/scale discovery, Line 61 canonical parent net income, `TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT = 0`.<br>• `P2-E` evidence-backed entity classification scale-out foundation: pure deterministic classifier (`evidence_backed_entity_classifier.py`), multi-evidence fusion across legal charter / statement form codes / line item markers, fail-closed `UNKNOWN_ENTITY_CLASS`, zero hardcoded ticker logic, evaluated across 40 validation candidates (20 known baseline + 20 previously UNKNOWN listed equities), authority status `PROMOTION_REVIEW_READY` (`p2e_entity_classification_artifact.json`).<br>• `P2-E3` bounded entity classification authority promotion: Layered Authority Topology B adopted; 20 exact owner-approved records promoted to current-state authority (`config/promoted_entity_classifications.json`); seed baseline unchanged (20 seed + 20 promoted = 40 positive current-state, 1,620 listed UNKNOWN; historical PIT `NOT_ESTABLISHED`). |
| **P3** | Portfolio Sizing, Execution, Backtest | **FAIL-CLOSED** | Strictly blocked until upstream price/liquidity authorities pass. |

---

## 3. Active Blockers & Invariant Governance Rules

1. **Price Basis Invariant**: `RAW_AS_TRADED` is **NOT PROMOTED**. Bounded REST OHLC remains `ADJUSTED_RETROSPECTIVE`. Unpromoted price fields fail closed for point-in-time backtesting.
2. **Liquidity & Turnover Invariant**: `QUALIFIED_LIQUIDITY_INPUTS = NO` and `POSITION_SIZING_IS_SAFE = NO`. Volume data is restricted to display and within-series analytics (`legacy.rel_vol`); it must never drive execution sizing or market liquidity metrics.
3. **Active Universe Invariant**: `ACTIVE_UNIVERSE` remains `UNKNOWN` for all instruments because DNSE feeds do not carry official exchange or listing-status proof.
4. **Temporal Freshness Invariant**: Freshness is determined by domain rules and market session calendars (`freshness_history.py`); naive `date < today => stale` is strictly prohibited.
5. **No Speculative Inference**: Ex-dates must never be inferred from record dates; debt fields must never be invented; missing independent measurements cannot be turned into evidence.

---

## 4. Current Critical Path & Exact Next Action

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
18. **Phase 2-F BCTC Note & Disclosure Parsing / Sector Taxonomy Expansion** — **NEXT PRODUCT MILESTONE**.

### Exact Next Bounded Action:
Implement **Phase 2-F BCTC Note & Disclosure Parsing / Sector Taxonomy Expansion** (BCTC note segmentation, segment reporting, and bank/securities multi-statement templates).

---

## 5. Operations & Evidence Reference Map

For historical investigation logs, forensic reports, and raw capture manifests, consult:
- **A3E Multi-Session Closeout**: [operations-review/p0-a3e-multi-session-closeout-20260819.md](../operations-review/p0-a3e-multi-session-closeout-20260819.md)
- **P0-B.2D Volume Review & Closeout**: [operations-review/p0-b2d-scoped-promotion-review-and-closeout-20260819.md](../operations-review/p0-b2d-scoped-promotion-review-and-closeout-20260819.md)
- **P0-B.2B1 Scale Validation**: [operations-review/p0-b2b1-scaled-g1-validation-residual-classification-v1-20260818.md](../operations-review/p0-b2b1-scaled-g1-validation-residual-classification-v1-20260818.md)
- **P0-B.2C Value Authority Gate**: [operations-review/p0-b2c-trading-value-input-authority-gate-v1-20260818.md](../operations-review/p0-b2c-trading-value-input-authority-gate-v1-20260818.md)
- **Task 160 Canonical Materialization**: [operations-review/task-160-canonical-materialization-v1-20260817/](../operations-review/task-160-canonical-materialization-v1-20260817/)
