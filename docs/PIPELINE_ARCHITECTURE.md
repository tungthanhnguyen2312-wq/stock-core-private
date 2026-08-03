# Pipeline Architecture — Post-Close Canonical Financial Activation

## Overview

The StockLookup post-close pipeline connects market-wide canonical financial facts (Pillar A) to Consumer AI context generation and release publication through a unified, fail-closed operator loop.

```
Canonical Fact Store (data/canonical-financial-facts/)
       │
       ▼
Producer Exporter (export_ai_bundle.py --include-canonical-financial-facts)
       │
       ▼
Analysis Bundle (analysis_bundle.json: tickers[ticker].canonical_financial_facts)
       │
       ▼
Consumer Context Builder (ai-core-private/builders/build_ticker_context.py)
       │
       ▼
Consumer Context Package (context["canonical_financial_facts"])
       │
       ▼
Exact-Session Integrity Validation (verify_exact_session_bundle)
       │
       ▼
Post-Close Operator & Release Publisher (tools/operate_stocklookup.py)
```

## Layer Architecture

1. **Layer 1 — Observation Retention**: Retains raw financial statement payloads in `data_bctc/`.
2. **Layer 2 — Financial Canonicalization**: Resolves statement scope, sign conventions, balance identities, and cross-statement scale checks (`canonical_financial_resolvers.py`, `canonical_financial_facts.py`).
3. **Layer 3 — Canonical Fact Store**: Sharded gzip JSONL fact store in `data/canonical-financial-facts/` containing 195,552 canonical facts across 1,493 tickers (`canonical_fact_store.py`).
4. **Layer 4 — Calculation Readiness Policy**: Evaluates per-metric readiness (231 EBITDA ready, 1,321 ROE ready; market cap/EV fail closed) (`market_wide_calculation_readiness.py`).
5. **Producer Bundle Section**: Opt-in additive section `tickers[ticker].canonical_financial_facts` (`canonical_financial_bundle_section.py`).
6. **Consumer Context Pass-Through**: `build_ticker_context.py` passes the section verbatim into AI ticker context packages without recalculating metrics or changing statuses (`canonical_financial_facts_contract`).
7. **Operator Automation**: `tools/operate_stocklookup.py` orchestrates preflight, verification, export, consumer validation, and release preview.

## Milestone Exclusions

* Corporate-action crawling (HOSE, HNX, VSDC) remains unactivated.
* Price basis qualification remains unverified.
* Share count acquisition remains unverified.
