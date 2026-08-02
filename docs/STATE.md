# Stock Lookup state

- Active phase: P0 — Market-data basis and lineage.
- Active milestone: Configure EODHD credential, then run authenticated price-authority enablement.
- Producer baseline: `3c7a372`.
- Consumer baseline: `6797cab`.
- Dashboard baseline: `5ecbbad`.
- Completed: trusted-subset manifest/hash validation, Consumer trust validation, and HPG/VNM FY2024 verified historical-only financial analysis.
- Completed: historical fundamental briefs, Consumer context/prompt integration, AI response validation, and empirical price-basis tool scaffolding.
- Blocker: active VCI OHLCV rows are legacy records without retained provider/library version; new ingestion now retains version-bound lineage, but cannot retroactively qualify legacy rows.
- Completed: price-test event identity is official-event evidence; a VCI corporate-action event ID is optional metadata and is not a qualification prerequisite.
- Blocker: `VCI_PROVIDER_INTERNAL_ROUTE_BLOCKED_BY_RATIO_SEMANTICS`; vnstock 4.0.4 `Company.events` exposes `exercise_ratio` without a direct numerator/denominator/direction/scale contract, so provider-internal price windows are not authorized.
- Blocker: `ACTIVE_PRICE_PATH_SEMANTICS_UNQUALIFIED`; the bundle consumes unchanged `ohlcv.close` from `Quote(source='VCI').provider.history(start,end,interval='1D')`, whose installed documentation defines historical OHLC but no adjustment/default contract.
- Blocker: `DOCUMENTED_RAW_ADJUSTED_PATH_UNAVAILABLE`; no installed package exposes a directly documented raw-and-adjusted Vietnam equity EOD path. Next P0 requirement: `EXPLICIT_MARKET_DATA_SOURCE_AUTHORITY_CHANGE_REQUIRED`.
- Blocker: price basis is `unknown/unverified`; volume basis and current shares are also unqualified.
- Next exit gate: `OHLCV_PROVIDER_VERSION_RETAINED = YES` and `QUALIFIED_PRICE_TEST_EVENTS >= 8`.
- Production state: runtime databases and generated production artifacts remain unchanged by governance work.
