# Dashboard release-session contract

Scope: `publish_dashboard.py` / `sync_and_publish.bat` — the screener-data publish path.
This is a separate concern from the AI-bundle exact-session contract
(`docs/exact_session_bundle_contract.md`, `tools/publish_release.py`); see
"Two publishers" below for how the two relate.

## Why this exists

`publish_dashboard.py` used to derive the release session by reading `screen_snapshot.csv`'s
own `date` column (`max()` across non-delisted rows) in the *destination* (`WEB_ROOT`), with
no external cross-check. That heuristic cannot detect staleness: a frozen leftover copy of
`screen_snapshot.csv` is internally self-consistent — every row shares its own frozen date —
so `max()` over it always "succeeds" and reports a confident, wrong session. Concretely, a
dry-run could print `Snapshot hợp lệ: ... phiên 2026-07-24` and a corresponding build plan
as if it were valid, while `bundle_manifest.json` sitting in the very same directory already
recorded `freshness.reference_session: 2026-08-04` — a fact the publisher never looked at.

The fix (`release_session_contract.py`) makes `bundle_manifest.json`'s
`freshness.reference_session` the one authority, cross-validates every session-sensitive
artifact against it, and fails closed on any disagreement, missing value, malformed
manifest, or absence of anything to validate against. It never accepts file modification
time as a stand-in for session identity, and it never silently picks the min/max/first
session among disagreeing files.

## Artifact roles

| Artifact | Owns session identity? | Role |
| --- | --- | --- |
| `bundle_manifest.json` | **Yes — the authority** | `freshness.reference_session`, written by `export_ai_bundle.py` and anchored to the trading calendar (`get_session_anchor_and_prior` over `ohlcv`), is the one external source of truth. Cross-checked against `trusted_subset.session_identity` when present; disagreement is a hard failure. |
| `screen_snapshot_live.csv` | Session-scoped | Live-universe subset of `screen_snapshot.csv` (`is_live == True` rows only), written by the same `vn_indicators.py` run. This is what `export_ai_bundle.py` itself uses as its session-scoped anchor (`DEFAULT_SESSION_SCOPED_CATEGORIES`) — not `screen_snapshot.csv`. |
| `market_breadth.csv` | Session-scoped | Written by the same `vn_indicators.py` run as both snapshots; every row shares one `date`. |
| `analysis_bundle.json` | Session-scoped | `reference_session_date` field, written by `export_ai_bundle.py`. |
| `analysis_latest.json` | Session-scoped | `summary.session_date` field (not a top-level key), written by `stock_analyzer.py --strategy all`. |
| `screen_snapshot.csv` | **No — never release-session authority** | See "The screen_snapshot.csv decision" below. |
| `financial_snapshot.csv` / `.parquet` | **Session-neutral** | Keyed by reporting period (quarter/year), not by market session. An older reporting period is normal and must never be read as staleness — callers pass these names via `session_neutral=` and the contract never compares them to `reference_session`. |

## The screen_snapshot.csv decision

**Decision: screen_snapshot.csv is the canonical full-universe snapshot and remains
required, but it is explicitly demoted from release-session authority (option B in the
governing task). It is regenerated every run alongside screen_snapshot_live.csv; it is
never again used to derive the release session by itself.**

Evidence this is the architecture the code already implies, not a new design:

* `vn_indicators.py` writes `screen_snapshot.csv` (line ~934) and `screen_snapshot_live.csv`
  (line ~940) from the *same* in-memory DataFrame (`s`) in the *same* run —
  `s[s["is_live"]].to_csv(live_out, ...)` is a row-filter of the exact `s` just written to
  `screen_snapshot.csv`. One bounded generation run, compatible session metadata by
  construction (verified by `tests/test_vn_indicators_utf8.py::SubprocessSmokeTests`).
* `export_ai_bundle.py::DEFAULT_SESSION_SCOPED_CATEGORIES` deliberately excludes
  `screen_snapshot` — only `screen_snapshot_live` is session-scoped there. `screen_snapshot.csv`
  intentionally carries mixed-freshness rows (a delisted or thinly-traded ticker keeps its
  own last-available date `pct_above_ma200`), by design, for backward-compatible full-table
  consumers. A per-row `max()` over a file that is allowed to hold heterogeneous dates can
  never reliably signal "is this file itself stale" — that requires an external anchor.
* `daily_analysis_pipeline.py::DEPS` treats `screen_snapshot.csv` as a root input (no
  dependency entry) and its `inspect()` only confirms the file *exists*, never that its
  own session matches anything.

Given this, `screen_snapshot.csv` keeps its existing role (full-universe table, copied to
the dashboard for legacy full-table consumers) and its existing generator
(`vn_indicators.py`, unconditionally run by `daily_analysis_pipeline.py`'s `base` steps —
there is no `--skip-indicators` flag). What changed is only that `publish_dashboard.py` no
longer *trusts* it for session identity.

## Two publishers — this contract only governs one of them

* `tools/publish_release.py` publishes the AI-bundle release set (`analysis_bundle.json`,
  `bundle_manifest.json`, `focus_extract.json`, `statement_taxonomy_sidecar.json`) and
  already derives its session from `bundle_manifest.json.trusted_subset.session_identity` —
  it was never affected by this defect.
* `publish_dashboard.py` (this contract) publishes the screener data layer
  (`screen_snapshot.csv`, `market_breadth.csv`, `analysis_bundle.json`, the `ai_report_*`
  files, and the `data/*.js` mirrors) and is invoked independently, typically via
  `sync_and_publish.bat`.

Because these two publishers run independently, a dashboard checkout can legitimately hold
artifacts from two different publish cycles at once (e.g. `bundle_manifest.json` from a
`publish_release.py` run one day, `screen_snapshot.csv` from a `publish_dashboard.py` run a
different day). This contract does not merge the two publishers — that would be an
architecture change outside this defect's scope — it only makes `publish_dashboard.py` fail
closed instead of silently trusting whichever `screen_snapshot.csv` happens to already be
sitting in the destination.

## How the gate works (`release_session_contract.py`)

`resolve_release_session(root, required, *, session_neutral=(), today=None)`:

1. If `root/bundle_manifest.json` exists: read `freshness.reference_session` as the
   authority. A manifest that is present but unreadable, missing the `freshness` block, or
   missing `reference_session` is a **hard failure** — it never falls through to legacy
   mode, because a broken manifest is not the same thing as no manifest. `blocked: true`,
   a `trusted_subset.session_identity` disagreement, or a session date in the future are
   all reported as problems.
2. If `root/bundle_manifest.json` is absent: `legacy_cross_check` mode. The session is
   accepted only on **unanimous** agreement among the `required` artifacts that are
   present and readable — never the min, max, first, or any other single-file pick. Zero
   or conflicting observations both fail closed.
3. Every artifact in `required` is checked against the resolved session using an explicit,
   named accessor (`ARTIFACT_SESSION_RULES` — CSV `date` column `max()`, or a named JSON
   field path such as `analysis_bundle.json`'s `reference_session_date`). A name with no
   registered rule, or an unparseable value, is reported as a failure, never silently
   skipped.
4. Reporting order always follows the caller-supplied `required` order (a fixed sequence,
   not a dict/set) — deterministic across runs.

`publish_dashboard.py` calls this against `BACKEND_ROOT` (the fresh generation root — equal
to `WEB_ROOT` in a single-root invocation) immediately after `git_preflight()`, before any
copy, manifest write, or git mutation, and prints the report unconditionally:

```
RELEASE_SESSION=2026-08-04
SESSION_AUTHORITY=bundle_manifest.json
REQUIRED_ARTIFACTS_VALIDATED=screen_snapshot.csv,market_breadth.csv,screen_snapshot_live.csv,analysis_bundle.json
SESSION_MISMATCHES=0
PUBLISH_READY=YES
```

or, on failure:

```
RELEASE_SESSION=2026-08-03
SESSION_AUTHORITY=bundle_manifest.json
REQUIRED_ARTIFACTS_VALIDATED=analysis_bundle.json
SESSION_MISMATCHES=3
PUBLISH_READY=NO
SESSION_MISMATCH:
  screen_snapshot.csv observed=2026-07-24 expected=2026-08-03
  market_breadth.csv observed=2026-07-24 expected=2026-08-03
  screen_snapshot_live.csv observed=2026-07-23 expected=2026-08-03
```

A `PUBLISH_READY=NO` report stops `main()` immediately (exit code 1) — no copy, no manifest
write, no asset-version rewrite, no git add/commit/push, in both dry-run and `--live`.

## `source_root()`: the other half of the fix

Even with the gate in place, `validate_snapshot()`, `build_signature()`, and `file_entry()`
used to read `screen_snapshot.csv` / `market_breadth.csv` from `WEB_ROOT` unconditionally —
including in `--live` mode, where `copy_public_artifacts()` overwrites those exact files
with fresh bytes from `BACKEND_ROOT` moments *later* in the same run. That ordering meant a
live publish could write a `build_id` / `data/build_info.json` / `data/screener_data.js`
computed from the stale pre-copy bytes while the `.csv` files themselves ended up fresh —
an internally inconsistent release, and not something the module's own docstring intended
("preview and live always agree on build_id/content").

`source_root(relative)` resolves each backend-sourced name (`BACKEND_SOURCED`) to
`BACKEND_ROOT` whenever `BACKEND_ROOT` actually has that file, and to `WEB_ROOT` otherwise
(single-root invocations, or an optional file never generated in the backend). Every read of
a copied artifact's content now goes through this one function, so the dry-run preview and
a live write are computed from the same bytes.

## Operator-facing behavior

Unchanged commands: `cmd /c .\sync_and_publish.bat` (dry-run) and `... --live`. The new
preflight block above prints unconditionally, before the existing `[DRY-RUN]` / publish
lines. No new required environment variable — `STOCK_LOOKUP_BACKEND_DIR` remains optional;
when unset, `BACKEND_ROOT` still defaults to the script's own directory (unchanged), and the
gate simply validates that directory's own artifacts against its own manifest.
