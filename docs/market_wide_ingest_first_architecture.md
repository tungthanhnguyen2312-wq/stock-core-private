# Market-wide ingest-first architecture

Status: active foundation, 2026-08-11. This document implements [ADR-20260811](adr/ADR-20260811-market-wide-ingest-first-feature-store.md).

## Doctrine

Raw retention is not downstream qualification. Every raw observation is immutable and carries provider, dataset, instrument, retrieval time, request identity, source/event time when present, payload/hash, schema version, and provenance. Unknown semantics remain explicit. Data may be stored before it is usable; only restricted calculations reject unqualified inputs.

The historical eleven tickers remain the golden/regression corpus; they are not the production
universe, which is populated from the supported security master at runtime.

Feature status is per field/feature/use-case: `OBSERVED`, `CANONICAL`, `QUALIFIED`, `DERIVED`, `DERIVED_PROXY`, `HISTORICAL_ONLY`, `UNQUALIFIED`, `UNKNOWN`, `BLOCKED`, `NOT_APPLICABLE`, and `SUSPECT`. Every non-exact result retains its reason, method, and lineage. A proxy has a separate feature identity and can never masquerade as the exact calculation.

## Layer contracts

| Layer | Required contract | Current foundation |
|---|---|---|
| Market universe | Runtime security master; exchange, board, instrument class; no fixed count | `instrument_master_sync.py` plus future universal master adapter |
| Raw data lake | Immutable `RawObservation`, payload hash and request provenance | `market_data_contracts.py`; existing financial raw shards |
| Data quality | Deterministic rule + exception queue + disposition; no deletion | `QualityException`, `quality_exceptions()` |
| Canonical / semantic | Standard identity, exchange, board, units, timestamps, price/corporate-action basis, statement scope, period/publication/effective/revision fields and quality flags | `CanonicalRecord`, existing canonical financial pipeline |
| PIT | Financial availability is `publish_date`/`effective_from`, and restatements only at `revision_publish_date`; period end is never availability | `PitFinancialFact`, `financial_facts_available_as_of()` |
| Feature store | Historical table (`ticker,date,...`) and cross-sectional session snapshot; statuses/lineage alongside values | `market_feature_store.py`, dictionary foundation |

The data-quality queue has `VALID_MARKET_EVENT`, `SOURCE_ERROR`, `CORPORATE_ACTION`, `UNIT_TRANSFORM_REQUIRED`, and `UNRESOLVED` dispositions. Required deterministic checks include duplicate identity, impossible OHLC, invalid numerics, session/timestamp mismatches, stale series, exchange-limit anomalies where contracted, volume-unit anomalies, robust rolling median/MAD and log-return/log-volume flags, corporate-action discontinuities, and source reconciliation. A Z-score alone is not a valid anomaly policy.

DNSE board mappings are source/version-provenanced semantic registry entries. Known concepts include G1 round lot, G4 odd lot, T1/T3 put-through round lot, and T4/T6 put-through odd lot. Where aggregation/unit semantics are undocumented, ingestion remains permitted and a market-wide reconciliation contract compares board cumulative/transaction quantities against OHLC volume across instruments, sessions, exchanges, and regimes. A multiplier may be introduced only after statistically consistent evidence and has effective-date/regime provenance; exceptions enter the queue.

## PIT and price-basis rules

Financial facts retain `period_end`, `publish_date`, `received_at`, `effective_from`, optional `revision_publish_date`, `source_document`, `statement_scope`, and audit/review status. Backtests and historical features must not expose a fact before its actual availability timestamp. Raw historical price or PIT-only workflows stay unavailable where their accepted basis is absent; adjusted retrospective prices remain valid for declared trend/momentum/MA workflows.

## Feature dictionary and sector rules

[`config/feature_dictionary.json`](../config/feature_dictionary.json) is the machine-readable seed. A definition carries identity, family, description, required inputs, formula, unit, PIT requirement, accepted price basis, sector applicability, quality/qualification rules, fallbacks, output status, strategy dependencies, and lineage version. It seeds market, flow, fundamental, valuation, and quality namespaces.

Sector rules are deterministic dictionary/registry data, never an LLM choice: banking uses P/B, ROE, NIM, and asset quality rather than core EV/EBITDA; securities use brokerage/balance-sheet metrics; industrial, consumer, and technology may use P/E, EV/EBITDA, FCF, and margins when qualified.

## Strategy and AI boundaries

`StrategyDeclaration` is the plugin interface: a strategy declares required features, accepted feature statuses and price bases, PIT need, instrument/sector applicability, and signal/scoring contract. It fails closed on missing, proxy, unaccepted-basis, or non-PIT inputs. Planned plugins are VALUE, GROWTH, CANSLIM, MOMENTUM, BREAKOUT, SMC, FLOW, and EVENT_DRIVEN.

AI may research official semantics, extract candidate structured evidence, identify CANSLIM “New” evidence, explain deterministic outputs, produce counter-theses, and surface anomalies. It may not calculate authoritatively when deterministic computation is possible, invent data/statuses/probabilities/targets, or override source and feature authority.

## Target package direction and migration map

The repository’s flat modules remain the compatibility surface; a disruptive directory move is deferred. The target grouping is `universe`, `ingestion/raw`, `quality`, `canonical`, `semantics`, `pit`, `features/{market,flow,fundamental,valuation,quality}`, `feature_store`, `strategies`, `portfolio`, `research`, and `contracts`, with dependencies flowing left to right and AI outside deterministic core.

| Existing module | Target group | Phase |
|---|---|---|
| `instrument_master_sync.py`, `live_universe.py` | `universe` | 1 |
| `raw_financial_observations.py`, `raw_financial_store.py` | `raw` | 1 (retained) |
| `canonical_financial_facts.py`, `canonical_fact_store.py` | `canonical/fundamental` | 2 |
| `market_basis_capability_registry.py`, DNSE modules | `semantics/market` | 2 |
| `point_in_time_*.py` | `pit` | 2 |
| `market_data_contracts.py`, `market_feature_store.py` | `contracts`, `quality`, `feature_store/market` | 3 foundation complete |
| `analysis_lane_eligibility.py`, ranking modules | `strategies` | 4 |
| portfolio/risk modules | `portfolio` | 5 |
| `ai_analyzer.py`, research bundles | `research` | 5 |

No strategy imports ingestion adapters. Source adapters never own canonical definitions. Feature definitions are separate from strategy declarations. This milestone creates no live store, bulk crawl, provider adoption, deployment, or publication.
