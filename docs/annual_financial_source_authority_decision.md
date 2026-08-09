# Canonical annual financial source authority decision

Decision date: 2026-08-09. Scope: one bounded corporate-research pilot only. No provider
or issuer endpoint was called; the pilot uses one already retained immutable artifact.

## Selected route

**Issuer investor-relations audited annual consolidated financial statements** are the sole
selected source class. The retained PAN FY2024 report is the evidence-bearing pilot:

- issuer: The PAN Group Joint Stock Company;
- report: audited consolidated financial statements for the year ended 2024-12-31;
- publication date: 2025-03-31;
- immutable SHA-256: `f1d6fb0dde557d9e098e13cc10ca0b0506e10e446f3ac6dc8122c4fa560df006`;
- evidence ID: `35b50a2ddd09153fb18c46b3ee3530420c5f67b715966fb0cb1f7cec4b8618b9`;
- provenance URL: `https://storage.thepangroup.vn/Data/2025/03/31/20250331-pan-audited-2024-consolidated-fs-638790383114311854.pdf`.

The artifact is retained under the established governed-official-evidence contract and its
manifest hash verifies before any citation can be used. The report is consolidated, annual,
and VND-denominated. No superseding FY2024 document is retained, so no restatement choice was
made; an older comparative-column revision is not treated as a FY2024 restatement authority.

## Candidate decision

| Candidate class | Decision | Reason |
| --- | --- | --- |
| Exchange disclosure pages | Rejected | Current registry exposes notices/market items, not a qualified audited annual-financial-statement acquisition contract. |
| Issuer IR audited annual consolidated statement | Selected | It supplies issuer authority, immutable document provenance, reporting period, consolidated scope, currency/unit, statement page, and explicit line-item extraction. |
| VCI/KBS provider financial responses | Rejected | Their retained evidence does not establish the document provenance, consolidated scope, scale/currency, or supersession semantics required for annual research facts. |

## Bounded PAN materialization

All values are VND, annual FY2024, consolidated. The first four citation IDs below are new
append-only financial-identity records; net income was already retained and is preserved.

| Metric | Value | Page | Citation ID | Extraction |
| --- | ---: | ---: | --- | --- |
| `operating_cash_flow` | -1,739,184,049,701 | 13 | `6c80bbbded0e2045c6acd11694fdaef7d598dca4ea73e2d2227cc8b48d0da250` | Direct: Net cash used in operating activities |
| `net_income` | 1,167,068,107,309 | 12 | `7f4f846e6573deb3db256fb6f797390dd3a2d91e3aa4f4469c476be592263795` | Direct: Net profit after corporate income tax |
| `cash_and_equivalents` | 2,958,874,263,351 | 8 | `de985331e6e0170dd2afb323062f39407f39dccd9ebc2955ba51b2780e22988a` | Direct: Cash and cash equivalents |
| `total_interest_bearing_debt` | 11,699,678,520,506 | 10 | `309935543f10840478cd153e48d0d48d212f08a4333ae0be2ffaa070206aea97` | 11,493,025,595,010 short-term borrowing/finance leases + 206,652,925,496 long-term borrowing/finance leases |
| `shareholders_equity` | 8,859,450,516,042 | 11 | `21b5b6c9a78d20e58c4c143465d162d18bafc09b7bb322817a390b39177e5153` | Direct: Total equity |

`official_annual_financial_fact_projection.py` makes these verified citation records an
ephemeral input to the existing qualification and research projections. It writes neither the
database nor canonical fact shards; it also cannot use provider-reported values as substitutes.
The total-debt calculation is accepted only when both labelled statement components and their
exact sum are retained in the citation identity.

## Capability result and scale-out boundary

PAN is a `corporate` production-universe ticker, so the five same-period annual/consolidated
facts satisfy the existing research gate. The resulting PAN projection is
`research_eligible=true` for FY2024. HPG/VNM trusted `financial_canonical` retains strict
precedence.

This selects the source **class**, not an unrestricted crawl. `storage.thepangroup.vn` is the
provenance host of the retained artifact but is not yet an approved `issuer_ir` host in the
current source registry. A new external PAN retrieval or another issuer host requires an
owner-approved registry/allowlist addition before acquisition. The next canonical milestone is
`BOUNDED_OFFICIAL_FINANCIAL_EVIDENCE_SCALE_OUT`.
