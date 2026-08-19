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
| **P2** | Multi-Period Fundamentals & Sector Normalization | **IN PROGRESS (P2-A, P2-B, P2-C & P2-D2 Complete)** | `multi_period_financial_panel.py` deterministic panel & `generic_financial_canonicalizer.py` dictionary-driven scale-out.<br>• `P2-C` corporate evidence scale-out wave executed with authority-safe cohort (`GAS`, `MWG`, `VIC`, `VRE`), zero ticker-specific code (`f9ab8e98d2e691d8`).<br>• `P2-D2` official source registry promotion: `GAS` (`www.pvgas.com.vn`) and `VRE` (`ir.vincom.com.vn`) promoted under `issuer_ir` for `audited_annual_financial_statements`; `MWG` (`NOT_READY_REDIRECT_CHAIN`) and `VIC` (`NOT_READY_REPRODUCIBILITY`) remain unpromoted / blocked. |
| **P3** | Portfolio Sizing, Execution, Backtest | **FAIL-CLOSED** | Blocked until upstream price and liquidity qualifications are complete. |

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
12. **Phase 2-D2 Bounded Official Source Registry Promotion (GAS + VRE)** — **COMPLETE LOCALLY** (`config/official_source_registry.json`).
13. **Phase 2-D BCTC Template Recognition & Governed Official Document Expansion** — **NEXT PRODUCT MILESTONE**.

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
