# ADR-003: Retain SQLite authority with DuckDB/Parquet analytical shadow

## Status

Accepted - Phase 3D benchmark (2026-07-28).

## Context and bounded evidence

The read-only benchmark used production SQLite and the retained Phase 3A HPG/VNM/VCB Parquet lake. Each backend/query had one warm-up and exactly two measured runs. Semantic parity passed before timings were accepted. Evidence: `operations-review/evidence/phase3d-storage-benchmark-20260728T164005Z/BENCHMARK_REPORT.json`.

| Query | Rows | SQLite/Pandas median ms | DuckDB/Parquet median ms |
|---|---:|---:|---:|
| HPG OHLCV history | 2,012 | 60.381 | 20.322 |
| Three-ticker latest-date slice | 3 | 2.197 | 2.553 |
| Historical price lookup | 3 | 4.870 | 6.020 |
| Financial/evidence lineage join | 46 | 18.072 | 6.839 |
| Representative analytical scan | 3 | 3.863 | 2.524 |

Output bytes, identity/value/null/date/provenance fingerprints, and source authority fingerprints matched. Peak memory is reported as Python allocation peak only; native engine allocations are deliberately not estimated by this bounded harness.

## Decision

Continue with SQLite/JSONL as the sole production authority and retain DuckDB/Parquet as a read-only analytical shadow. SQLite remains operationally simpler for current transactional/runtime paths and short point lookups. DuckDB/Parquet is justified for isolated history, scan, and evidence-lineage analysis.

PostgreSQL is deferred. Revisit only when an explicit multi-process durable query/write service, concurrent users, operational replication/backup requirements, or measured SQLite contention requires it. TimescaleDB is also deferred: no continuous high-volume time-series ingest, retention policy, hypertable operation, or service workload is qualified. No migration, dual-write, scheduler, authority cutover, API, or dashboard wiring is authorized.

## Consequences

The benchmark harness is reusable but remains caller-supplied-path only. Every future performance claim must retain semantic parity and source-invariance checks. Parquet physical bytes are not an authority and remain outside runtime promotion.
