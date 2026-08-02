# Stock Lookup roadmap

## P0 — Market-data basis and lineage — ACTIVE
- Deliverables: provider/schema-version lineage; qualified corporate-action lineage; empirical active-path price test; volume semantics; source/version scale handling.
- Prerequisite: a replacement source may be integrated only after explicit owner approval of source authority, cost, licensing, and access. Until then, no paid provider or credential plumbing is an active milestone.
- Exit gates: `OHLCV_PROVIDER_VERSION_RETAINED = YES`; `QUALIFIED_PRICE_TEST_EVENTS >= 8`; `PRICE_BASIS_ACTIVE_PATH = DETERMINED_DOCUMENTED | DETERMINED_EMPIRICALLY`; `VOLUME_BASIS_ACTIVE_PATH = DETERMINED`; `NO_MARKET_CONSUMER_USES_UNQUALIFIED_BASIS = YES`.

## P1 — Trusted current-session readiness — PARTIAL
- Completed: exact-session manifest structure, hash binding, Consumer validation, and forward-retained daily/technical source timestamps for HPG/VNM.
- Remaining: qualified current shares, production regeneration through the forward timestamp contract, and price/volume-qualified same-session current fields.
- Exit gate: `HPG_VNM_CURRENT_SUBSET_FULLY_QUALIFIED = YES`.

## P2 — Point-in-time valuation alignment — BLOCKED
- Starts only after P0 and required P1 gates: market cap, raw/adjusted namespaces, point-in-time shares, and valuation-period alignment.
- Exit gate: `VALUATION_ENABLED_WITH_QUALIFIED_TEMPORAL_INPUTS = YES`.

## P3 — Evidence-qualified investment analysis — HISTORICAL-ONLY COMPLETE
- FY2024 historical HPG/VNM work is complete; future catalysts, risks, and scenarios cannot enable market-dependent conclusions before P0/P1/P2.
- Exit gate: `MARKET_DEPENDENT_ANALYSIS_REQUIRES_P0_P1_P2 = YES`.

## P4 — Market Scan and ranking — DEFERRED
- No universal score, ranking, or recommendation before valuation and current-market gates qualify.
- Exit gate: `RANKING_INPUTS_QUALIFIED = YES`.

## P5 — Portfolio and platform expansion — DEFERRED
- Portfolio fit/sizing, backtesting, RAG, Dashboard v2, and infrastructure scaling are last priority.
- Exit gate: `PORTFOLIO_AND_PLATFORM_PREREQUISITES_QUALIFIED = YES`.
