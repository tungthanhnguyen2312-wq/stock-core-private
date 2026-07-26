# Financial Statement Semantic Qualification

Installed vnstock 4.0.4 evidence:

- `vnstock/api/financial.py`, `Finance.__init__` and dynamic methods accept only
  provider, symbol, `period`, `get_all`, and `show_log`.
- `vnstock/explorer/vci/financial.py`, constructor lines 90-104, validates only
  `year`/`quarter`; `process_data` lines 349-363 selects response `years` or
  `quarters`. No consolidated/separate parameter, response-scope parser,
  currency mapping, scale mapping, or cumulative-basis marker was found.
- KBS and VCI public financial calls for HPG/PAN/VCB therefore prove requested
  annual versus quarterly selection only. They do not prove statement scope,
  unit/currency, scale, or standalone-quarter basis.

Official evidence bridge: the hash-qualified HPG Annual Report 2025, page 35,
table *Revenue, total assets, equity of the Group for 2014-2025*, explicitly
uses Group and billion VND. It corroborates the already retained annual HPG
official-evidence facts only. It is not a financial-statement title/header and
does not link to any VCI raw observation, cash-flow/debt item, quarter, PAN, or
VCB. No semantic assignment was retained or applied.

| Semantic | Result | Reason |
|---|---|---|
| Statement scope | unqualified | no provider selector/field; PDF has no exact raw-observation linkage |
| Currency / scale | unqualified | provider response lacks metadata; PDF page 35 applies only to its cited table |
| Quarterly basis | unqualified | provider selects quarters but labels no standalone/cumulative basis |

The existing observation IDs and unknown semantic states remain unchanged.

## Addendum: bounded exact-match qualification (HPG, annual, FY2024 only)

The provider-level finding above is unchanged: VCI/vnstock still exposes no
scope/currency/scale/basis metadata, and this addendum does not alter that for
the general case. It records one narrow, citation-backed exception found by
sourcing the actual audited financial-statement filings (not the annual-report
narrative) directly from the issuer's own document host.

Two new documents were retrieved from `file.hoaphat.com.vn` (same authority
domain as the existing evidence): the FY2024 audited **consolidated**
statements (forms B01/B02/B03-DN/HN, Circular 202/2014/TT-BTC; signed
2025-03-24) and the FY2024 audited **separate** statements (forms
B01/B02/B03-DN, Circular 200/2014/TT-BTC; same signing date). Both are
scanned/image PDFs (no text layer); pages were rendered and read directly.
The consolidated statement's own title states scope ("hợp nhất") and its
column headers state currency ("VND") at full precision (no scale factor).

All 9 retained raw observations for ticker=HPG, reporting_frequency=annual,
reporting_period=2024 (3 balance_sheet, 2 income_statement, 4 cash_flow items)
were compared against the consolidated statement's line items by exact
numeric match — no rounding, no inference. All 9 matched exactly, to the
integer VND. The separate statement's corresponding lines (e.g. cash of
319,257,876,941 vs. the consolidated/retained 6,887,646,139,852) are
materially different, confirming the match is scope-discriminating rather
than coincidental.

This qualifies, by direct citation, exactly those 9 observation IDs as
statement_scope=consolidated, currency=VND, unit_scale=1. It does not
extend to: any other reporting period, any quarterly observation, PAN, VCB,
or any HPG item outside this list of 9. `observations.jsonl` itself was not
modified (append-only; no existing row, hash, or ID was changed). The linkage
is recorded as new, additive records:

- `dashboard-runtime/data/official-evidence/manifest.json` — 2 new entries
  (evidence_id `a7c3711d1b02c131...`, consolidated, used for citations;
  evidence_id `cd4c4754fb807ef0...`, separate, retained for disambiguation
  only, no citations recorded against it). The pre-existing annual-report
  entry is untouched.
- `dashboard-runtime/data/official-evidence/qualification_citations.jsonl` —
  new file, 9 records, each linking one existing `observation_id` to the
  consolidated evidence_id with exact page/mã-số citation and the matched
  value. IDs are deterministic sha256 hashes over canonical JSON of their
  identifying fields (same convention as `_hash` in
  `financial_observations.py`), so re-generating them is idempotent.

Downstream gates (Fundamental Quality, FCFF, Net-Net, Relative Valuation) are
keyed off canonical projections derived from `observations.jsonl`'s own
`statement_scope`/`raw_currency`/`raw_scale` fields, which remain `unknown`
for all 368 raw observations including these 9 — so this addendum does not
by itself change any downstream gate; it is evidence available for a future,
explicitly-scoped decision about whether/how citation-backed exceptions
should feed canonical projection.
