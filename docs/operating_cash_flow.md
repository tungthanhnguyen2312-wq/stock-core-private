# Operating Cash Flow period policy

Phase 3 separates cash flow values by basis instead of treating every financial
snapshot row as a standalone quarter.

## Output fields

- `operating_cash_flow_reported`: the non-null value exactly reported for the source period.
- `operating_cash_flow_ytd`: the reported cumulative YTD value when the source profile confirms that basis.
- `operating_cash_flow_quarter`: a reported standalone quarter, or a difference between two comparable YTD observations.
- `operating_cash_flow_ttm`: the sum of four contiguous and comparable standalone quarters.
- `operating_cash_flow`: backward-compatible scalar; valid TTM first, otherwise reported OCF for the same source period.

The output also records source period, basis, basis confidence, source, report
scope, audit status, raw unit, normalized unit, unit multiplier, and unit status.

## Comparability rules

YTD is converted to a standalone quarter only when the prior YTD observation is
available in the same fiscal year and source, report scope, audit status, and
normalized unit are equal. Q1 YTD is numerically the standalone Q1. TTM requires
four contiguous standalone quarters with the same comparability attributes.

A null TTM never overwrites a reported value. The context builder selects the
latest non-null reported OCF when the latest general financial period has no
cash-flow observation.

## Units

Declared `VND`, `thousand VND`, `million VND`, and `billion VND` units are
normalized to VND while preserving sign. When the raw statement has no unit
metadata, the output uses `raw_unit=null`, `normalized_unit=unknown`, and
`unit_status=unit_unknown`; magnitude is not guessed.

## PAN result

PAN has reported KBS OCF at `2025-Q4` of `-2,885,506,210,000`. The configured KBS
quarter cash-flow basis is YTD. Q3 is absent, so Q4 cannot be converted to a
standalone quarter and TTM remains unavailable with status
`insufficient_periods`. The later general financial row at `2026-Q1` is skipped
for OCF selection because it has no OCF value.

Generate the diagnostic with:

```powershell
python tests/diagnostics/ocf_audit.py --ticker PAN --output reports/ocf_diagnostics_pan.json
```
