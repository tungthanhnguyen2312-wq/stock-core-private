# Missing-data schema v2 migration

## Before and after

Schema v1 had 41 snapshot columns, no version field, and no materialized Phase 4 advanced metrics. Schema v2 has `schema_version=2.0`, keeps all public scalar compatibility fields, and adds advanced metric status, formula, inputs, source, and period columns. No scalar field was removed in Phase 9.

## Consumer migration

Legacy consumers may continue reading `operating_cash_flow`, `ebit`, `ebitda`, and other scalars. New consumers should read the matching status/provenance before use. In AI context packages, prefer:

```python
value = context["financial_summary"]["ebit"]
meta = context["financial_summary"]["ebit_meta"]
if meta["status"] in {"reported", "derived"}:
    use(value)
```

Do not use truthiness to test numeric fields: zero is a valid value. Do not count `not_applicable` as missing. Do not use `valid` as a purpose-specific decision; use `profile_valid`.

## Rebuild

The active Python environment must provide pandas and a Parquet engine such as `pyarrow`.

```powershell
python snapshot_rebuild.py --replace
```

The command builds `financial_snapshot.next.csv/.parquet`, validates schema, row/ticker/period coverage, duplicate keys, null/status rates, units, PAN and representative tickers, then backs up and atomically replaces both current files. A validation failure leaves the current snapshot unchanged.

Reports are written to `reports/financial_snapshot_rebuild.json` and `.md`.

## Rollback

Stop downstream consumers. Copy the CSV and Parquet backup paths recorded under `rollback` in the rebuild JSON over both current snapshot files during the same maintenance operation. Re-run snapshot tests and PAN context dry-run before resuming consumers.

## Verified example

Before replacing the snapshot, the rebuild runs a full derivation pass (EBIT, SG&A, retained earnings, EBITDA status, OCF period selection) against a real corporate-profile ticker from the representative set, confirming each field resolves to the expected `status` (`derived`, `reported`, or `insufficient_periods`) instead of crashing or silently defaulting to zero. Exact figures are written to `reports/financial_snapshot_rebuild.json`/`.md` for local review — these reports are gitignored and not published, since they contain real per-ticker financial values.

## Known limitations

- Raw statement files do not consistently declare units; schema v2 reports `unit_unknown` instead of assuming VND.
- Filing publication dates are absent, so the snapshot is not point-in-time safe for strict backtests.
- EBITDA remains missing when neither combined D&A nor both separate components are reported.
- BIO balance-sheet sources without period/value columns are quarantined as structured `parse_failed` records in the rebuild report.

## Consumer audit

- AI context builder is the only executable downstream reader of `financial_snapshot`; it reads schema v2 metadata and retains legacy scalar fallback.
- Stock analyzer does not directly consume the financial snapshot, so no compatibility change was required.
- Read-only diagnostics were migrated from the old “snapshot not rebuilt” assumption to actual v2 statuses.
- No repository notebook directly consumes these fields.
- Backtest validation still blocks absent analysis cutoff, filing availability, and adjusted-price confirmation.
- Reports, workflow JSON, API metadata, and prompt guidance reference the snapshot contract but do not implement a competing parser.

The legacy core `ITEM_MAPPING` and duplicate-revenue compatibility helper remain because registry coverage is limited to the advanced metric set. They are not dead code and were not removed merely for cleanup style.
