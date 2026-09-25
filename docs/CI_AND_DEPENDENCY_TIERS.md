# CI and dependency tiers

Milestone: `CI_HERMETIC_DEPENDENCY_AND_EVIDENCE_TIER_V1` (2026-09-25). Scope: CI and test
infrastructure only. No production analytical, provider or authority behavior changed.

## 1. Why

On 2026-09-25 every Producer CI job started failing at `pip install -r requirements.txt`
(`No matching distribution found for vnstock>=4.0.4`, run 75 on `cde156e`). The PyPI Simple API
(PEP 792) now reports `project-status: quarantined` for both `vnstock` and `vnai` and lists no
files, so no version of either can be installed from PyPI. This is the package index's
security-review status. This document draws no other conclusion from it.

Before that, `Focused deterministic regressions` had already been red for a separate reason
(run 73, 2026-09-24). Two tests in `tests/test_canonical_daily_operation.py` read gitignored
retained evidence under `operations-review/`, which a clean clone does not have. One of them
reached CI because the workflow's `--deselect` still named its pre-`bb31c15` test name, so the
deselect matched nothing.

## 2. Dependency surfaces

| File | Tier | Installed by core CI |
|---|---|---|
| `requirements.txt` | core runtime | yes |
| `requirements-test.txt` | core test | yes |
| `constraints.txt` | exact pins for the core + test closure | yes (`-c`) |
| `requirements-providers.txt` | optional provider runtime | **no** |

Reproducible core install (the one CI runs):

```bash
python -m pip install -r requirements.txt -r requirements-test.txt -c constraints.txt
python tools/verify_dependency_tiers.py --installed   # split + exact-pin + no-provider check
```

Provider runtime, when the packages can be installed:

```bash
python -m pip install -r requirements.txt -r requirements-providers.txt -c constraints.txt
```

### Classification

| Package | Class | Where it is needed |
|---|---|---|
| pandas, numpy, requests, pyarrow | `CORE_RUNTIME` | the core pipeline, the feature/quant engines and the hermetic tests |
| openpyxl | `CORE_RUNTIME` | private local-only portfolio workbook import (`private_portfolio_context.py`) |
| pytest | `CORE_TEST` | the test runner |
| vnstock | `OPTIONAL_PROVIDER_RUNTIME` | production KBS/VCI supplemental lane: `daily_session_level2_package` → `vnstock_worker_client` → `vnstock_worker_process` → `vn_stock_pipeline`; also the `*_sync.py` provider scripts |
| vnai | `OPTIONAL_PROVIDER_RUNTIME` | a transitive dependency of vnstock. `vnstock_worker_process` also imports it directly, inside `try/except`. It is never declared directly |
| anthropic | `OPTIONAL_PROVIDER_RUNTIME` | `ai_analyzer.py` for real API calls only (not `--dry-run`) |
| pandas_ta | `UNKNOWN` (commented out, unchanged) | `vn_indicators.py full` only; the import is guarded |

Where vnstock/vnai are needed:

- **Normal hermetic CI: no.** Every `vnstock`/`vnai` import in source is lazy (inside a
  function). CI runs with both imports blocked (§4).
- **Core analytical imports: no.** Importing the core modules never imports a provider.
- **Production provider workers: yes.** The KBS/VCI supplemental path and the sync scripts need
  vnstock (and therefore vnai). While the quarantine lasts, a machine that does not already have
  them cannot rebuild the provider runtime from PyPI. Do not vendor or privately mirror the
  packages, and do not fetch wheels from untrusted locations.
- **Provider contract tests: no.** Repo-wide, only `MetadataUpdatedTests` in
  `tests/test_producer_sync_timestamp_contract.py` needed an importable vnstock, and only to
  resolve two class names that the mocked `call_api` never calls. They now use an inert
  interface stub that fails loudly if used. The `vnstock_*` tests use the tracked fake worker
  (`tests/fixtures/fake_vnstock_worker.py`).

### Constraints

`constraints.txt` pins every distribution in the core + test closure: 19 on Linux, plus
`colorama`, which pytest needs on Windows only. The versions are exactly the set that the last
successful Producer CI install resolved (run 73, 2026-09-24, CPython 3.13, ubuntu-latest).
That set was re-validated from a clean clone without vnstock/vnai. The `requirements*.txt` files
keep their `>=` floors as the compatibility statement. The constraints make the resolution
deterministic.

These are deliberately **not** pinned:

- `requirements-providers.txt`: there is no installable vnstock/vnai distribution to verify a
  pin against, and they must never block the core install. The last versions CI installed were
  vnstock 4.0.8, vnai 2.6.1 and anthropic 1.8.0.
- `pip` itself: CI upgrades it before installing.

Change a pin only together with a green core CI run on the new set.
`tools/verify_dependency_tiers.py --installed` fails on any drift, and on any unpinned
distribution in the installed closure.

## 3. Test tiers

The tier plugin is `tests/_test_tiers.py`, re-exported by `tests/conftest.py`.

| Tier | Selection | Runs where |
|---|---|---|
| Hermetic core | `-m "not retained_evidence and not provider_runtime"` | GitHub CI (clean clone), anywhere |
| Retained evidence | `@pytest.mark.retained_evidence("<repo-relative path>", ...)` | owner local acceptance (strict); CI reports each as skipped |
| Provider runtime | `@pytest.mark.provider_runtime("<module>", ...)` | only where the optional provider packages are installed |

A retained-evidence test declares every evidence path it reads.
`STOCKLOOKUP_RETAINED_EVIDENCE_POLICY` controls what happens when a path is missing:

- `strict` (default; the owner's local acceptance): the test **fails** with
  `RETAINED_EVIDENCE_REQUIRED: <path>`. Nothing is silently skipped.
- `skip-if-absent` (clean-clone CI accounting): the test **skips** with
  `RETAINED_EVIDENCE_ABSENT: <path>`.

When the evidence is present, the test runs with its full, unchanged assertions under either
policy, and a genuine failure still fails. A marker without paths, an absolute path, a path
containing `..`, or an unknown policy value is a usage error at collection.

`STOCKLOOKUP_PROVIDER_RUNTIME_POLICY` works the same way for `provider_runtime`. Its default is
`skip-if-absent` (`PROVIDER_RUNTIME_ABSENT`), because the packages are optional. Set `strict` to
turn an absent provider into a failure. No test currently needs a real provider package, so the
tier is empty.

Tests currently in the retained-evidence tier (all inside the CI focused selection):

| Test | Evidence it replays | Hermetic counterpart |
|---|---|---|
| `test_canonical_daily_operation.py::test_retained_pre_workspace_session_fails_closed_before_publication` | real 2026-08-26 post-close operation | `test_canonical_dashboard_runtime_release.py` (`WORKSPACE_PRODUCER_MATERIALIZATION_UNAVAILABLE`) |
| `test_canonical_daily_operation.py::test_real_2026_09_21_retained_evidence_skips_working_dates_probe` | real 2026-09-21 MVA exact-session snapshot | `test_synthetic_retained_mva_snapshot_skips_working_dates_probe` (new, same end-to-end helper) |
| `test_canonical_current_product_projections.py::test_real_2026_09_18_live_enrichment_reproduces_the_accepted_relationship_distribution` | real 2026-09-18 foreign-flow evidence | synthetic flow-price tests in the same file (e.g. `test_flow_price_prefers_operation_linked_current_evidence_over_a_stale_static_artifact`) |
| `test_canonical_current_product_projections.py::test_retained_2026_09_11_replay_materializes_genuinely_current_products` | real 2026-09-11 replay inputs | synthetic projection tests in the same file (e.g. `test_workspace_threads_supplementary_velocity_and_flow_price_into_every_card`) |
| `test_investment_decision_workspace_projection.py::test_real_20260918_live_path_reconciles_to_the_exact_evidence_verified_counts` | real 2026-09-18 technical evidence | synthetic tests in the same file (e.g. `test_coherent_technical_evidence_drops_recovery_when_disposition_incoherent`) |

The last three used an unconditional `skipif`. They are now strict locally, like the first two.

## 4. CI workflow (`.github/workflows/producer-ci.yml`)

- Every job installs only `CORE_INSTALL` (core + test under `constraints.txt`). No secrets, no
  provider calls.
- `PYTHONPATH` puts `tests/provider_import_block/` first. Its `sitecustomize.py` makes every
  interpreter in the job refuse `vnstock`/`vnai` with
  `ModuleNotFoundError: PROVIDER_RUNTIME_BLOCKED:<name>`. That covers the pytest process and
  every Python subprocess a test spawns. A hidden provider import therefore fails loudly, even
  on a machine where the packages are installed. To reproduce locally:
  `PYTHONPATH=tests/provider_import_block python -m pytest ...`.
- `structural` also runs `pip check` and `tools/verify_dependency_tiers.py --installed`.
- `production-call-shape-smoke`, `structural` and `focused-regressions` are the hermetic tier
  (`-m "$HERMETIC_MARKERS"`). The focused selection is defined once, in `FOCUSED_SELECTION`.
- `retained-evidence-tier` runs `-m retained_evidence` over the same selection with
  `skip-if-absent`. On a clean clone every test in it skips, and `-rs` prints each explicit
  reason. The ad-hoc `--deselect` is gone.

## 5. Platform

The only runner is `ubuntu-latest` (CPython 3.13). The owner runs Windows with CPython 3.13
(`docs/PYTHON_EXECUTION_POLICY.md`), so a green Linux run does not prove Windows hermeticity.

- Path length: the longest tracked path is 218 characters (under
  `operations-review/real-official-corporate-action-factor-chain-evidence-v1-20260915/`).
  Checked out below a 43-character prefix such as `C:\Projects\StockLookup\stock-core-private\`
  (or a GitHub Windows runner's `D:\a\stock-core-private\stock-core-private\`), that path reaches
  261 characters, past the 259-character `MAX_PATH` limit. Windows checkouts therefore need
  `git config core.longpaths true`, as `CONTRIBUTING.md` already requires. A `.worktrees/<name>/`
  checkout adds its own prefix on top. No other tracked path exceeds the limit at that prefix.
- A future Windows job would need `core.longpaths` set before checkout. It is not added here.

## 6. Remaining clean-clone debt (recorded, not fixed here)

A full `pytest tests` from a clean clone (core dependencies only, network blocked, no
vnstock/vnai) gives: 7,206 passed, 516 failed, 74 errors, 274 skipped. By first error line, the
failures are dominated by:

- **Absent retained evidence under `operations-review/`** (~174 of the attributed failures).
  These tests are not yet marked `retained_evidence`. Future work should mark them the same way.
- **Absent runtime-root artifacts** (`STOCK_LOOKUP_RUNTIME_ROOT` / `dashboard-runtime`,
  `data_bctc/`, `data/`).
- **The sibling `ai-core-private` checkout** (`builders.*`, `metadata_registry_reader`).
- **Undeclared optional imports:** `pypdf`, `PyMuPDF` (`fitz`), `Pillow` (`PIL`), `duckdb` and
  `websockets` are imported by the official-document, OCR, storage-benchmark and PIT-shadow lanes
  but declared nowhere. Their five test modules fail at collection.
- **Genuine stale test:**
  `test_producer_sync_timestamp_contract.py::OperationalGeneratedAtBehavioralTests::test_bctc_sync_normalize_report_scraped_at_uses_frozen_vn_time`
  still patches `bctc_sync.vn_now`, but `8f9be00` made `normalize_report` stamp
  `vn_now_iso()`. That class is therefore not in the CI selection. The file's other three
  classes are.
- **Absolute paths:** 39 source/tool references to `C:\Projects\...` (mostly `tools/run_*`
  defaults, plus `release_checkout_identity.py`), and test fixtures that embed Windows runtime
  paths as data. None of them is on the hermetic CI path.
- `requirements-providers.txt` keeps the vnstock `setup_api_key` step from the old
  `requirements.txt`. The `docs/USER_GUIDE.md` that the old file referred to does not exist.
