# Fundamental Quality Contract

`fundamental_quality` v1.0.0 consumes canonical financial records only. Models contain applicability/result state, score/value, components, periods, scope, required/used/missing inputs, provenance, warnings, limits and actionability. States are available, partial, unavailable, inapplicable, incomparable, unknown. No legacy fallback or Consumer recomputation exists.

Industrial models require an explicitly classified corporate/industrial entity and compatible known scope/period records. Unknown scope/classification is unknown; non-industrial entities are inapplicable. Annual, quarterly and TTM never mix. Piotroski is never rescaled; Altman needs an explicit variant; Beneish needs every exact input. Null is never zero; negative values remain valid.

## Current runtime scope limitation

The existing `financial_snapshot.parquet` retains `operating_cash_flow_report_scope`, but representative HPG and PAN records are explicitly `unknown`; no supported persisted field qualifies consolidated or separate scope for the complete statement. Fundamental Quality therefore leaves industrial models `unknown` in production. No ticker, row order, value pattern, or undocumented source convention is used to infer scope.
