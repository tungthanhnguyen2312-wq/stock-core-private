# VCI historical volume-basis qualification (v1.0.0)

## Decision

VCI historical chart volume is **unknown / unverified**. Liquidity activation is blocked. This declaration is intentionally provider-specific: the four KBS rows remain excluded and unknown.

## Exact ingestion lineage

`vn_stock_pipeline.fetch_one(ticker, start, end)` constructs `Quote(symbol=ticker, source="VCI", random_agent=True).provider.history(start=start, end=end, interval="1D")`. In vnstock 4.0.4, the VCI adapter POSTs to `https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart` with `timeFrame="ONE_DAY"`, `symbols=[ticker]`, `to=<end epoch seconds>`, and `countBack=<business-day count + 1>`. It converts vector fields `t,o,h,l,c,v` to rows and maps `v -> volume`. Pipeline `normalize()` lowercases column names, copies `volume`, drops missing/zero-volume rows, then applies `pd.to_numeric(...).fillna(0).astype("int64")`; it applies no volume multiplier, adjustment, aggregation, or unit conversion. The final value is stored in `ohlcv.volume` with `source="VCI"`.

## Bounded raw samples and corporate-action coverage

On 2026-07-30, direct POST samples were captured for HPG (2024-04-05), VNM (2024-08-09), and VCB (2025-01-17), each with `countBack=10`. The payloads contain both `v` and `accumulatedVolume`; all 30 corresponding values were equal. The samples cover three tickers and dates around the project’s corporate-action review periods, but neither the raw response nor the adapter supplies a unit or states whether this is shares, lots, matched volume, total traded volume, or adjusted volume. Equality of the two payload fields only proves aliasing, not unit semantics. No magnitude-based inference was used.

## Coverage and conflicts

The existing VCI price-only benchmark records 1,923,111 VCI rows and exactly four KBS rows excluded from the VCI segment. This job does not reclassify any KBS row. There is no conflicting qualified VCI volume declaration; the conflict rule rejects any future source/alias mismatch or competing basis evidence.

## Forward gate

`vci_volume_basis.validate_forward()` requires provider, raw field mapping (`v` / `accumulatedVolume`), basis, verified flag, and evidence id. It rejects unknown/unverified claims and does not permit liquidity activation until an independently sourced unit/basis declaration supports it.