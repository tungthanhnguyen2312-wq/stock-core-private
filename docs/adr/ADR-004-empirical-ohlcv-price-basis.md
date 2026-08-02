# ADR-004: empirical qualification of the active OHLCV close path

The active bundle path is `vn_stock.db:ohlcv.close` through
`export_ai_bundle.load_ohlcv_recent`. Qualification is version-scoped to the retained
provider and schema. The tool compares three pre- and post-ex-date closes around qualified,
non-overlapping stock-dividend/bonus events, allowing for the HOSE price band. It never
generalizes to another provider, library version, data path, or cash-dividend total-return
methodology.

The result must be retested after a provider/schema version change, corporate-action evidence
change, or sufficient qualified event coverage becomes available. Until a determined result,
price basis remains unknown and all market-dependent use remains blocked.
