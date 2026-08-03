# Post-Close Operations Runbook — Canonical Financial Activation

## Objective

Execute the supported post-close path with canonical financial data enabled, verifying end-to-end exact-session integrity from the canonical fact store through Producer export, Consumer context generation, Consumer validation, and release publication preview.

## Command

Run on Windows PowerShell from `stock-core-private`:

```powershell
python tools/operate_stocklookup.py --runtime-root C:\Projects\StockLookup\dashboard-runtime --include-canonical-financial-facts
```

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

## Canonical Financial Limitations

* EBITDA ready for 231 tickers; ROE ready for 1,321 tickers.
* Market Capitalisation, EV, EV/EBITDA, P/E, and P/B remain `unavailable` / `blocked_by_price_basis` because price basis and share count acquisition are unverified.
* Corporate-action crawling and price basis qualification remain separate downstream milestones.

## Failure & Recovery

* If any gate fails during `--execute`, the operator automatically restores previous production artifacts from the snapshot directory under `reports/operate_rollback/<timestamp>/`.
