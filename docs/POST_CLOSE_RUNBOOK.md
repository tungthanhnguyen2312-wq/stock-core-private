# Post-Close Operations Runbook — Canonical Financial Activation

## Objective

Execute the supported post-close path with canonical financial data enabled, verifying end-to-end exact-session integrity from the canonical fact store through Producer export, Consumer context generation, Consumer validation, and release publication preview.

## Command

Run on Windows PowerShell from `stock-core-private`:

```powershell
python tools/operate_stocklookup.py --runtime-root C:\Projects\StockLookup\dashboard-runtime --include-canonical-financial-facts
```

## The daily dependency chain

```text
metadata / current-share refresh   --refresh-metadata   (meta_sync.py; writes vn_stock.db)
  -> focus analysis                --prepare-inputs     (stock_analyzer.py -> Focus_Analysis.md)
  -> context packages              --prepare-inputs     (build_ticker_context.py)
  -> AI bundle export              --execute            (export_ai_bundle.py)
  -> Consumer exact-session check  --execute
  -> release publication           --publish [--live]
```

Each stage consumes what the one before it produced. A stage run on a predecessor's stale
output produces an artifact that is internally consistent and describes two sessions, so the
order is enforced rather than documented: the operator refuses at the first stage whose input
belongs to another session, and names both the stage and the remedy.

A complete daily run, in one command:

```powershell
python tools/operate_stocklookup.py --runtime-root C:\Projects\StockLookup\dashboard-runtime --refresh-metadata --prepare-inputs --execute --include-canonical-financial-facts
```

Add `--publish --web-root <served checkout>` to stage a release, and `--live` to promote it.
`--live` runs only when every prior gate has passed.

### What each flag does, and does not

| flag | does | does not |
| --- | --- | --- |
| `--refresh-metadata` | runs `meta_sync.py --refresh`: the only stage that moves `metadata.updated` and the provider share observation onto the current session | anything offline; it writes `vn_stock.db` and reaches the network, so it requires `--execute` and takes a restorable database copy first |
| `--prepare-inputs` | rebuilds the offline session-scoped inputs: technical signals, strategy report, focus analysis, context packages | refresh metadata or current shares — its meaning is unchanged and deliberately narrow |
| `--execute` | rebuilds and validates the artifact set | publish |

Never use `--allow-stale` for a release. It exists to override the export's session gate and
records the divergence in the manifest; a published bundle that used it is a mixed-session
artifact carrying a warning nobody reads.

### Remediation codes

The operator fails at the first stage whose input is off-session, prints the code and stops.
No later stage runs, and no success line is printed.

| code | meaning | remedy |
| --- | --- | --- |
| `METADATA_REFRESH_REQUIRED` | the share observation is older than the session, and `--include-canonical-financial-facts` would put it into the export; or the share stores could not be read | re-run with `--refresh-metadata`, or drop `--include-canonical-financial-facts` |
| `FOCUS_ANALYSIS_REFRESH_REQUIRED` | `Focus_Analysis.md` describes another session | re-run with `--prepare-inputs` |
| `CONTEXT_PACKAGE_REFRESH_REQUIRED` | one or more context packages describe another session | re-run with `--prepare-inputs` |

Lagged shares are **not** blocked when `--include-canonical-financial-facts` is absent: the
default bundle carries no share-derived value, so the lag cannot reach the artifact. The lane
counts are reported either way and a lagged value is never relabelled as current.

## Stage Order

1. **Preflight safety & production hash baseline**: Verifies existence of required input artifacts (`vn_stock.db`, `data_bctc/`), acquires process lock, and records initial artifact SHA-256 hashes.
2. **Market-session resolution**: Reads SQLite `ohlcv` session anchor read-only to bind session identity.
3. **Existing market/runtime build**: Optionally prepares technical signals and strategy reports if `--prepare-inputs` is specified.
4. **Canonical fact-store verification**: Runs `canonical_fact_store.verify()` over all 1,493 shards under `data/canonical-financial-facts/`.
5. **Producer bundle build with canonical financials enabled**: Invokes `export_ai_bundle.py --include-canonical-financial-facts` to construct `analysis_bundle.json`, `bundle_manifest.json`, and `focus_extract.json`.
6. **Consumer context generation**: Runs `build_ticker_context.py` smoke test across target tickers.
7. **Consumer validation**: Runs `builders.build_ticker_context.verify_exact_session_bundle()` to confirm exact-session proof.
8. **Four-artifact manifest validation**: Asserts that `analysis_bundle.json`, `bundle_manifest.json`, `focus_extract.json`, and `statement_taxonomy_sidecar.json` exist and match manifest hashes.
9. **Exact-session integrity validation**: Verifies bundle session date against manifest session anchor.
10. **Atomic publication preview only**: Runs `tools/publish_release.py` in dry-run mode (if `--publish` specified without `--live`).
11. **Final post-close summary**: Generates execution report `reports/operate_stocklookup_latest.json` and outputs SHA-256 digest summary.

## Inputs & Outputs

* **Inputs**:
  - `C:\Projects\StockLookup\dashboard-runtime\vn_stock.db`
  - `C:\Projects\StockLookup\dashboard-runtime\data\canonical-financial-facts\`
  - `C:\Projects\StockLookup\dashboard-runtime\data_bctc\`
* **Outputs (Dry-Run)**:
  - `reports/operate_stocklookup_latest.json`
* **Outputs (Execute)**:
  - `analysis_bundle.json`
  - `bundle_manifest.json`
  - `focus_extract.json`
  - `statement_taxonomy_sidecar.json`

## Dry-Run vs. Live Behavior

* **Dry-Run Mode (Default)**: Validates state and execution plan; writes nothing to production files or served checkout.
* **Live Mode (`--execute --publish --web-root <path> --live`)**: Promotes release artifacts by atomic rename into served checkout, updates manifest hashes, and commits release.

## Verifying the run

Read these off the report the run just wrote (`reports/operate_stocklookup_latest.json`),
in this order. Anything that does not match is the finding.

1. `steps[].preflight_database.reference_session_date` is the session you intended to publish.
2. `market_wide_shares_coverage.session_date` equals it, and `status` is `measured`.
   `measured_at` is this run's clock. A block with `status: unresolved_error` means the share
   stores could not be read — that is a finding, not a formatting issue.
3. `market_wide_shares_coverage.counts_reconcile` is `true` and the lane counts sum to
   `active_universe_count`.
4. Read the lane split rather than a single headline. `qualified_official` is **0** and will
   stay 0 until the corporate-action ledger is qualified for a ticker that also has an
   official anchor — see `docs/STATE.md`. Everything usable is `provider_reported_*`.
5. If the whole universe is `provider_reported_lagged`, the provider share observation
   (`metadata.updated`) is older than the session. `--prepare-inputs` does **not** refresh it;
   it is offline by construction. Only the daily market chain's `meta_sync.py` moves it.
6. `outcome`, `failed_gate`, and — on failure — that `rollback.performed` is `true` and the
   four artifact hashes match the previous session's set.

Do not read a valuation-readiness count out of this report. It does not compute one, and the
counts that used to appear here (`pe_ready_count` and siblings) were literals — see
`docs/DECISIONS.md`, "A reported measurement must be produced by the run that reports it".

## Known failure: stale context packages

`export_analysis_bundle` fails with `lệch phiên: context_package: <old> (cần <session>)` when
the Consumer's context packages belong to an earlier session than the one resolved. This is the
export gate working, not a bug. Re-run with `--prepare-inputs`, which rebuilds them (slow —
`candle_scan.py` alone is ~25 minutes over the full universe). `--allow-stale` exists but
records the divergence in the manifest and should not be used for a published release.

## Canonical Financial Limitations

* EBITDA ready for 231 tickers; ROE ready for 1,321 tickers.
* Market Capitalisation, EV, EV/EBITDA, P/E, and P/B remain `unavailable` / `blocked_by_price_basis` because price basis and share count acquisition are unverified.
* No ticker has a qualified current share count: the three retained official anchors are FY2024 period-end figures, and the corporate-action ledger covers 5 of 1,683 tickers at `partial_unqualified_50_row_cap`, so none can be carried forward to the session.
* Corporate-action crawling and price basis qualification remain separate downstream milestones.

## Failure & Recovery

* If any gate fails during `--execute`, the operator automatically restores previous production artifacts from the snapshot directory under `reports/operate_rollback/<timestamp>/`.
