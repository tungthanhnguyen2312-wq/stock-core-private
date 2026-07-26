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
