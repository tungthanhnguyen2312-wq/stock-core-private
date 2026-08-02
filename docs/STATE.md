# Stock Lookup state

- Active phase: P0 — Market-data basis and lineage.
- Active milestone: Retain provider-version and qualified corporate-action lineage, then rerun price-basis qualification.
- Producer baseline: `3c7a372`.
- Consumer baseline: `6797cab`.
- Dashboard baseline: `5ecbbad`.
- Completed: trusted-subset manifest/hash validation, Consumer trust validation, and HPG/VNM FY2024 verified historical-only financial analysis.
- Completed: historical fundamental briefs, Consumer context/prompt integration, AI response validation, and empirical price-basis tool scaffolding.
- Blocker: active VCI OHLCV rows are legacy records without retained provider/library version; new ingestion now retains version-bound lineage, but cannot retroactively qualify legacy rows.
- Blocker: zero retained HPG/VNM corporate-action events have both direct provider event lineage and an official citation/hash required for price continuity testing.
- Blocker: price basis is `unknown/unverified`; volume basis and current shares are also unqualified.
- Next exit gate: `OHLCV_PROVIDER_VERSION_RETAINED = YES` and `QUALIFIED_PRICE_TEST_EVENTS >= 8`.
- Production state: runtime databases and generated production artifacts remain unchanged by governance work.
