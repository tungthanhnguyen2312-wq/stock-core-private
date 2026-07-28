# Phase 2E ? bounded orchestration pilot

`bounded_orchestration_pilot.py` is an opt-in, subprocess-only pilot for the
existing three-step chain. It does not replace the CLI recovery path, schedule
work, publish output, or select a production runtime automatically.

## Assets

| Asset | Existing authoritative CLI | Inputs | Output / fail-closed check |
| --- | --- | --- | --- |
| `metadata_snapshot` | `metadata_registry_export.py` | staged read-only `vn_stock.db`, nine explicit tickers | one explicit JSONL snapshot; exactly nine records |
| `ticker_context_packages` | `build_ticker_context.py` | snapshot, staged runtime, frozen UTC | registry packages only after the explicit shadow gate; semantic comparison against a direct database CLI build must pass |
| `ai_artifact_set` | `export_ai_bundle.py` | registry context packages plus staged source artifacts | focus extract, bundle, and manifest; ticker set and freshness status must pass |

Every asset records a run ID, frozen time, explicit inputs/outputs, dependency,
command, and structured `passed` / `failed` / `skipped` status in the evidence
report. A failed asset prevents every downstream asset from launching.

## Isolated execution

The default runtime root is a newly created system temporary directory. An
explicit `--runtime-root` must be a new empty directory and is rejected if it
is the production `dashboard-runtime`, its parent, or a child. The runner copies
only required runtime inputs and a read-only Consumer source copy to that root.
It sets `STOCK_LOOKUP_RUNTIME_ROOT` and the explicit
`STOCK_LOOKUP_AI_RUNTIME_ROOT` only for child commands. The latter preserves
`export_ai_bundle.py`'s legacy default when absent; it has no path discovery.

Example (manual/recovery CLI remains supported independently):

```powershell
python bounded_orchestration_pilot.py `
  --workspace C:\Projects\StockLookup `
  --runtime-root C:\tmp\phase2e-example `
  --evidence-dir C:\Projects\StockLookup\operations-review\evidence\phase-2e-orchestration-pilot-<UTC> `
  --frozen-at 2026-07-28T10:43:00Z
```

The temporary Consumer runtime keeps direct and registry contexts under `exports/context_packages/database/` and `exports/context_packages/registry/` respectively. The bundle receives the registry directory only through the explicit `STOCK_LOOKUP_CONTEXT_PACKAGES_DIR` child-process variable. The pilot compares the direct database context CLI output with the explicit
registry + shadow-gate output using the existing semantic provenance allowlist:
all business context and metadata must match; only the explicit snapshot
`data_sources` and metadata provenance replacement may differ. Invalid/missing
snapshot configuration and a mismatch fail closed; there is no metadata DB
fallback. The bundle must report `fresh` rather than use a stale override.

## Non-goals

No scheduler, daemon, web UI, Docker, PostgreSQL, dual-write, authority cutover,
production artifact promotion, Dashboard wiring, or default runtime-path change
is introduced. The engine is the standard-library isolated subprocess runner;
Dagster is not required for this bounded pilot.
