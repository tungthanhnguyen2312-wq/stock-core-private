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
| **P1** | Foreign Flow Scale-Out & Feature Normalization | **DEFERRED** | Foreign trading V1 session retained; broader scale-out deferred. |
| **P2** | Multi-Period Fundamentals & Sector Normalization | **DEFERRED** | Official financial filings pipeline isolated under `data-landing/`. |
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
7. **First Market-Wide Deterministic Analysis/Research Artifact** — **COMPLETE LOCALLY** (`market_analysis_artifact.py`, `09c662b20944d25e77671a2972e5d515345310f17b585c6fa293241db5eb995d`).
8. **Phase 1 Feature Store Normalization & Multi-Session Export** — **CURRENT EXECUTION FOCUS**.

### Exact Next Bounded Action:
Implement **Phase 1 Feature Store Normalization & Multi-Session Export** (P1 feature schemas, vectorized indicator pipelines, and export bundle contracts).

---

## 5. Operations & Evidence Reference Map

For historical investigation logs, forensic reports, and raw capture manifests, consult:
- **A3E Multi-Session Closeout**: [operations-review/p0-a3e-multi-session-closeout-20260819.md](../operations-review/p0-a3e-multi-session-closeout-20260819.md)
- **P0-B.2D Volume Review & Closeout**: [operations-review/p0-b2d-scoped-promotion-review-and-closeout-20260819.md](../operations-review/p0-b2d-scoped-promotion-review-and-closeout-20260819.md)
- **P0-B.2B1 Scale Validation**: [operations-review/p0-b2b1-scaled-g1-validation-residual-classification-v1-20260818.md](../operations-review/p0-b2b1-scaled-g1-validation-residual-classification-v1-20260818.md)
- **P0-B.2C Value Authority Gate**: [operations-review/p0-b2c-trading-value-input-authority-gate-v1-20260818.md](../operations-review/p0-b2c-trading-value-input-authority-gate-v1-20260818.md)
- **Task 160 Canonical Materialization**: [operations-review/task-160-canonical-materialization-v1-20260817/](../operations-review/task-160-canonical-materialization-v1-20260817/)
