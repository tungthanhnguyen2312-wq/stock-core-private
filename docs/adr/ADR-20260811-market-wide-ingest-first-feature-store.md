# ADR-20260811 — Market-wide ingest-first feature-store architecture

Status: accepted 2026-08-11

## Decision

Stock Lookup's active production architecture is:

`MARKET UNIVERSE → RAW DATA LAKE → DATA QUALITY → CANONICAL / SEMANTIC / PIT → VECTORIZED FEATURE STORE → FEATURE-LEVEL QUALIFICATION / CAPABILITY → POLYMORPHIC STRATEGY ENGINE → PORTFOLIO / RISK / LEVERAGE → AI RESEARCH / COUNTER-THESIS → DASHBOARD / HUMAN DECISION`.

The supported universe is the security master’s runtime set for HOSE, HNX, and UPCoM. It is not a fixed count and is classified into equities, ETFs, warrants, bonds, derivatives, rights, and other types. The former fixed 11-ticker set is a golden/regression corpus only.

## Rationale and consequences

- Ingest first; qualify a field, feature, and use later. Unknown semantics are preserved in immutable, provenance-bearing raw observations, not discarded.
- A missing fact blocks only dependent features. It never makes an instrument globally qualified or unqualified.
- Raw data, quality exceptions, canonical records, and PIT availability are separate layers. An anomaly is retained and routed to an exception queue; it is never deleted by detection.
- Deterministic Python engines own formalizable calculations. Polars/Parquet/Arrow is the target columnar production core; vectorized operations replace ticker-by-ticker production loops. AI may research semantics, extract candidate facts, explain deterministic results, and provide a counter-thesis, but cannot fabricate numerical authority.
- Price basis is source/dataset contract metadata (`RAW_AS_TRADED`, `ADJUSTED_RETROSPECTIVE`, `CURRENT_MARKET`, `PIT_OBSERVED`, `UNKNOWN`). Adjusted technical work can be eligible where declared; raw/PIT-dependent work remains blocked when those bases are unavailable.
- Strategies declare required features, accepted statuses/bases/PIT, and sector/instrument applicability. The engine fails closed rather than allowing a strategy to interpret evidence ad hoc.

## Supersession

The prior ticker-by-ticker qualification-first production workflow is **SUPERSEDED_AS_DEFAULT_WORKFLOW**. Its passed evidence, decisions, and historical constraints remain historical truth. Existing source-authority and evidence gates are not weakened or silently reopened.

## Migration

No mass move is made in this ADR. Existing `raw_financial_observations.py`, `canonical_financial_facts.py`, and related market-wide modules remain compatible while the new contracts are adopted incrementally. The migration map and the precise layer contracts are in [market_wide_ingest_first_architecture.md](../market_wide_ingest_first_architecture.md).
