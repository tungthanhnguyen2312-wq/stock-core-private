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
| P0-A.2 | Corporate-action evidence scale-out | Not started authoritatively; reviewable prior art exists (`1183c72`→`d7b9bf3`) |
| P0-A.3 | Market-wide PIT price reconstruction | Not started; depends on A.1 + A.2 |
| P0-A.4 | Scoped price-basis promotion | Not started; depends on A.3 |
| P0-B | Qualified volume/liquidity basis + market-wide turnover | Not started authoritatively; reviewable prior art exists (`c05bec0`→`4480c3b`→`0d19e07`) |
| P0-C | Canonical market universe + exclusion ledger + freshness semantics | **Active gate** — review-for-promotion of existing prior art; not started authoritatively, not promoted |
| P0-C.1 | Instrument-master reconciliation | Reviewable prior art exists (`b4e3c71`); review-for-promotion active, not promoted |
| P0-C.2 | Universe-tier hierarchy / exclusion ledger | Reviewable prior art exists (`3d9a2ab`); review-for-promotion active, not promoted |
| P0-C.3 | Field-level freshness/as-of retrofit | Not started |
| P1 | Foreign-flow scale-out; UFS/feature-authority normalization; Research Evidence Layer; market-internals | Deferred |
| P2 | Sector/factor normalization; official multi-period fundamentals; operational robustness | Deferred |
| P3 | Return/risk, calibrated scenarios, sizing, backtest | Deferred; fail-closed until P0-A + P0-B pass |

`P0-A`, `P0-B`, and `P0-C` are independent, parallelizable lanes once started, but current
execution focus is **market-wide/full-universe data foundation first**, not single-ticker
artifact expansion — see `docs/STATE.md`'s `## CRITICAL PATH` for the full ordered chain.
`CANONICAL_TRADES_MATERIALIZATION` and P0-RECOVERY close are both **complete**
(`TERMINAL_SUCCESS_QUALITY_RESTRICTED`). Active gate: canonical universe boundary
(`P0-C.1`/`P0-C.2` review-for-promotion of existing prior art, not yet promoted) → then
`P0-A.2`/`P0-A.3`/`P0-A.4`/`P0-B` → `P0-C.3` → first market-wide deterministic analysis artifact.
P0-A.1 is complete and no longer on this chain. `HPG_BOUNDED_ANALYSIS_OUTPUT_VERIFICATION` remains
withdrawn from the immediate chain, a deferred future validation candidate only (see
`docs/STATE.md`'s `## BOUNDED ANALYSIS OUTPUT CANDIDATE`). Opening P0-C implementation, or any P1
work, requires its own explicit owner authorization — parallel-safe is not the same as "start now."

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
  basis-dependent historical returns/backtests, and continue independent valid capabilities.

## Governing decisions for this phase

- [ADR-20260811 — Market-wide ingest-first feature-store architecture](adr/ADR-20260811-market-wide-ingest-first-feature-store.md)
- [DECISIONS — 2026-08-17 P0-RECOVERY closed](DECISIONS.md#2026-08-17---p0-recovery-closed-canonical-trades-materialization-terminal-success) (canonical Trades materialization terminal result)
- [DECISIONS — 2026-08-17 critical path revision](DECISIONS.md#2026-08-17---critical-path-revision-market-wide-universe-foundation-before-hpg) (market-wide foundation before HPG)
- [DECISIONS — 2026-08-17 terminal closure](DECISIONS.md#2026-08-17---terminal-closure-task-160-stage-b-and-p0-a1-ohlc-coverage) (Task 160 Stage-B and P0-A.1 terminal results)
- [DECISIONS — 2026-08-17 authority doc rebaseline](DECISIONS.md#2026-08-17---authority-doc-rebaseline-p0-priority-order-canonical-roadmap-ids-prior-art-disposition) (current priority order, canonical IDs, prior-art disposition)
- [DECISIONS — 2026-08-12 governance rebaseline](DECISIONS.md#2026-08-12---one-time-governance-rebaseline) (retained technical facts)
- [AI rules](AI_RULES.md)

`READY_FOR_NEXT_MILESTONE` is not permission to execute the next milestone. Each external,
authority-affecting, or later-phase action remains owner-gated.
