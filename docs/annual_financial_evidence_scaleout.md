# Bounded official financial evidence scale-out

## Next official financial evidence cohort closeout (2026-08-11)

The newly owner-bounded follow-up is exactly FPT and PNJ, the two unresolved Cohort 3 issuer
blockers. It is a finite blocker-resolution cohort, not a re-run of Cohort 3/4 or an arbitrary
new issuer cohort.

| Ticker | Retained official filing | Qualification result |
| --- | --- | --- |
| FPT | FY2025 audited consolidated statement through the approved `fpt.com` disclosure proxy; document ID `7c7ec0a1e76045bbb655f46f807165962516f3b16833a005a57af59a0e6bce32`, SHA-256 `630f61f6ef9f07d5c593c3bf8f65bad1d56ecbb091921296ed5c4e830ea070a4`. | Five VND annual/consolidated facts qualify from visually verified statement pages 8, 10--13. Debt is exactly `19,169,697,497,955 + 1,903,789,988,184 = 21,073,487,486,139`; FPT is historical-only/non-actionable research eligible. |
| PNJ | FY2025 audited consolidated statement directly linked by PNJ IR; document ID `d838e40adfa470cab934840ce579d8c7690a9e4bee98a93ca020a2b8292c749b`, SHA-256 `2a0f8591ed1acacb4a14849ccf807e596020c162fe7ed6adee999acaffd8b551`. | `REQUIRED_DEBT_COMPONENT_MISSING`: page 7 labels short-term borrowings only; page 7's non-current-liability rows are other long-term payables/provisions, not debt. No total is inferred and PNJ stays non-eligible. |

FPT uses the existing page-preserving OCR and append-only promotion contracts. The retained PDFs
and sidecars remain governed operational evidence, not Git-binary inputs. No market-data, DNSE,
Consumer, Dashboard, release, provider, target, probability, price, liquidity, or sizing contract
is changed. Further issuer acquisition requires a new explicit scope decision.

## Cohort 4 closeout (2026-08-11)

The owner-fixed Cohort 4 set is exactly SSI and QNS. The existing approved issuer paths are
`ssi.com.vn` and `qns.com.vn`; no third ticker, source-authority expansion, provider, crawl,
FPT/PNJ retry, or substitute occurred.

| Ticker | Retained official filing / qualification | Registration and projection |
| --- | --- | --- |
| SSI | FY2024 issuer audited consolidated filing, source URL `https://www.ssi.com.vn/upload/files/IR/20250320_SSI_Bao_cao_tai_chinh_hop_nhat_nam_2024_EN.pdf`, document ID `3fd72890fe43b78071d641b8d89523d4aa28e340d4f1904a90667f8c1d794bf0`, SHA-256 `38e5b9ba2fc951120be813b09df05fa2d8b152b3b95443c6cd108de8abf03b74`, published 2025-03-20 and observed 2026-07-30T00:00:00Z. Page 10 explicitly states consolidated VND current liabilities of `46,599,438,522,989` at 2024-12-31. | Added one manifest record and one page-verified `current_liabilities` citation. SSI remains `not_applicable` to the corporate five-metric projection: its securities funding is not corporate debt. |
| QNS | FY2024 issuer audited consolidated filing, source URL `https://qns.com.vn/upload/product/qns-cong-bo-bao-cao-tai-chinh-nam-2024-da-qua-kiem-toan-1740555452-17405559121.pdf`, document ID `5c264f4eaa4dd484299f49a71f9c8632e22ce4b017ae82e8619fed4237e7668f`, SHA-256 `faaa54465d1d6a3ca98bebf2a47a45096e21ee6ac3d1cfe3c95db3b1c0bae3e3`. | Existing manifest and five citations re-verified. Cash, equity, net income, operating cash flow, and debt (short-term borrowing plus explicit long-term nil) all qualify; no duplicate was added. |

SSI annual financial evidence is independent of the deferred SSI/VSDC corporate-action/ex-date
branch. Cohort 4 is `PARTIAL` and closed; a new owner-scoped evidence decision is required before
any further scale-out.

## Cohort 3 closeout (2026-08-11)

The owner-fixed Cohort 3 set is exactly FPT, PNJ, and PVD. This closeout does not reopen the
earlier bounded work, acquire a fourth ticker, or create a general locator crawl.

| Ticker | Minimum official evidence result | Qualification / registration result |
| --- | --- | --- |
| FPT | The previous exact audited-consolidated locator and two exact FY2024 annual-report locators identified from the official FPT IR route each returned HTTP 404. No URL variants were attempted and no bytes were retained. | `ISSUER_FILING_LOCATOR_RETURNED_404`; no hash, citation, or manifest registration. |
| PNJ | The retained FY2024 issuer-IR PDF remains hash-verified as `71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099`. Its reviewed debt evidence names only the short-term component. | `REQUIRED_DEBT_COMPONENT_MISSING`; no inferred debt total or registration. |
| PVD | The retained FY2024 issuer-IR audited consolidated PDF remains hash-verified as `ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14`, document ID `e03146183ffecb8cc94c5302edca1d8b5010e2121a00d18ae74e284cf0c306cb`. | Existing qualified manifest identity `8135440eea7f02bdfe52571488ec8a3f2590db4c4c48132f5b2615315afe8bb5` and five annual FY2024 USD citations re-verified; no duplicate registration. |

FPT's three exact issuer-IR locator identities, retained only as failed acquisition diagnostics,
are `https://fpt.com/-/media/project/fpt-corporation/fpt/ir/information-disclosures/year-report/2025/march/20250314---fpt---audited-consolidated-financial-statements-for-2024.pdf`,
`https://fpt.com/-/media/project/fpt-corporation/fpt/ir/information-disclosures/year-report/2025/april/20250402---fpt---annual-report-2024.pdf`,
and `https://fpt.com/-/media/project/fpt-corporation/fpt/ir/general-meetings-of-shareholders/fpt_annual_report_2024.pdf`.
Each returned HTTP 404. They are not retained source evidence and have no evidence hash or
manifest identity.

This Cohort 3 pass is `PARTIAL` and closed. Any continuation requires a separate owner-scoped
official-evidence decision for the exact missing FPT or PNJ source; it does not authorize another
attempt under this cohort.

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
