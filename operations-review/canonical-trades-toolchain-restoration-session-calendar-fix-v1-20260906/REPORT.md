# Canonical Trades toolchain restoration and governed session calendar fix V1

Status: `COMPLETE` for the bounded source-code repair.

The Task-160 reconciliation adapter, materializer, and their command-line entrypoints were manually restored from the unmerged historical candidate, adapted to current `atomic_io` and foreground execution conventions. The restored path retains immutable reconciliation selection, Stage-A zero-writer binding, confirmed empty evidence, remaining failures, board IDs, raw timestamp/page lineage, deterministic raw-record identities, and verified materialization idempotence. No branch was merged or cherry-picked.

The matched-liquidity defect was separate: it used Canonical Trades' observed 40-session coverage list as the trading calendar. `2026-08-25` and `2026-09-04` are now valid governed sessions; their exact ADTV values remain unavailable because Canonical Trades ends on `2026-08-11`. The blocker is `REQUIRED_SESSION_CANONICAL_DATA_MISSING`, not `TARGET_SESSION_NOT_IN_GOVERNED_CALENDAR`.

The 65-session Anti-Gravity union is confirmed. Retained baseline compatibility is established by the Task-160 materialization-manifest/cohort identity and schema: 40 sessions, 66,400 logical units, 27 known failures, and 18,109,141 canonical rows. No source authority, PIT/RAW_AS_TRADED, liquidity authority, execution, sizing, provider, raw data, database, dashboard, publication, or deployment change occurred.
