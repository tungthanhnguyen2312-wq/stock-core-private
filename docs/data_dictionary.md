# Financial snapshot data dictionary

`financial_snapshot.csv` and `.parquet` use schema version `2.0` and one row per `(ticker, period)`. `period_type` is `quarter` or `year`. Monetary units remain source-dependent; when source files do not declare a unit, `operating_cash_flow_normalized_unit=unknown` and `operating_cash_flow_unit_status=unit_unknown`. Unknown is not equivalent to VND.

## Compatibility fields

Core scalar fields such as `revenue`, `net_profit`, `equity`, `operating_cash_flow`, `roe`, and `roa` remain available. `operating_cash_flow` is the compatibility scalar: valid TTM has priority; otherwise the latest reported value is retained. Consumers needing exact basis must use the parallel OCF fields and metadata.

## Advanced fields

Each advanced scalar is accompanied by status/provenance columns where applicable:

- `ebit`, `ebitda`, `interest_expense`, `retained_earnings`, `depreciation`, `amortization`, `depreciation_and_amortization`, and `sga`;
- `*_status`, `*_basis`, `*_reason`, `*_formula`, `*_inputs`, `*_source`, and `*_period`;
- `selling_expense` and `general_admin_expense` remain reported scalar inputs for SG&A.

`derived` requires formula and inputs. `not_applicable` is used for corporate-only SG&A on bank, securities, insurance, and unknown profiles. Missing values remain null and are never converted to zero.

The snapshot does not contain filing publication dates. It is suitable for current analysis but not strict historical backtests without a separate availability-date layer.
