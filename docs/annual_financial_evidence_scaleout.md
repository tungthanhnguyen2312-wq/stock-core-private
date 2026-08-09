# Bounded official financial evidence scale-out

Decision date: 2026-08-09. Cohort: PNJ, FPT, and PVD only. The cohort is evidence-leverage
selected from the supported production corporates; HPG/VNM/PAN are controls and SSI/EVF remain
outside the corporate research archetype. No provider financial endpoint was called.

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

The right next milestone is `ANNUAL_FINANCIAL_EVIDENCE_MATERIALIZATION_HARDENING`: use a bounded,
reviewable extraction route for the two retained scanned statements and re-check FPT only from a
new issuer-supplied exact locator. It must not broaden into a crawl or provider fallback.
