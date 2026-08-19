# Stock Lookup roadmap

> **Active roadmap, not an execution log.** Current operational state and the exact next bounded
> action are in [STATE.md](STATE.md). Historical milestone detail is retained in
> [DECISIONS.md](DECISIONS.md), ADRs, and `operations-review/`; historical cohorts and handoffs
> are **REFERENCE ONLY**, not default work queues.

## Canonical priority order (2026-08-17)

This is the binding execution sequence; it supersedes the "Active ordered workstreams" table below
as the **program-sequencing** authority. That table's technical detail remains valid and is cited
from the relevant sub-milestone below. See `docs/STATE.md` for current runtime/gate status and
`docs/DECISIONS.md` (2026-08-17 entry) for full rationale.

| ID | Milestone | Status |
| --- | --- | --- |
| P0-RECOVERY | Task 160 Trades Stage-B recovery/materialization | **Closed** — Stage-B and canonical Trades materialization both `TERMINAL_SUCCESS_QUALITY_RESTRICTED` |
| P0-A | Qualified price basis + corporate-action + historical PIT authority | Active (independent of P0-RECOVERY) |
| P0-A.1 | OHLC raw-coverage completion | **Complete** — 1,528/1,660 successful (92.05%), 132 `PERMANENT` provider-rejected, 0 retryable, 0 unclassified, 0 untouched |
| P0-A.2 | Corporate-action evidence scale-out | **Complete** — document authority and multi-event extraction integrated to local main (commit `a7e4a1ce7e8df1c24587c25f669393a5f0265b5e`, `push = NO`) |
| P0-A.3 | Market-wide PIT price reconstruction | **In progress** — P0-A.3A contract, P0-A.3B read-only review, P0-A.3C evidence acquisition, and P0-A.3D governed shadow hardening complete locally; P0-A.3E Part A prospective multi-session collection is complete (`COMPLETE_EVIDENCE_ACQUIRED`, Sessions 1–4 retained), while Part B event-window price-basis qualification is blocked pending a qualified ex-date; no price-basis promotion |
| P0-A.4 | Scoped price-basis promotion | Not started; depends on A.3 |
| P0-B | Qualified volume/liquidity basis + market-wide turnover | **In progress — not closed.** P0-B.2A_B2B: BLOCKED (C1–C4 fail across full 40-session/35,231-symbol-session corpus; root cause: ×10 scale mismatch + board composition mismatch). P0-B.2B1: `VALIDATED_SHADOW_SCALE_RELATION_WITH_UNRESOLVED_RESIDUALS` — C5=10×G1 matches 35,164/35,231=99.81% exactly (2× determinism confirmed, hash `ac5942913291c9ac8efb73d77a3b97dbb9068f111c8c6996422b66ef4e2b183d`); 67 residuals (62 POSITIVE_DELTA_MULTIPLE_OF_100, 5 NEGATIVE_DELTA_MINUS_4) unresolved; scale is EMPIRICAL_CANDIDATE only, semantic_unit=UNKNOWN, no authority promotion. P0-B.2C (va/turnover) NOT started / deferred. `QUALIFIED_LIQUIDITY_INPUTS` NOT emitted. P0-B.2D promotion review required before closing. |
| P0-C | Canonical market universe + exclusion ledger + freshness semantics | Foundation (C.1/C.2) and semantic qualification integrated to local main (commit `0f29019da83e83144f4f7f3832f054e04be66a97`, not pushed); security-group semantics qualified for ~99.6% of `UNKNOWN_SECURITY_GROUP`; exchange and listing/active status remain unqualified so `ACTIVE_UNIVERSE` stays fail-closed; C.3 not started — see `docs/STATE.md`'s P0-C.1/P0-C.2 foundation and semantic-qualification entries |
| P0-C.1 | Instrument-master reconciliation | **Promoted with bounded patch** (`b4e3c71` + patch); integrated to local main, not pushed |
| P0-C.2 | Universe-tier hierarchy / exclusion ledger | **Promoted with bounded patch** (`3d9a2ab` + patch); integrated to local main, not pushed; `ACTIVE_UNIVERSE` fail-closed `UNKNOWN` pending listing-status/exchange evidence (both investigated, both remain unqualified — see `docs/STATE.md`) |
| P0-C.3 | Field-level freshness/as-of retrofit | Next actionable milestone |
| P1 | Foreign-flow scale-out; UFS/feature-authority normalization; Research Evidence Layer; market-internals | Deferred |
| P2 | Sector/factor normalization; official multi-period fundamentals; operational robustness | Deferred |
| P3 | Return/risk, calibrated scenarios, sizing, backtest | Deferred; fail-closed until P0-A + P0-B pass |

`P0-A`, `P0-B`, and `P0-C` are independent, parallelizable lanes once started, but current
execution focus is **market-wide/full-universe data foundation first**, not single-ticker
artifact expansion — see `docs/STATE.md`'s `## CRITICAL PATH` for the full ordered chain.
`CANONICAL_TRADES_MATERIALIZATION` and P0-RECOVERY close are both **complete**
(`TERMINAL_SUCCESS_QUALITY_RESTRICTED`). Canonical universe boundary foundation
(`P0-C.1`/`P0-C.2`) and semantic-evidence qualification are integrated to local
`stock-core-private` main (commit `0f29019da83e83144f4f7f3832f054e04be66a97`, fast-forward, not
pushed to `origin`); that pass resolved ~99.6% of the `UNKNOWN_SECURITY_GROUP` population but left
exchange and listing/active-status semantics unqualified, so `ACTIVE_UNIVERSE` remains fail-closed
for every instrument — see `docs/STATE.md`'s P0-C.1/P0-C.2 foundation and semantic-qualification
entries for exact scope, verified numbers, and remaining blockers. `P0-A.3B` (DNSE Prospective
PIT Price Authority Architecture Review) is **COMPLETE_READ_ONLY** with verdict
`SOURCE_SEMANTICS_BLOCKED`: no current DNSE source/feed/field is authoritative `RAW_AS_TRADED`.
`P0-A.3C` is **COMPLETE_EVIDENCE_ACQUIRED** from the retained real HPG/VCB WebSocket `bc` payload
run; its result does not promote price basis. `P0-A.3D` is **COMPLETE_LOCAL_NO_PUSH** as governed
`EXPERIMENT_SHADOW_ONLY` collector hardening, including local commit `ecb2c6c` which corrected
routine ping keepalive exhaustion of the semantic receive budget and was subsequently live
validated through governed A.3E capture. Active gate: `P0-A.3E` — **Prospective Multi-Session /
Event-Window Price-Basis Qualification** (`PART_A_COMPLETE_EVIDENCE_ACQUIRED`,
`PART_B_BLOCKED_PENDING_QUALIFIED_EX_DATE`, `NO_PRICE_BASIS_PROMOTION`).

- **A. PROSPECTIVE_MULTI_SESSION_COLLECTION** — `COMPLETE_EVIDENCE_ACQUIRED`:
  Sessions 1 through 4 have acquired distinct, multi-session governed evidence for HPG and VCB
  (including partial sessions with honest expected `BLOCKED_NO_COMPLETED_EVENT` outcomes without failure).
  No additional prospective acquisition is required.
- **B. EVENT_WINDOW_PRICE_BASIS_QUALIFICATION** — `BLOCKED_PENDING_QUALIFIED_EX_DATE`: no ex-date
  may be inferred from record date, and unavailable event evidence remains fail-closed.

`RAW_AS_TRADED_NOT_PROMOTED`,
`OFFICIAL_CLOSED_BAR_FINALITY_DOES_NOT_BY_ITSELF_PROVE_RAW_AS_TRADED`, and
`NO_REVISION_OBSERVED != IMMUTABLE` remain binding. A.3E Part A complete / Part B blocked → `P0-C.3` (freshness/as-of retrofit) / `P0-B` → first
market-wide deterministic analysis artifact. P0-A.1, P0-A.2, P0-A.3A, P0-A.3B, P0-A.3C, and
P0-A.3D are complete and no longer on this chain.
`HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` remains withdrawn from the immediate chain, a deferred
future validation candidate only (see `docs/STATE.md`'s `## BOUNDED ANALYSIS OUTPUT CANDIDATE`).
Opening P0-A.2/P0-B/P0-C.3 implementation, a push to `origin`, or any P1 work, requires its own
explicit owner authorization — parallel-safe is not the same as "start now."

### Canonical ID note — legacy "C. Research Evidence Layer" vs `P0-C`

This roadmap also retains an older, pre-P0 lettered narrative below ("A. Market Data Foundation",
"B. Universal Feature Foundation", "C. Research Evidence Layer") for historical continuity. Its
**"C" is not `P0-C`** — the legacy section is P1-scoped research-packet-generation work; `P0-C` is
canonical-universe/freshness work, an unrelated scope. Informal branch/worktree labels seen
locally (`C3C1`, `C3C2`, `C3C2H`, `C3C3`, `C3C4`) refer to the **legacy "C. Research Evidence
Layer"**, not `P0-C`, and are **not canonical roadmap IDs** — do not use them in new work; use the
IDs in the table above, or `legacy-c-research-evidence-...` if the historical section must be
referenced.

## Active ordered workstreams

The current program is **UNIVERSAL MARKET DATA & FEATURE FOUNDATION V1**. Its order is binding
unless the owner makes a new decision. This table is retained as P0-A.1-relevant technical detail
(see the canonical priority order above for current program sequencing):

| Order | Workstream | Current status / exit direction |
| --- | --- | --- |
| 1 | Dynamic market universe | Active and retained from DNSE security master; do not hard-code a small ticker list. |
| 2 | Market-wide raw coverage | OHLC V2 raw coverage **complete** (1,528/1,660 successful, 132 permanent provider-rejected, 0 untouched); foreign-trading V1 session complete. |
| 3 | Generic acquisition, pagination, restart contracts | Active. Trades contract ready for one-session market-wide run after checkpoint; quotes contract partial. |
| 4 | Coverage review and systemic exception discovery | **Complete and classified** — reconciled 1,528 successful + 132 `PERMANENT` + 0 untouched = 1,660 (see `docs/STATE.md`). `P0-A.1_TERMINAL_CLASSIFICATION` is closed; no further blind reprobe without new evidence. |
| 5 | Quality, canonicalization, semantics, PIT | Pending after sufficient raw contract/coverage evidence; feature/dataset-level status, never global ticker acceptance. |
| 6 | Vectorized feature-store enrichment | Pending. Canonical columnar Parquet/Arrow-compatible datasets and vectorized Polars-oriented computation. |
| 7 | Sector-aware semantic packs | Pending. Banking, securities, industrial, consumer, technology, and other proven packs define applicability and `NOT_APPLICABLE`. |
| 8 | Strategy breadth | Downstream. Strategies must declare dependencies and accepted feature statuses, preserve lineage, score deterministically where formalizable, and fail closed. |
| 9 | Multi-strategy aggregation | Downstream. |
| 10 | Portfolio/risk/sizing/leverage | Downstream consumer of qualified feature coverage. |
| 11 | PIT backtesting/calibration | Downstream; never use a feature whose price basis/PIT contract does not allow it. |
| 12 | AI and Dashboard decision support | Downstream consumers; AI cannot create numerical or source authority. |

## Current priority statement

> **CURRENT DEVELOPMENT PRIORITY — MARKET-WIDE DATA EXPANSION**
>
> Stock Lookup expands reliable, provenance-preserved, restartable DNSE/Livespeed datasets.
> The optimization target is **coverage × provenance × reusable dataset contracts**, not the
> count of individually qualified securities. Raw ingestion is broad; downstream use stays
> fail-closed by feature-level semantic, PIT, quality, and basis eligibility.

## Active market-wide acquisition lanes

### A. Security master / universe

Use dynamic enumeration. Retain observed provider identifiers and unknown security groups without
guessing their instrument type. A dataset adapter may restrict its request population only with a
verified request-contract rule; that restriction does not delete or globally reject the rest of
the universe.

### B. Historical OHLC

`UNIVERSAL_MARKET_DATA_LAKE_EXPANSION_V2` is partial and checkpointed. The next work is the
coverage review named in `STATE.md`, not a new qualification cohort, canonicalization phase, or
strategy expansion. Preserve provider failures and exceptions; open a systemic investigation only
when the review finds a shared pattern.

### C. Foreign trading

One market-wide session is complete with zero untouched applicable instruments. Future depth or
extension decisions must retain pagination, raw payloads, checkpoints/restart, and explicit
success/failure/untouched accounting. Completion of coverage leads to a market-wide coverage
review, not a per-ticker qualification loop.

### D. Trades history

Before any deep crawl, maintain and prove a generic bounded contract for cursor/pagination,
multi-page retrieval, termination, duplicate handling, restart, board fields, failure semantics,
and coverage. The current trades contract is ready only for a one-session market-wide raw run
after the owner/source checkpoint.

### E. Quotes history

Quotes has its own semantics. Do not infer them from names shared with trades. It remains pending
one complete continuation-to-terminal proof before bulk acquisition is eligible.

### F. Depth/backfill policy

Set history depth only after measured page density, API behavior, storage cost, throughput,
reliability, restart characteristics, and analytical value. Full history is not the default.

## Quality, semantics, and feature fabric

The raw lake retains immutable, provenance-bearing observations. The analytical core transforms
them into canonical columnar datasets, semantic/PIT records, historical feature tables, and
cross-sectional snapshots. A feature store must support both `instrument × date × feature/status`
and `instrument × snapshot × feature/status`.

Every reusable feature contract carries at least:

`value, status, method, quality, provenance, freshness, PIT_status, price_basis, blockers, lineage`.

Unknown semantics are retained as raw observations, not global ticker rejection. For example,
missing debt can block EV and EV/EBITDA while independent price, momentum, P/E, P/B, or flow
features retain their own status.

### Required semantic lanes

- Foreign-flow canonicalization: buy, sell, net, board, session, completeness, and status.
- Trade/quote board semantics: retain bounded-verified mappings only; do not over-generalize.
- Quantity/volume semantics: distinguish observed raw unit from normalized unit; never assume
  a multiplier without evidence.
- Price-basis registry: use the real code enum where one exists; conceptual states include
  `RAW_AS_TRADED`, `ADJUSTED_RETROSPECTIVE`, `PROVIDER_DEFINED`, and `UNKNOWN`.
- Corporate actions: distinguish planned from executed; never substitute record date for ex-date;
  track price, shares, EPS, valuation denominator, return, and PIT effects separately.
- Session completeness: distinguish market closed, pre-listing, suspension, no trade, provider
  omission, request failure, and true zero activity.

### Versioned data dictionary / semantic registry

The roadmap requires a versioned registry for feature name, definition, inputs, formula/version,
unit, PIT requirement, price/share basis requirement, quality requirement, sector applicability,
fallback behavior, status semantics, lineage, and strategy dependencies. Semantic truth may not
live only in chat, comments, or agent memory.

### Feature families to enrich after raw/semantic gates

- Price/technical: returns, moving averages, trend, volatility, range, high/low, relative
  strength, liquidity, turnover, and breakout structure.
- Flow: foreign buy/sell/net, participation, accumulation/distribution, round-lot, odd-lot,
  put-through, and normalized flow.
- Fundamentals: revenue, earnings, EPS, equity, debt, cash, margins, growth, ROE/ROA, and
  supportable cash flow/FCF.
- Valuation: P/E, P/B, P/S, EV, EV/EBITDA, FCF yield, and sector-specific alternatives.
- Quality: provenance, freshness, completeness, PIT, price basis, anomalies, and status.

## Strategy, portfolio, AI, and dashboard

**Strategy breadth is downstream of sufficient market-wide data and feature coverage.** The target
strategy family remains Momentum, Breakout, Value, Growth, CANSLIM, Flow, SMC/Market Structure,
and Event-driven. Each strategy declares feature dependencies and accepted statuses/bases/PIT and
fails closed per instrument/feature; one failed dependency does not make the instrument globally
unusable.

Portfolio/risk/leverage (multi-strategy ranking, construction, concentration, covariance,
volatility, liquidity-aware sizing, scenarios, stress/drawdown, margin eligibility, and PIT
backtesting) are downstream consumers. They are not current active priority.

AI consumes qualified evidence plus deterministic engines to explain, challenge, and surface
anomalies for human decision. It cannot invent facts, qualify unknowns, fabricate targets or
calibrated probabilities, or override deterministic risk gates.

## Provider and historical-evidence doctrine

- DNSE/Livespeed is the current market-data direction. Do not add another provider without an
  owner decision; EODHD remains rejected.
- Bounded HPG/VCB/VNM price-basis work and prior official-evidence cohorts are golden corpus,
  regression evidence, and historical milestones. They do not authorize ticker-by-ticker
  expansion or provider-wide semantic inference.
- Price-basis resolution should be dataset-level, provider-contract-level, representative-cohort,
  and corporate-action reconciliation work. When the basis is unknown, retain data, block only
## Side acquisition program

### ISOLATED_BULK_ACQUISITION_FRAMEWORK_V1 — Official Financial Filings Foundation

- **Status**: **COMPLETE_LOCAL** (branch `feature/isolated-bulk-acquisition-framework-v1`).
- **Scope**: Reusable, domain-agnostic foundation for bounded, resumable, provenance-preserving bulk document acquisition and immutable retention (`data-landing/`). First supported domain: official financial filings (replayed from Stock Lookup's existing governed evidence corpus with exact SHA-256 preservation).
- **Architecture**: 7 separated concerns across 9 small modules; content-addressed immutable retention (`raw/blobs/`); crash-safe atomic manifest and per-run checkpointing; first-class isolated quarantine store (`quarantine/`); fail-closed production isolation guard (`assert_write_allowed`); zero network or LLM dependencies in core retention modules.
- **Qualification Boundary**: Acquisition and qualification remain strictly separated. Every document record carries `qualification_state = "unknown"` unconditionally. No analytical, financial-fact, or provider authority is promoted.
- **Future official document bulk acquisition**: Completed foundation for future document domains. Corporate-action bulk acquisition is explicitly NOT started or implemented in this milestone.

## Future capability placement

> **Non-active future capabilities.** The placements below define technical requirements,
> prerequisites, and semantic boundaries for downstream workstreams. They do NOT alter the
> active P0 critical path, do not open implementation, and their sub-milestone numbering remains
> intentionally TBD until each respective phase is authoritatively opened by owner decision.

### P0-B — Qualified Volume/Liquidity Basis & Market-Wide Turnover (Formalized Design, Non-Active)

Formalized design for the P0-B volume/liquidity lane. Not marked active; implementation not started.

- **Sub-milestones**:
  - `P0-B.2a` — Daily Volume/Value Semantic Registry
  - `P0-B.2b` — Board + Session Cross-Sectional Reconciliation
  - `P0-B.2c` — Trading-Value Reconciliation
  - `P0-B.2d` — Scoped Promotion Review
- **`P0-B.2b` Invariants**:
  - `G1`/`G4`/`T1`/`T3`/`T4`/`T6` candidate reconciliation against official board semantics;
  - Discriminating sessions are required (sessions with distinct continuous, put-through, and odd-lot activity);
  - Trading-phase classification must be exchange/instrument/regime aware, not a universal hard-coded clock assumption;
  - Evaluate complete eligible cohorts rather than ad-hoc individual tickers;
  - Known missing observations remain explicit and are never imputed as zero;
  - Verdicts must support concepts equivalent to:
    - `EXACT_RECONCILED`
    - `COVERAGE_RESTRICTED_RECONCILED`
    - `CONFLICTING`
    - `INSUFFICIENT_DISCRIMINATION`
    - `UNAVAILABLE`
- **P0-B Closeout Output**:
  - Emits `QUALIFIED_LIQUIDITY_INPUTS` (volume, trading value, turnover, participation basis).
  - Explicitly **NOT**: `POSITION_SIZING_IS_SAFE` (position sizing and portfolio leverage remain downstream at P3 and fail-closed until all required price, volume, and risk authorities pass).

### P0-C — Official Exchange & Listing-Status Authority

- **Purpose**: Acquire and qualify official HOSE/HNX/VSDC evidence sufficient to resolve
  historically and as-of qualified: exchange identity, listing status, suspension/restriction
  windows, delisting/listing transitions, and active-universe eligibility.
- **Invariants**: Do not assume a current exchange snapshot is historically stable. Do not
  promote `ACTIVE_UNIVERSE` merely from DNSE raw security-master fields. Current state remains
  fail-closed (`ACTIVE_UNIVERSE = UNKNOWN`) until qualified official evidence is ingested and
  verified. Sub-milestone numbering remains TBD.

### P1 — Market Internals & Historical Market Breadth

- **Scope**: Advance/decline series, percentage of universe above MA50/MA200, new 52-week
  highs/lows, and market-wide breadth trend/deterioration/recovery indicators.
- **Prerequisites**: Qualified PIT price history (P0-A), historical constituent/universe
  semantics (P0-C), strict absence of survivor bias, and explicit treatment of
  suspended/missing/no-trade names.
- **Historical Weighting**: Cap-weighted sector or market analytics additionally require qualified
  historical market-cap inputs; equal-weight, median, and dispersion research do not imply those
  inputs are available.
- **Operating Boundary**: A shadow research implementation may precede production authority only
  when explicitly labelled non-authoritative. Retain existing P1 foreign-flow scale-out and
  Research Evidence Packet release architecture.

### P1 — Macro & Monetary Liquidity Context

- **Scope**: Candidate deterministic evidence/features subject to official source qualification:
  SBV Open Market Operations (OMO), SBV bill issuance and maturities, deterministic net-liquidity
  measures over explicit windows, interbank overnight and other qualified money-market rate series,
  qualified USD/VND exchange-rate series, and rolling rate/change/regime indicators.
- **Critical Semantic Boundary**: Do NOT encode empirical hypotheses (e.g. "SBV net injection
  predicts equities in 2–4 weeks", "FX depreciation causes foreign selling", "low interbank rates
  guarantee risk-on behavior") as system facts. The deterministic engine emits observed values,
  deltas, rolling statistics, and formal regime classifications only. Predictive or causal
  claims require separate qualified empirical validation.

### P1 — VN30 Derivatives & Market Microstructure Context

- **Scope**: Candidate deterministic features: VN30 futures minus VN30 spot basis, normalized /
  annualized basis where contract semantics support it, basis percentile / z-score under explicit
  lookback rules, futures volume, open interest (OI), change in OI, expiry-calendar context,
  contract roll context, and qualified ETF/index rebalance event context where official evidence
  exists.
- **Critical Semantic Boundary**: Observed market microstructure data must NOT automatically become
  inferred actor intent. A basis level or historical basis z-score is an observed/derived fact;
  claims such as "institutions are short hedging", "positive basis indicates a bull trap", "expiry
  week proves index manipulation", or single-name moves in large caps establish "kéo/đạp trụ" intent
  are unevidenced hypotheses. AI may discuss competing hypotheses with provenance and uncertainty,
  but these must never be stored as deterministic facts.
- **Basis Qualification Contract**: A future basis contract must define the futures price field
  (last, close, settlement, or another qualified field), spot/index observation type,
  timestamp/session alignment, trading calendar, contract identity, expiry/roll boundary, and
  stale/missing-observation treatment. A numerical difference between asynchronous or semantically
  incompatible observations is not automatically a qualified basis.

### P2 — Multi-Period Sector-Aware Fundamental Foundation

- **Scope**: Systematic acquisition and qualification of 3–5 years of official financial
  statements across the canonical EQUITY candidate universe (subject to issuer applicability and
  coverage states; not a permanent hard-coded denominator).
- **Requirements**: Official-document provenance, period identity, consolidated vs separate
  statement identity, currency/unit identity, restatement/amendment handling, knowledge/as-of
  semantics, and missing-field fail-closed behavior.
- **Sector Semantic Packs**: Must distinguish at least ordinary corporates, banks, securities
  companies, and insurance. Derived deterministic metrics (D/E, short/long borrowing structure,
  OCF, FCF, earnings quality) must emit `NOT_APPLICABLE` where economically inapplicable (e.g.
  where a sector-specific contract determines EBITDA or D/E is non-comparable), never forced into
  a universal schema.

### P2 — Financial Forensics & Accounting-Risk Features

- **Scope**: Deterministic accounting-risk signals and financial statement anomalies. This
  capability identifies risk signals; it does NOT determine fraud, manipulation, tunneling, or
  illegal conduct.
- **Cash Conversion / Earnings Quality**: CFO / Net Income (where denominator semantics are valid),
  operating cash flow trends, accrual-related measures, multi-period cash conversion consistency,
  and earnings/cash-flow divergence. Signed observations remain retained: sector/model
  inapplicability emits `NOT_APPLICABLE`; missing facts fail closed; near-zero denominators are
  blocked or explicitly handled by the metric contract; negative numerators/denominators require
  metric-specific interpretation and eligibility, not automatic `NOT_APPLICABLE` or deletion.
- **Receivables / Advances / Asset-Concentration Risk**: Advances / total assets, other short-term
  receivables / total assets, combined unusual-receivable concentration, growth in unusual
  receivables, related-party disclosure exposure, and receivable aging where officially disclosed.
  Terminology must remain neutral (e.g. `other_receivables_asset_concentration`,
  `accounting_risk_signal`); pejorative or legalistic labels ("rút ruột doanh nghiệp", fraud,
  manipulation) are strictly forbidden without authoritative legal/evidentiary proof.
- **Deterministic Financial Health Scores**: Altman Z-family models, Piotroski F-Score (with explicit
  formula/version identity, source facts, sector applicability, deterministic calculation, and
  fail-closed missing-data behavior). Not treated as calibrated probabilities of bankruptcy or
  future returns unless separately empirically qualified.

### P2 / P3 — Sector-Aware Valuation Engine

- **Scope**: Candidate model families subject to later qualification and sector/applicability
  contracts; not generically a "DCF engine".
- **Model Families**:
  - Non-financial corporates: FCFF / FCFE / DCF where multi-period cash flow evidence is sufficient.
  - Banks & financial institutions: Residual income, excess return, P/B–ROE-oriented methods, and
    dividend/equity approaches where justified.
  - Securities & insurance: Sector-specific valuation contracts appropriate to their financial
    structure.
- **Requirements**: Qualified multi-period financial inputs, deterministic assumptions, scenario
  provenance, explicit model applicability, and fail-closed handling for missing inputs. Never
  fabricate WACC, growth rates, or terminal assumptions.

### P2 / P3 — Deterministic Factor and Score Attribution

- **Scope**: Explicit decomposition of strategy/security scores into verifiable components
  (momentum, quality, value, liquidity/flow, sector/context effects, idiosyncratic contribution).
- **Invariants**: No post-hoc black-box explanations. Attribution must be derived directly from
  the same deterministic inputs and weights that produced the score.

### P3 — Portfolio Risk Budgeting & Position Sizing

- **Candidate Methods**: Deterministic risk budgets, volatility sizing, ATR/range-based sizing
  where qualified, and VaR/CVaR when return-distribution requirements are satisfied.
- **Kelly Sizing Boundary**: Kelly sizing from assumed, LLM-generated, or uncalibrated
  probabilities is strictly forbidden. Kelly may only become eligible when probability/distribution
  estimates are empirically calibrated and validated out-of-sample under authoritative backtest
  semantics.

### P1 / Dashboard — Research Evidence Packet Consumption

- **Architecture**: The canonical governed handoff to the AI research layer and dashboard release
  pipeline remains the **Research Evidence Packet (REP)** (no parallel canonical object called
  "Research Evidence Bundle" exists). Dashboard evolution consumes immutable, deterministic REPs
  and release contracts rather than recreating analytical truth from ad-hoc SQLite/CSV/JS exports.
  Do not schedule a dashboard rewrite ahead of upstream feature/dataset authority.
- **REP Optional Qualified Facets**: The REP evolves by carrying optional qualified facets, each
  preserving its own provenance, knowledge time, PIT semantics, eligibility state, and reason codes:
  `market_price_context`, `volume_liquidity_context`, `foreign_flow_context`,
  `market_breadth_context`, `macro_monetary_context`, `derivatives_microstructure_context`,
  `financial_evidence`, `financial_forensics`, `valuation_context`, `portfolio_risk_context`,
  `thesis_evidence`, `counter_thesis_evidence`. One BLOCKED facet does not invalidate an
  independent valid use case.

### Cross-Cutting Invariants (Operational Requirements, Not Milestones)

- **Restartability / Checkpointing**: Future ingestion and materialization pipelines must remain
  resumable, idempotent, checkpointed, and manifest/reconciliation based. This is an existing
  engineering invariant, not a missing milestone.
- **Isolated / Shadow Execution**: New pipelines, candidate features, and materializations must
  continue to use isolated worktrees, shadow outputs, and explicit promotion reviews without
  production authority by side effect. This is standard operating doctrine, not a missing milestone.

### Daily Screener Policy

- **`SHADOW_RESEARCH_SCREENER`**: Permissible as research-only when provenance is explicit,
  UNKNOWN/BLOCKED semantics remain visible, and no output is represented as authoritative or
  actionable.
- **`AUTHORITATIVE_LIVE_ANALYSIS`**: Currently remains blocked until required P0 price basis,
  volume/liquidity basis, and universe authorities are qualified. A later opened capability must
  additionally satisfy the specific authority gates for its exposed outputs; unrelated blocked
  facets do not freeze an otherwise qualified independent use case.

## Governing decisions for this phase

- [ADR-20260811 — Market-wide ingest-first feature-store architecture](adr/ADR-20260811-market-wide-ingest-first-feature-store.md)
- [DECISIONS — 2026-08-17 P0-RECOVERY closed](DECISIONS.md#2026-08-17---p0-recovery-closed-canonical-trades-materialization-terminal-success) (canonical Trades materialization terminal result)
- [DECISIONS — 2026-08-17 critical path revision](DECISIONS.md#2026-08-17---critical-path-revision-market-wide-universe-foundation-before-hpg) (market-wide foundation before HPG)
- [DECISIONS — 2026-08-17 terminal closure](DECISIONS.md#2026-08-17---terminal-closure-task-160-stage-b-and-p0-a1-ohlc-coverage) (Task 160 Stage-B and P0-A.1 terminal results)
- [DECISIONS — 2026-08-17 authority doc rebaseline](DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition) (current priority order, canonical IDs, prior-art disposition)
- [DECISIONS — 2026-08-17 P0-C.1/P0-C.2 foundation implemented](DECISIONS.md#2026-08-17---p0-c1-and-p0-c2-canonical-universe-foundation-implemented-local-worktree-only) (bounded-patch promotion, verified 3,250/1,660/1,590 reconciliation, remaining blockers)
- [DECISIONS — 2026-08-17 P0-C universe semantic evidence qualification](DECISIONS.md#2026-08-17---p0-c-universe-semantic-evidence-qualification) (security-group ~99.6% resolved; exchange and listing status investigated and found unqualified)
- [DECISIONS — 2026-08-12 governance rebaseline](DECISIONS.md#2026-08-12---one-time-governance-rebaseline) (retained technical facts)
- [AI rules](AI_RULES.md)

`READY_FOR_NEXT_MILESTONE` is not permission to execute the next milestone. Each external,
authority-affecting, or later-phase action remains owner-gated.
