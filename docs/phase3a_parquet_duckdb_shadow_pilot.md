# Phase 3A ? Parquet/DuckDB shadow analytics pilot

`shadow_analytics_pilot.py` is a bounded, opt-in, read-only shadow. SQLite and
append-only JSONL remain the sole authority. The pilot is limited to HPG, VNM,
and VCB and requires explicit, new temporary lake and evidence directories.

It materializes ticker-partitioned Parquet datasets for OHLCV, available
canonical financial metrics, Evidence Registry identities, and verified
share-basis citations. DuckDB reads only those Parquet files for latest and
historical lookups, valuation-input joins, and evidence lineage trace-back.

FY2024 financial rows are promoted only from the existing evidence bridge: each
row must be a direct, `available` annual observation with explicit
`consolidated` or `separate` scope, currency, scale, one observation identity,
and matching citation/evidence lineage. Unknown or missing scope/lineage is
rejected; two scopes for one ticker/metric fail closed. The raw provider snapshot
is never used to infer statement scope. HPG/VNM are corporate rows; VCB is
restricted to the bounded bank-metric allowlist.

Numeric precision is an explicit per-column contract. OHLCV `open`, `high`,
`low`, and `close` are finite SQLite `REAL` values written/read as DuckDB
`DOUBLE`; `volume` is `BIGINT`. Qualified financial/share-basis/evidence amounts
are accepted only as exact integers and written/read as `BIGINT`, with their
currency and unit scale retained. There is no blanket float tolerance and no
JSON/display conversion in parity. A non-integral financial amount or non-finite
price fails closed until a separately qualified decimal schema is added.

Parity compares authority and shadow identity/value/null/date/provenance fields.
The deterministic contract is semantic content: sorted canonical-row fingerprints
must match. Physical Parquet bytes are not required to match because writer
metadata and physical layout are documented exceptions.

VCB remains a bank: unsupported corporate metrics, including `total_debt` and
EV/EBITDA-like inputs, fail closed. No deposits-to-debt alias exists. No database,
JSONL, runtime artifact, Dashboard, Consumer, scheduler, service, or authority
cutover is part of this pilot.
