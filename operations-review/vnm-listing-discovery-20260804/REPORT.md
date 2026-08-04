# VNM governed listing-page discovery pilot — 2026-08-04

One bounded, governed announcement-index acquisition for VNM. **One real network request.** No
candidate document was acquired.

## Entry URL provenance

| | |
| --- | --- |
| Source | `vsdc` (Vietnam Securities Depository and Clearing Corporation), `activation: approved` |
| Entry URL | `https://vsd.vn/en/alc/6` |
| Observed in | `operations-review/vnm-2024-cash-dividend-official-evidence/vsdc-record-date-notice.html` |
| Exact observation | breadcrumb `<li><a href="/en/alc/6" title="Securities registration institution - related business news">` |
| What that artifact is | the retained official VSDC notice `/en/ad/177392` for VNM, `sha256:4a27d077058566f2403b0a34fe3b959322116c0ddabfe7be4725e42c4d26ecd5`, retained 2026-07-29 |

The URL was **not** constructed from an assumed pattern. It is the category listing that the one
retained VNM official document declares itself to belong to. The taxonomy is corroborated by a
second, independent retained artifact: `vsdc-vcb-listing-change-execution.html` carries the same
breadcrumb shape under `/en/alo/MEMBER` → `/en/alc/4`.

A VSDC search URL was considered and rejected: the site's search box has no `<form>`, no
`action` and no named fields (only `id="gSearchAdvText"`), so any search URL would have been
invented rather than read.

## Governance

| | |
| --- | --- |
| Approval instant | `2026-08-03T07:00:00Z`, verdict `verified` |
| Admission | `admitted` / `admitted_by_registry` for (`vsdc`, `announcement_index_page`) |
| Rate interval | 15 s (vsdc) |
| Redirect limit | 5, from `global_policy.max_redirects` |
| Call path | `tools/run_official_listing_discovery.py` → `official_document_acquisition.acquire()` → `admit()` → `fetch_http` |
| Requests | 1. Redirects 0, retries 0. |
| Bypass check | no `requests`/`urllib`/`httpx`/curl/wget/browser call anywhere in the path |

## Stored artifact

```
sha256        97778a8215123f61db098e02682ff7e9518260aa728fa4a7224821ca1886cfd0
document_id   43ee4065a9fb9c96dec77e1e51c365604f169d6ec108587f621e9ecc0d63e8d7
bytes         51,080   content-type text/html   HTTP 200
final_url     https://vsd.vn/en/alc/6   (unchanged — no redirect)
relative_path documents/VNM/2026/announcement_index_page/97778a…cfd0.html
```

The manifest holds exactly **one** record. Re-running the pilot returned `cached_valid` and made
no second request, which is the acquisition contract's cache rule doing its job.

## Result: 0 VNM candidates from the acquired page

The page is a chronological **all-issuer** feed. Its 14 announcements were all dated
2026-08-03/04 — `DAG`, `PSI`, `OCB12517`, `OCB12521`, `CTG12414`, `CTR`, `SCM12601`, `CTG12223`,
`CTG12415`, `VSN`, `CTG12224`, `PTB`, `TPB12534`, `BRR`. VNM's most recent VSDC announcement is
2026-06-17, outside the window. The string `VNM` does not occur in the stored bytes.

This is a yield limit of the entry URL, not a failure of the machinery: the parser correctly
identified 14 coded announcements and rejected all 14 as `different_issuer`. **No second listing
page was fetched** — that is an explicit boundary of this milestone.

## Offline VNM candidates (no network)

Parsing the **already-retained** VNM notice `/en/ad/177392` yields 10 deterministic candidates
from its "Issuer's news" block. This is an offline read of an artifact retained on 2026-07-29;
it is not an acquisition. Discovery ledger `sha256:d830ca1b88e97270452d619149b60a7b2b6d291a4cc8c820e5600f1da134346d`, all 10 `new`, all crossing the retention seam with `source_id: vsdc`.

| # | candidate_id | visible date | visible title | URL |
| --- | --- | --- | --- | --- |
| 1 | `ca2995ad96a94084` | 2026-06-17 | VNM: Residual Payment of 2025 cash dividend | `/en/ad/197038` |
| 2 | `051f3bdbc2efb63c` | 2026-02-26 | VNM: 2026 Annual General Meeting | `/en/ad/192327` |
| 3 | `3ac82e98bd22e717` | 2025-10-02 | VNM: Payment of 2024 Residual Cash Dividend and 1st Advance Payment of 2025 Cash Dividend | `/en/ad/187729` |
| 4 | `efd0d815b68ed4d5` | 2025-05-08 | VNM: Correcting information of the notice of the record date | `/en/ad/182559` |
| 5 | `56312ca0bd63d194` | 2025-04-29 | VNM: First Residual Payment of 2024 Cash Dividend | `/en/ad/182377` |
| 6 | `8e8b6a2d17b86ddf` | 2025-02-05 | VNM: 2025 Annual General Meeting | `/en/ad/178989` |
| 7 | `23d1d0f23e013215` | 2024-09-04 | VNM: Last Payment of 2023 cash dividend and First Advance Payment of 2024 Cash Dividend | `/en/ad/174349` |
| 8 | `e9988046d4e7f990` | 2024-03-08 | VNM: 2024 Annual General Meeting and Third Advance Payment of 2023 Cash Dividend | `/en/ad/168521` |
| 9 | `5079c28e4047dbed` | 2023-12-14 | VNM: Second Advance Payment of 2023 Cash Dividend | `/en/ad/165609` |
| 10 | `ecf6bc12bd8c68c9` | 2023-07-18 | VNM: Payment of 2022 Residual Cash Dividend and First Advance Payment of 2023 Cash Dividend | `/en/ad/160128` |

Issuer, date and title are **direct page facts**. Document class is an **inference** from the
subject line and is labelled as such in the parser output.

## Bearing on `2,089,955,445`

**None of the 10 can corroborate it, and that is a finding, not a gap.** Read from the retained
notice body: a VSDC cash-dividend record-date notice states issuer name, securities code, ISIN,
par value, trading platform, securities type, record date, payment rate, payment time and
payment place — and **no share count of any kind**.

The VSDC class that does carry an absolute registered share quantity is *"adjustment of the
number of registered shares"*, observed twice: `CTR: Adjustment of the number of registered
shares` on the page acquired today, and `VCB: Certification of the 10th adjustment of the number
of the registered shares` in the retained VCB artifact. **No such VNM notice appears anywhere in
the retained window (2023-07 → 2026-06).**

Consistent with VNM having had no capital-structure event in that window — but the block is a
10-item sidebar, not a complete history, so absence here is **not** evidence of absence. No fact
was written anywhere from this observation.

## Rejections

From the acquired page (96): `no_issuer_code_prefix` 77 (site chrome, pagination digits, nav),
`different_issuer` 14, `no_visible_title` 3, `host_outside_approved_source` 1
(`https://mail.vsd.vn/owa/`), `unsafe_or_unusable_url` 1.

From the retained notice (130): `no_issuer_code_prefix` 113, `different_issuer` 10 (incl. bond
codes `NAB12504`, `BAB12506`, `BHB12501`, `HDC12502` — a prefix match, not a substring match,
which is why `NAB12504` does not match `NAB`), `unsafe_or_unusable_url` 3, `no_visible_title` 3,
`host_outside_approved_source` 1.

## Non-effects

No production database, generated bundle, dashboard artifact, ledger, resolver output, price
basis, adjustment factor, `qualified_official`, `corroborated_period_end` or `is_actionable` was
read for write or changed. No observation was extracted; no promotion was performed. The
acquired page cannot enter the evidence store — `official_document_store.adopt_retained_document`
refuses `announcement_index_page` by name, under test.
