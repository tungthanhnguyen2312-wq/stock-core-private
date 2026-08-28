# Workspace topology convergence

## Canonical operational topology

| Role | Canonical path | Constraint |
|---|---|---|
| Runtime root | `C:\Projects\StockLookup\dashboard-runtime` | Runtime/data only; never a served checkout or publisher authority. |
| Dashboard source/publish checkout | `C:\Projects\StockLookup\market-dashboard` | Normal clone of `tungthanhnguyen2312-wq/market-dashboard`, branch `main`. |
| Producer/publisher authority | `C:\Projects\StockLookup\stock-core-private\tools\release_orchestrator.py` | The only supported live publication entrypoint. |

The invariant is: **ONE CANONICAL RUNTIME + ONE CANONICAL DASHBOARD CHECKOUT + NO ALTERNATE PRODUCTION PUBLICATION PATH**.

`release_checkout_identity.py` pins both runtime and web paths. The Producer publisher,
release publisher, and release orchestrator fail closed for an alternate runtime or web
checkout, except isolated test fixtures. Dashboard checkout copies of publisher scripts are
targets and refuse direct execution.

## Preserved non-canonical paths

`dashboard-runtime` contains legacy Git metadata, two unpushed commits on
`feature/horizontal-top-navigation`, tracked generated-artifact WIP, and untracked retained
runtime stores. It is not a second canonical source/publish checkout, but its Git metadata and
contents must not be removed until its unique WIP is explicitly reconciled. The runtime remains
path-distinct from the source/publish checkout.

The archived `archive/deployment-evidence/recovery-test-*` repositories are retained historical
evidence. They are independent clean repositories with no linked-worktree common-dir dependency;
they are not operational publication paths and are intentionally not physically retired here.

## Operator path

Use a dry run or live release only through:

```powershell
python C:\Projects\StockLookup\stock-core-private\tools\release_orchestrator.py all `
  --backend-dir C:\Projects\StockLookup\dashboard-runtime `
  --web-dir C:\Projects\StockLookup\market-dashboard `
  --expected-session YYYY-MM-DD
```

`--live` remains an explicit, separately authorized operation. This topology milestone never
publishes, deploys, writes runtime data, or mutates a database.
