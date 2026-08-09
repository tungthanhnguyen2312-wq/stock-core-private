# Annual financial evidence materialization hardening

Completed 2026-08-09 against exactly two retained issuer PDFs. The source PDFs were
not changed. Derived sidecars are page-preserving local OCR output under
`operations-review/governed-official-evidence-v1/derived/annual_financial_ocr_materialization_v1/`.

The bounded adapter uses local `tesseract v5.5.0.20241111` and in-memory PyMuPDF
rasterisation at 216 DPI. A sidecar identity binds the immutable document SHA-256,
Tesseract version, materialization contract, PDF page, and OCR-text SHA-256. Citation
promotion additionally requires exact OCR label/value occurrence and a recorded visual
check of the original PDF page. OCR never becomes authority by itself.

## Results

PNJ source `71eb69f97fab83a36ed3dca032193cfc24754f416d24d4ad136f198ab2a73099`
(49 pages; 4 pages processed; VND):

| Metric | PDF page | Raw displayed value | Citation ID |
| --- | ---: | ---: | --- |
| `cash_and_equivalents` | 7 | 1,122,712,392,130 VND | `f4bcfd1cd04cd4df339ccf9b77c7c38d886ebe0b78e39e7d38e6f00cd7a60a67` |
| `net_income` | 10 | 2,112,916,282,946 VND | `a21ba424c427b7be78185086033a653bc68409528c8344928920ba515dd878ba` |
| `operating_cash_flow` | 11 | 83,185,174,755 VND | `4098ee1618c0d58c538cdd659138725b5c0b1a9ee94412c11ddedf6aa06dfbb8` |
| `shareholders_equity` | 9 | 11,255,306,630,522 VND | `3e78c7bd495ff416a54d80db3cf5ff63606ec65258714105b9c3b2c0aaf8b97a` |

PNJ's page 9 reports short-term borrowings but no labelled long-term-loans component.
The approved debt contract requires both components, so `total_interest_bearing_debt`
is intentionally absent (`REQUIRED_DEBT_COMPONENT_MISSING`); no zero was inferred.

PVD source `ba70100acf9391a85992e67ebc1a3d68da33e50402a17e860f579e320f5f2d14`
(108 pages; 4 pages processed; USD):

| Metric | PDF page | Raw displayed value | Citation ID |
| --- | ---: | ---: | --- |
| `cash_and_equivalents` | 6 | 87,254,694 USD | `402c2ca9ddd2a31b27eb0355b61cdef10bf6ee0467329dbc3484931c28ef1f47` |
| `net_income` | 8 | 28,074,925 USD | `a5af56efc5e95d3a63b0bdfc06520d6386d1a4ec6779d9077f24ead2e86f38c2` |
| `operating_cash_flow` | 9 | 41,707,698 USD | `3acfdcf5ad998123351f5c2d6220e189524f75a0914adeff3f16af66470309aa` |
| `shareholders_equity` | 7 | 635,711,153 USD | `c642f35f6dd6c9a649a383f9fa1df47487e016e7e1a73979371ef92aba1f8501` |
| `total_interest_bearing_debt` | 7 | 20,090,244 + 100,645,129 = 120,735,373 USD | `5428a0baf42decbf5839c922bd0e8a4975836dba1e9f083e224e8a6c442efb8a` |

PVD explicitly presents USD. The materializer preserves that reporting currency and
unit scale of one; it does not invent a VND foreign-exchange conversion. The five values
are same-period, annual, consolidated, and accepted by the existing qualification and
research contracts. PVD's historical research projection is available and remains
non-actionable. PNJ remains non-eligible at four of five.

## Safety and reuse assessment

The bridge validates source-page materialization metadata against manifest SHA-256 and
rejects malformed OCR metadata, unresolved numeric ambiguity, unverified pages, missing
debt components, and cross-ticker evidence. Parentheses remain accounting negatives.
No DB, provider, market-data, DNSE, or generated runtime bundle was changed.

`SCAN_ONLY_MATERIALIZATION_REUSABLE: YES` for English/VAS-style audited consolidated
face statements with legible rows. It is deliberately a bounded adapter, not an OCR
backlog or a generic document platform. FPT remains `SOURCE_LOCATOR_REQUIRED` and was
not queried.
