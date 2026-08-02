# Stock Lookup state

- Active phase: P0 — Market-data basis and lineage.
- Active milestone: Retain provider-version and qualified corporate-action lineage, then rerun price-basis qualification.
- Producer HEAD: `bbca785`.
- Consumer HEAD: `da516dc`.
- Dashboard HEAD: `ebdb6e9`.
- Completed: trusted-subset manifest/hash validation, Consumer trust validation, and HPG/VNM FY2024 verified historical-only financial analysis.
- Completed: historical fundamental briefs, Consumer context/prompt integration, AI response validation, and empirical price-basis tool scaffolding.
- Blocker: active VCI OHLCV has unretained provider/library version and zero qualified HPG/VNM corporate-action test events.
- Blocker: price basis is `unknown/unverified`; volume basis and current shares are also unqualified.
- Next exit gate: `OHLCV_PROVIDER_VERSION_RETAINED = YES` and `QUALIFIED_PRICE_TEST_EVENTS >= 8`.
- Production state: runtime databases and generated production artifacts remain unchanged by governance work.
