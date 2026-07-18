# Canonical news ticker mapping

Phase 5 maps news to canonical tickers using versioned exact aliases instead of
requiring an unstable source `ticker` field.

## Alias registry

`config/ticker_aliases.csv` stores ticker, alias, alias type, priority, and
optional validity dates. Existing metadata may add only fields that are actually
present: ticker, legal name, and company name. In the current database metadata
has no company-name field, so ticker aliases are generated automatically and
manual PAN names supply the legal/company aliases.

Match priority and confidence:

- legal name: `1.00`;
- company name: `0.98`;
- registered alias: `0.95`;
- ticker with explicit financial context: `0.92`;
- subsidiary/brand: `0.85`/`0.80`, candidate review only.

Matches at `>=0.90` are auto-accepted, `0.70–0.89` remain candidates, and lower
scores are not mapped. Generic uppercase tokens are never treated as tickers.

## Pipeline behavior

Articles are deduplicated by canonical URL, or normalized title and publication
date when no URL exists. One article may emit mappings for multiple tickers. Each
accepted mapping records `news_id`, ticker, method, matched alias, confidence,
and mapping version.

Company, sector, and market news remain separate. Sector or market fallback does
not make a ticker news section available. When no company article matches, the
output explicitly uses `status=no_company_specific_news` with separate counts
and the configured 30-day lookback.

## PAN diagnostic

The current `news_latest.csv` contains 100 recent articles but none matching PAN
at the accepted threshold. PAN therefore has zero company and sector articles,
100 market fallback articles, and status `no_company_specific_news`. This is not
reported as a missing mapping.

Generate the diagnostic and mapping table with:

```powershell
python tests/diagnostics/news_mapping_audit.py --ticker PAN --output reports/news_mapping_diagnostics_pan.json --map-output reports/news_ticker_map_pan.csv
```

## Phase 9 compatibility

Mapping thresholds and alias precedence are unchanged. Consumers must read the explicit summary status; `company_news_count=0` is a valid observed count and must not be converted to `mapping_missing`.
