# Stock Lookup state

- Active phase: P0 — Market-data basis and lineage.
- Active milestone: Import operator-supplied official event documents, retain VCI windows, rerun qualification.
- Producer baseline: `3c7a372`.
- Consumer baseline: `6797cab`.
- Dashboard baseline: `5ecbbad`.
- Completed: trusted-subset manifest/hash validation, Consumer trust validation, and HPG/VNM FY2024 verified historical-only financial analysis.
- Completed: historical fundamental briefs, Consumer context/prompt integration, AI response validation, and empirical price-basis tool scaffolding.
- Blocker: active VCI OHLCV rows are legacy records without retained provider/library version; new ingestion now retains version-bound lineage, but cannot retroactively qualify legacy rows.
- Completed: price-test event identity is official-event evidence; a VCI corporate-action event ID is optional metadata and is not a qualification prerequisite.
- Blocker: no retained official document has explicit ex-date and ratio metadata for price-test intake; operator-supplied official PDF/HTML bytes plus stable source URL and explicit event metadata are required.
- Blocker: price basis is `unknown/unverified`; volume basis and current shares are also unqualified.
- Next exit gate: `OHLCV_PROVIDER_VERSION_RETAINED = YES` and `QUALIFIED_PRICE_TEST_EVENTS >= 8`.
- Production state: runtime databases and generated production artifacts remain unchanged by governance work.
