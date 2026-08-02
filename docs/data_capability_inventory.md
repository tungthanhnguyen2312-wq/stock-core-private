# Data Capability Inventory

Audit date: 2026-07-26. Scope was `stock-core-private` authoritative Python,
configuration, tests, its read-only `vn_stock.db`, and the adjacent runtime
artifacts named by `STOCK_LOOKUP_RUNTIME_ROOT`. Backups, archives, secrets and
the untracked Producer `reports` directory were excluded.

| Domain | Provider / module | Runtime source / observed schema | IDs, time and coverage | State | Qualification / availability / missing behavior | Consumer and recommended action |
|---|---|---|---|---|---|---|
| Prices / volume | vnstock; `vn_stock_pipeline.py`, `vn_indicators.py` | `ohlcv(ticker,date,open,high,low,close,volume)`; parquet/CSV exports | ticker + session date; local history | runtime_active | price adjustment and volume-unit semantics unqualified; unknown stays unknown | Dashboard technical views; qualify raw/adjusted basis before returns or corporate-action adjustment |
| Financial statements | KBS mapping; `bctc_sync.py`, `bctc_processor.py`, `financial_canonicalization.py` | `financial_snapshot.parquet`; statement metrics, period labels, currencies | ticker + period; quarterly/annual, no publication time | semantics_blocked | raw values available but scope/restatement/publication usually unknown; null preserved | Fundamental, intrinsic, scenario; qualify statement metadata before joining periods |
| Company profile / shares | VCI/KBS; `company_profile_sync.py` | profile snapshots and `metadata` | ticker; retrieval time | semantics_blocked | `outstanding_shares` is source-specific and no basic/diluted basis is qualified | Relative/intrinsic valuation; qualify share basis and effective date |
| Corporate events | VCI `Company(...).events()`; `corporate_events_sync.py` | append-only event/observation/run tables; live HPG schema included `action_type_vi/en`, which normalization currently drops | VCI event id, provider dates; 50-row public cap, no qualified pagination | ingested_not_canonical | VCI-only forward observations are partial; KBS probes empty and fail closed | Corporate intelligence export; preserve/qualify action types, completion/revision and complete history before adjustment logic |
| Ownership | VCI/KBS; `shareholders_sync.py`, `ownership_structure_sync.py` | shareholder/ownership tables with raw payloads | ticker, holder, as-of/retrieval dates | runtime_active | shares and percent are independent; denominator not inferred | Consumer corporate intelligence; retain null percent when denominator absent |
| News | vnstock; `news_sync.py`, `news_ticker_mapping.py` | `news` and CSV exports | URL/title, published date | runtime_active | normalized mapping has provenance and explicit ambiguity | Dashboard/news context; no financial semantic unlock |
| Macro | vnstock; `macro_sync.py` | `macro(series,date,value)` and CSV/JSON | series + date; cadence per series | runtime_active | source/frequency exported; missing series explicit | Dashboard macro section; point-in-time signals remain unqualified |
| Index universe | vnstock; `instrument_master_sync.py`, `index_constituents_sync.py`, `index_membership_history.py` | instrument/index/history tables | symbol/index/effective date | available_unused | availability/history depend on provider response; no benchmark return semantics | Peer/benchmark work; qualify point-in-time membership and benchmark prices |
| Statement taxonomy (generated) | `statement_taxonomy_classifier.py`, `statement_taxonomy_sidecar.py`, `tools/build_statement_taxonomy_sidecar.py` | `statement_taxonomy_sidecar.json` built from `data_bctc/*_balance_sheet_quarter.parquet` | ticker + observed reporting-period range; session-bound | runtime_active | `generated_evidence` only, strictly below `config/ticker_entity_profiles.csv`; deterministic (`records_fingerprint` byte-stable on unchanged inputs); every input reconciled to a record or an explicit omission | Altman applicability gate (withhold-only) and coverage diagnostics; never presented as a verified issuer type |
| Official evidence | local official HPG PDF + manifest; `official_evidence.py` | `data/official-evidence/manifest.json`, hash-retained PDF | evidence id, source URL, SHA-256, issuer, reporting period, PDF page | runtime_active | qualified only while manifest and document hash verify; malformed/missing/hash mismatch emits no facts | Canonical financial records: HPG 2025 consolidated revenue, assets and equity now exported additively |

## Ranked gaps

1. Statement scope, publication date and restatement identity.
2. Basic/diluted/weighted-average share basis and effective date.
3. Complete dividend and corporate-action ledger.
4. Qualified debt split, CapEx, interest expense and attributable income.
5. Adjusted-price and volume-unit semantics.
6. Deterministic valuation history and peer classification.
7. Benchmark history with point-in-time membership/signals.
8. Complete VCI events pagination, ordering and revision status.
9. Official-evidence extraction for additional issuers/periods.
10. Financial-statement availability date layer for backtests.

## First unlock evidence

The retained `hpg-annual-report-2025.pdf` manifest has a qualified authority,
source URL, issuer/ticker, 2025 period and SHA-256. Page 35's table, *Revenue,
total assets, equity of the Group for 2014-2025*, reports 2025 Group revenue
VND 158,332bn, total assets VND 257,899bn and equity VND 131,220bn. These are
stored as reported, consolidated, annual VND facts with page, table, URL,
evidence ID and hash. The loader refuses to emit them if the file hash changes.
No value is copied into the provider snapshot and no unqualified series is
relabeled.
