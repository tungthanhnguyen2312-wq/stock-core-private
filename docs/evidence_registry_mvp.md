# Evidence Registry MVP

`evidence_registry.py` is a read-only, in-process index over existing runtime evidence. Stable fact identity is `ticker + period + metric + source + citation/observation ID`. It queries by ticker, period, metric, qualification status, document hash, and lineage. Validation detects document hash mismatch, dangling references, duplicate/supersession conflicts, unsupported share semantics, and bank deposits aliased to debt.

The CLI requires `--runtime-root` and an explicit non-existing `--output`; it never defaults to a production path or writes sidecars. It supports HPG/VNM/VCB coexistence while retaining VCB bank identity separation. Missing platform capabilities: transactional append locks, durable supersession graph/versioning, concurrent writers, SQL indexes, and service/API access.
## Phase 2D replay

evidence_replay.py replays only into an explicit isolated SQLite file and verifies read-only parity; it never dual-writes or changes authority.
