# HPG FY2024 EBITDA Qualification and Historical EV/EBITDA Unlock

Bounded to HPG, one valuation date: 2024-12-31 (the same historical snapshot as
`historical_relative_valuation_snapshot.md`). `ebitda` was never qualified as of that
document; this pass qualifies it and unlocks `ev_ebitda` only.

## Why the retained VCI observations alone could not support it

`financial_observations.py`'s retention allowlist (`_CODES`) has never included
`operating_profit`, `depreciation`, `amortization`, or a combined D&A item -- for HPG or
any other ticker, in any period. `observations.jsonl` therefore has no raw VCI
observation for any EBITDA component, so the existing observation-store +
`qualification_citations.jsonl` cross-check pattern (raw VCI value verified against an
official PDF value) cannot be used here. Fetching new live VCI data to fill that gap
would go beyond "already-retained" and is out of scope for this pass.

## Evidence used instead: standalone PDF-cited facts

The already-qualified audited consolidated FY2024 PDF (`evidence_id`
`a7c3711d1b02c131a87fef4a0f5bd4d5fbd780bbb0c07665111a358a2ddcd2a8`,
`hpg-consolidated-fy2024-audited.pdf`) was read directly for three figures, the same
"standalone, PDF-cited fact" pattern already established by
`share_basis_citations.jsonl` (share counts are also never part of a raw VCI
observation, so that file already has no `observation_id` to cross-check against).
Retained additively in new `data/official-evidence/ebitda_component_citations.jsonl`,
verified by new `semantic_evidence_bridge.load_verified_ebitda_components`: each entry's
`evidence_id` must still hash-verify against `manifest.json`, its `citation_id` must be
the deterministic hash of its own content, its `metric` must be in the supported set, and
no two citations may conflict for the same (ticker, metric, period) -- fails closed
otherwise, exactly like every other loader in `semantic_evidence_bridge.py`.

| Metric | Value (VND) | Statement | Mã số / line | Page |
|---|---|---|---|---|
| `profit_before_tax` | 13,693,502,261,178 | Consolidated income statement, B02-DN/HN | 50 "Lợi nhuận kế toán trước thuế (50 = 30 + 40)" | pdf p.11 (printed p.10) |
| `interest_expense` | 2,287,360,810,880 | Consolidated income statement, B02-DN/HN | 23 "Trong đó: Chi phí đi vay" | pdf p.11 (printed p.10) |
| `depreciation_and_amortization` | 6,915,671,331,197 | Consolidated cash flow statement, B03-DN/HN (indirect method) | 02 "Khấu hao và phân bổ" | pdf p.13 (printed p.12) |

All three: HPG, annual, FY2024, `statement_scope="consolidated"`, `currency="VND"`,
`unit_scale=1`. `interest_expense`'s value is independently corroborated by the
already-qualified `qualification_citations.jsonl` entry for raw item `interest_expenses`
(same PDF, same page, same figure, sign-rule `raw == -official`); it is re-cited here as
its own clean positive fact rather than reused from that pipeline, so this new sidecar's
verification does not depend on the observation-store's sign convention.

## Formula selected, and why the alternative was rejected

`ebitda = profit_before_tax + interest_expense + depreciation_and_amortization`
(`semantic_evidence_bridge.EBITDA_FORMULA_VERSION =
"ebitda_v1_profit_before_tax_plus_interest_expense_plus_depreciation_and_amortization"`).

= 13,693,502,261,178 + 2,287,360,810,880 + 6,915,671,331,197 = **22,896,534,403,255 VND**.

The other named candidate, `operating_profit + D&A`, was audited
(`operating_profit` = 13,267,005,585,330 VND, mã số 30, "Lợi nhuận thuần từ hoạt động
kinh doanh") and rejected, not omitted by default: HPG's own statement prints operating
profit's formula as `{30 = 20 + (21-22) - (25+26)}` -- gross profit plus (financial
income minus financial expense) minus opex. It is therefore already net of financial
income/expense (including most of interest expense) rather than a pre-interest figure,
so adding back only D&A would not reverse out interest and would not match the literal
Earnings-Before-Interest-and-Tax meaning of the acronym. `profit_before_tax +
interest_expense` does reverse out both tax and the disclosed interest-expense
component, which is why it is the qualified definition. The two formulas diverge
materially (20,182,676,916,527 vs. 22,896,534,403,255 VND, ~13%), which is exactly the
silent-choice risk this pass was told to avoid -- resolved here by evidence (HPG's own
printed operating-profit formula), not by convention or preference.

## D&A: combined by the evidence, and one exclusion

The cash-flow statement's own caption, "Khấu hao và phân bổ" (mã số 02), already
combines depreciation and amortization into one line -- the evidence does not
distinguish them for HPG FY2024, so they are not split here. A second, separate addback
on the same statement, "Phân bổ lợi thế thương mại" (amortization of goodwill from a
business combination) = 12,295,891,969 VND, is deliberately excluded: it is a distinct
line from the combined D&A caption and relates to acquisition accounting rather than
ongoing operating assets, so folding it in would not be "any combined
depreciation-and-amortization line" as evidenced -- it would be a fourth, uncited
formula ingredient. Neither this amount nor `operating_profit` is double-counted or
silently substituted; both are recorded in the canonical record's
`derivation_lineage.excluded` for auditability.

## Canonical record and wiring

`semantic_evidence_bridge.derive_ebitda` emits one canonical record per ticker (`None`
when any of the three components is missing, or when they disagree on
`reporting_period`, `statement_scope`, `currency`, or `unit_scale` -- fails closed,
never merged across a mismatch):

```
canonical_metric: "ebitda"
value: 22896534403255
statement_scope: "consolidated" | currency: "VND" | unit_scale: 1
period_identity: {period: "2024", period_type: "annual"}
quality_state: "available" | derivation_status: "derived"
formula_version: "ebitda_v1_profit_before_tax_plus_interest_expense_plus_depreciation_and_amortization"
derivation_lineage: {formula, formula_version, components: [...], excluded: [...]}
```

`export_ai_bundle.load_financial_canonical` calls `load_verified_ebitda_components`
once and `derive_ebitda` once per ticker, appending the record (when not `None`) into
the same additive `canonical["records"]` list that observation-store and
official-evidence records already flow through -- no new input key at the
`evaluate_relative_valuation` call site. `_financial_input` picks it up exactly like any
other canonical metric, so `financial["ebitda"]` becomes available for HPG with no
change to `relative_valuation.py`: `ev_ebitda` was already wired generically there
(`specs["ev_ebitda"] = "ebitda"`, same `market_cap + total_debt - cash_and_equivalents`
enterprise-value numerator already qualified for `ev_sales`) -- it was only ever waiting
on a qualified `ebitda` input.

## Result at 2024-12-31

Before this pass: `ev_ebitda` = unavailable (`required_input_missing`), as recorded in
`historical_relative_valuation_snapshot.md`.

After this pass: `ev_ebitda` = **8.86** (`(126,837,641,466,000 + 82,963,129,469,555 -
6,887,646,139,852) / 22,896,534,403,255`), `is_actionable: true`. `pe` 10.55, `pb` 1.11,
`ps` 0.91, `ev_sales` 1.46 are byte-identical to before -- confirmed by
`tests/test_ebitda_qualification.py::test_ev_ebitda_before_after` and by directly
re-running `evaluate_relative_valuation` against the real runtime evidence with and
without `ebitda_component_citations.jsonl` present.
