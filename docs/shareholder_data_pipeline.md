# Shareholder data pipeline

## Scope

Phase 6 makes shareholder data auditable without changing the price, financial, news, or analysis pipelines. Shareholder data is a point-in-time context signal, not historical ownership data and not an investment recommendation.

## Source chain

The ordered source list is configured in `config/shareholder_pipeline.json`. The default order is VCI then KBS with `first_valid` behavior:

1. Record the VCI attempt.
2. Stop if VCI returns a non-empty payload that parses into usable records.
3. Try KBS only when VCI is `source_empty`, `unsupported`, `parse_failed`, or `network_failed`.
4. Stop after the first valid provider. Verified manual records are merged afterward and never replace or delete API provenance.

Every attempt records `source`, `status`, `error_reason`, raw and parsed record counts, request timestamp, and latest source `as_of_date`. A valid primary result therefore has exactly one provider attempt; an empty or failed primary followed by a valid fallback has two.

## Status contract

| Status | Meaning |
|---|---|
| `done` | A configured provider returned usable records. |
| `source_empty` | A provider request completed but returned no payload. It does **not** mean the company has zero major shareholders. |
| `unsupported` | The provider does not implement the endpoint. |
| `parse_failed` | A non-empty payload could not be normalized into safe records. |
| `network_failed` | The provider request failed or exhausted network retries. |
| `stale` | Usable records are retained, but their latest `as_of_date` exceeds the configured freshness threshold. |
| `manual_override` | Verified manual records were merged; API records and provenance remain present. |
| `not_queried` | Backward-compatible state for a ticker with no provider attempts or progress row. |

The diagnostic counters may be zero for a failed/empty attempt. The public `major_shareholders_count` remains `null` when there are no usable records, because zero would make a claim about the company that the source did not establish.

## Provider normalization

- VCI: `share_holder`, `quantity`, and fractional `share_own_percent`; percentages are multiplied by 100.
- KBS: `name`, `shares_owned`, and already-percent `ownership_percentage`.
- Optional source dates are read from `as_of_date`, `update_date`, `updated_at`, or `date`. A request timestamp is not relabeled as a source `as_of_date`.
- Missing ownership percentage remains `null`. The pipeline does not calculate it from shares unless a verified denominator is supplied; no current adapter supplies such a denominator.
- Holder type is not inferred from a name.

## Manual override rules

Manual rows live in `data/manual/shareholders_overrides.csv` with the columns:

`ticker,holder_name,shares,ownership_pct,as_of_date,source_name,source_reference,verified_at,note`

`ticker`, `holder_name`, `as_of_date`, `source_name`, `source_reference`, and `verified_at` are mandatory. A row without those provenance fields is rejected. `shares` and `ownership_pct` are independently optional; neither is inferred from the other.

Do not add a PAN row without a verifiable filing or other authoritative reference. The shipped file is intentionally only a header.

## Deduplication and conflicts

The deduplication identity is `ticker + normalized holder name + as_of_date`. Unicode NFKC normalization, case folding, and whitespace folding are used only for the identity; the displayed name is retained.

- Equal values from multiple sources are coalesced and all provenance entries are kept.
- Conflicting values are both retained with `reconciliation_status=conflict_preserved` and a shared deterministic `conflict_group`.
- API and manual records therefore cannot silently overwrite one another.

## Freshness

`freshness_threshold_days` is configurable and defaults to 180 days. Freshness uses the latest verified source `as_of_date`, not the crawl timestamp. A stale snapshot remains in storage and in context with an explicit stale flag. Records without a source date have `freshness.status=unknown` rather than a fabricated date.

## Storage and backward compatibility

The legacy tables remain available:

- `shareholders`
- `shareholders_progress`

Phase 6 adds:

- `shareholder_source_attempts`: append-only attempt log.
- `shareholder_records_v2`: source/date/provenance-aware records.
- `shareholder_sync_runs`: latest ticker-level status, counts, reason, and freshness.

The sync writes a legacy snapshot only after receiving valid API records. Empty, unsupported, parse-failed, network-failed, and manual-only results do not delete the previous legacy API snapshot. `AI ANALYZE/builders/build_ticker_context.py` prefers Phase 6 tables when the ticker has Phase 6 state and otherwise falls back to the legacy schema, including old tests that create only six/seven-column tables.

## Offline validation and PAN

Run the required fixture suite without network access:

```powershell
python -m unittest tests.test_shareholder_pipeline -v
```

Generate the read-only PAN diagnostic:

```powershell
python tests/diagnostics/shareholder_audit.py --ticker PAN
```

The report is written to `reports/shareholder_diagnostics_pan.json`. On the current database PAN has no shareholder rows and no progress/attempt record, so the accurate status is `not_queried`, not `source_empty` and not zero major shareholders.

## Phase 9 compatibility

Shareholder data remains outside the financial snapshot. Context consumers preserve `not_queried`, `source_empty`, `parse_failed`, and `stale` as distinct states; a null `major_shareholders_count` is never changed to zero.
