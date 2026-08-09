# Bounded official financial evidence scale-out

Decision date: 2026-08-09. Initial cohort: PNJ, FPT, and PVD. Cohort 2 then bounded new issuer
work to POW, QNS, and NVL only. HPG/VNM/PAN are controls and SSI/EVF remain outside the corporate
research archetype. No provider financial endpoint was called.

## Domain governance and acquisition results

| Ticker | Issuer-domain evidence | Exact FY2024 filing result | SHA-256 / blocker |
| --- | --- | --- | --- |
| PNJ | `www.pnj.com.vn` Financial Reports directly links `cdn.pnj.io` | Retained: consolidated financial statements, year ended 2024-12-31, published 2025-03-28 | `71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099`; textless PDF, `needs_ocr` |
| FPT | `fpt.com/en/ir/report` links issuer-owned FY2024 reporting storage | Exact audited-consolidated filing URL attempted once | HTTP 404; no artifact, no URL variation guessed |
| PVD | `www.pvdrilling.com.vn` Financial Statements page lists FY2024 audited consolidated statements | Retained: Deloitte audited consolidated financial statements, year ended 2024-12-31, published 2025-03-21 | `ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14`; textless PDF, `needs_ocr` |

The registry admits exactly the demonstrated issuer hosts, their explicitly linked storage/CDN
hosts, and PAN's existing retained `storage.thepangroup.vn` host. It does not introduce a
wildcard storage rule. PNJ and PVD document covers visually confirm issuer identity, FY2024,
and consolidated scope; PVD's cover also states audited.

## Qualification result

No five-metric citation set was materialized for PNJ or PVD: there is no direct text layer and
this milestone does not build an OCR platform or infer values from a visual cover. FPT has no
retained document. Therefore all three remain non-eligible in the Pillar A annual projection;
no provider observation substitutes for a missing annual filing fact.

The bridge now rejects an attempted citation whose evidence manifest belongs to another ticker
(`evidence_ticker_mismatch`). This makes the multi-ticker boundary explicit. PAN remains
five-for-five qualified; HPG/VNM trusted source precedence and all market gates are unchanged.

## Efficiency and next step

- documents attempted: 3;
- documents retained: 2;
- citations materialized: 0;
- qualified facts: 0;
- additional research-eligible tickers: 0;
- `QUALIFIED_FACTS_PER_DOCUMENT = 0.0`;
- `RESEARCH_ELIGIBLE_TICKERS_PER_DOCUMENT = 0.0`.

That follow-on materialization route completed before Cohort 2. FPT still requires a new
issuer-supplied exact locator; it was not retried or broadened into a crawl/provider fallback.

## Cohort 2 closeout

| Ticker | Deterministic issuer result | Qualification result |
| --- | --- | --- |
| PNJ | Retained Note 19 labels only short-term borrowings of VND 3,341,542,016,760. It supplies no labelled long-term borrowing or finance-lease component. | 4/5; `REQUIRED_DEBT_COMPONENT_MISSING`. |
| POW | Official material located was an audit-appraisal report, not the audited consolidated statements; no exact filing locator was acquired. | `ISSUER_FILING_LOCATOR_REQUIRED`. |
| QNS | The one exact issuer-published FY2024 report URL was requested through the registry and returned HTTP 404. No variation was guessed. | `SOURCE_LOCATOR_REQUIRED`. |
| NVL | Retained audited consolidated FY2024 issuer PDF; SHA-256 `078fe614549d6f139b3cd3e9bdcd9f99a533b03c067c5018a989166cb2eab3d3`; scan OCR materialized pages 8, 10--13. | 5/5; VND; historical-only/non-actionable. |

NVL's five cited values are cash `4,607,601,921,683`, net income `(4,394,642,203,703)`,
operating cash flow `(5,971,178,115,653)`, shareholders' equity `47,291,024,358,614`, and
interest-bearing debt `61,565,854,654,966` (the only permitted component sum:
`36,978,198,251,788 + 24,587,656,403,178`). The registry admits only `qns.com.vn` and
`novaland.com.vn` plus their `www` forms; it adds no wildcard or mirror. FPT was not retried.
