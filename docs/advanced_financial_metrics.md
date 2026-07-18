# Advanced financial metrics

Phase 4 materializes advanced metrics from reported fields in the financial
mapping registry while retaining a scalar value and parallel provenance fields.

## Priority and formulas

- EBIT: reported EBIT first; otherwise `profit_before_tax + interest_expense`.
- EBITDA: reported EBITDA first; otherwise EBIT plus reported combined D&A, or
  EBIT plus both separately reported depreciation and amortization.
- Retained earnings: reported end-period total first; otherwise the sum of the
  explicitly separated prior-year and current-year undistributed earnings.
- SG&A: reported SG&A first; otherwise selling expense plus general admin expense.

Every metric records `status`, `basis`, `reason`, `formula`, and JSON-encoded
`inputs`. Derived values always include formula and inputs.

## Safety rules

- Canonical interest expense uses only validated interest-specific mappings;
  total financial expense is not accepted.
- EBIT derivation requires interest expense normalized to a positive expense.
- A combined depreciation-and-amortization value may be used directly for
  EBITDA, but is never split into invented depreciation and amortization values.
- Corporate SG&A formulas are not applied to bank, securities, insurance, or
  unknown profiles; those outputs are `not_applicable`.
- Share premium, development funds, minority interest, and other equity reserves
  are never included in retained earnings.

## PAN result at 2026-Q1

- EBIT: `600,682,628,000`, derived from reported PBT and interest expense.
- SG&A: `353,782,849,000`, derived from selling and general admin expenses.
- Retained earnings end period: `2,618,950,443,317`, reported.
- EBITDA: missing with `insufficient_periods`, because amortization or a reported
  combined D&A value is unavailable for the selected period.

Generate the diagnostic with:

```powershell
python tests/diagnostics/advanced_financial_audit.py --ticker PAN --output reports/advanced_financial_metrics_pan.json
```

## Snapshot schema v2

Phase 9 materializes these fields in both snapshot formats. Flat `*_status`, `*_basis`, `*_reason`, `*_formula`, `*_inputs`, `*_source`, and `*_period` columns preserve CSV compatibility. Scalar fields remain unchanged. Missing EBITDA is not fabricated, and unknown units are not promoted to VND.
