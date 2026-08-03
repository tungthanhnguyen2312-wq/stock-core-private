# CLI Reference — StockLookup Producer & Operator

## Post-Close Operating Command

The canonical post-close operation for StockLookup is executed through `tools/operate_stocklookup.py`.

### Exact Windows Command (Dry Run)

```powershell
python tools/operate_stocklookup.py --runtime-root C:\Projects\StockLookup\dashboard-runtime --include-canonical-financial-facts
```

### Exact Windows Command (Execute & Publish Dry Run)

```powershell
python tools/operate_stocklookup.py --runtime-root C:\Projects\StockLookup\dashboard-runtime --execute --include-canonical-financial-facts --publish --web-root C:\Projects\StockLookup\market-dashboard
```

### Operator Flags

* `--runtime-root <path>`: Required. Absolute or relative path to the dashboard runtime directory containing `vn_stock.db` and runtime stores.
* `--include-canonical-financial-facts`: Opt-in (P1F). Enables market-wide canonical financial fact store verification and attaches `tickers[ticker].canonical_financial_facts` to the Producer bundle.
* `--execute`: Performs actual build and validation steps instead of dry-run reporting.
* `--publish`: Runs `tools/publish_release.py` in dry-run mode (or live mode if `--live` is specified).
* `--web-root <path>`: Required with `--publish`. Target served Dashboard checkout for release promotion.
* `--live`: Requires `--execute` and `--publish`. Promotes release artifacts by atomic rename into `--web-root`.

## Export AI Bundle CLI

```powershell
python export_ai_bundle.py --include-canonical-financial-facts --tickers HPG,VNM,VCB
```

* `--include-canonical-financial-facts`: Opt-in additive section attaching canonical facts and calculation readiness.
