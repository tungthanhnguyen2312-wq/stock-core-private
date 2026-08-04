# Official corporate-action ingestion and price-adjustment engine — design

Status, updated **2026-08-04**: **B1 delivered, owner-approved and now actually enforced on the
request path; B2–B4 machinery built and proven on a bounded offline slice; no crawl has been
performed and no official URL has yet been requested over the network.**

| step | state |
| --- | --- |
| B1 crawl contract and allowlist | **delivered and approved.** `config/official_source_registry.json` is enforced by `official_source_registry.py`; `approval_state = APPROVED` with `approved_at = 2026-08-03T07:00:00Z` and `approved_at_provenance` naming the clock. All four sources are `approved`. **An agent may not approve a source or write either approval field.** Since `3b4cc5f` the gate runs on every request, and since `2026-08-04` it also runs on every redirect hop and every retry. |
| B2 bounded crawler | **unblocked on governance, blocked on inputs.** The immutable blob store exists (`official_document_store.py`) and is exercised by adopting already-retained documents with no network request. What is missing is not permission but an **owner-supplied listing or notice URL per ticker**: the registry declares only document types, never a listing/search page type, and no listing URL exists in any approved artifact. See "What B2 still needs" below. |
| B3 classification and typed extraction | **built** (`corporate_action_events.py`), proven against retained HPG evidence. |
| B4 linking and execution status | **built** (`official_corporate_action_ledger.py`): cross-document linking, deduplication, supersession, lifecycle, deterministic replay. |
| B5 historical qualification | not started |
| B6 factors and dual price series | not started. One factor path exists and is fail-closed: the slice's event yields `not_ready` for want of an explicit official ex-date. |

The bounded vertical slice produced **1 qualified executed `stock_dividend`** for HPG from two
independent retained official documents, with citations, both source hashes and a stable replay
fingerprint. See `operations-review/p1e-milestone-20260803/P1E_OPERATIONS_REVIEW.md`.

The original design follows unchanged.

## Why this pillar exists

Price basis has been `unknown / verified: false` for the whole universe across every
attempt. The provider routes are recorded as exhausted in `docs/STATE.md`
(`VCI_PROVIDER_INTERNAL_ROUTE_BLOCKED_BY_RATIO_SEMANTICS`,
`ACTIVE_PRICE_PATH_SEMANTICS_UNQUALIFIED`, `DOCUMENTED_RAW_ADJUSTED_PATH_UNAVAILABLE`), and
the one external route that was approved has now been closed by the owner
(`EODHD_ROUTE_STATUS: REJECTED_BY_OWNER`, `docs/DECISIONS.md`).

The remaining route does not depend on any provider's willingness to document its own
adjustment policy: build the corporate-action ledger from official sources and compute the
adjusted series ourselves. Then the adjustment authority is our own ledger, and the question
"does VCI adjust, and how" stops being on the critical path.

This also stops being only about dividends. An event ledger of this shape is the foundation
for share-count changes, share basis, rights issues, charter-capital changes, dilution,
adjusted returns, event studies, and ownership/governance intelligence.

## What already exists and must be reused, not rebuilt

| module | what it already does |
|---|---|
| `official_document_discovery.py` | closed-world **validation** of caller-supplied listing/detail pages and their explicit links; never searches, crawls, paginates — and never parses. Document vocabulary and `source_id` come from the registry, so a candidate cannot be shaped that the gate would refuse for a reason discovery never checked |
| `official_document_acquisition.py` | bounded acquisition, registry-admitted **per request, per redirect hop and per retry**, with hashing |
| `official_document_retrieval.py`, `official_document_ocr_handoff.py` | retrieval and OCR handoff |
| `corporate_action_evidence_registry.py`, `evidence_registry.py`, `evidence_replay.py` | evidence registry with replay parity (`docs/adr/ADR-002`) |
| `corporate_action_ledger.py` | ledger MVP over qualified cash-dividend / stock-dividend / bonus events, deterministic ordering, immutable lineage, emits **0** adjustment factors by design |
| `evidence_promotion.py` | the only approved evidence write boundary (`docs/DECISIONS.md`) |
| `corporate_action_factors.py`, `point_in_time_adjusted_prices.py` | factor and adjusted-price computation, currently fed nothing |

The gap is not the ledger and not the adjustment maths. The gap is a **production ingestion
path**: today a human supplies each URL. Pillar B is the step from closed-world discovery to
a periodic, bounded crawler with an immutable event ledger behind it.

## B2 listing-page discovery — delivered 2026-08-04

The three blockers below are resolved for `vsdc`. The registry declares
`index_document_types: ["announcement_index_page"]` **for vsdc only**;
`official_listing_page_parser.py` reads candidate links out of one stored artifact with no I/O
of any kind; and the entry URL is observed in a retained artifact rather than assumed. One live
acquisition has run (`https://vsd.vn/en/alc/6`). See `docs/STATE.md` and
`operations-review/vnm-listing-discovery-20260804/`.

**An index page is a discovery input, never evidence.** It is acquirable so links can be read
from stored bytes, and `official_document_store.adopt_retained_document` refuses it by name, so
it cannot reach the observation ledger, the resolver, `qualified_official` or
`corroborated_period_end`. The two vocabularies are separate lists in the registry precisely so
that this is structural rather than a naming convention.

**What the pilot measured, and did not.** The chosen index is a chronological all-issuer feed;
it carried no VNM entry on the day it was fetched. Extending this to a ticker whose notice is
older than the feed window needs either a per-issuer index URL (none observed yet) or a
deliberate decision about pagination, which the closed-world contract currently forbids. That
is the next design question, and it is a question about *inputs*, not about the machinery.

## What B2 needed (historical, resolved for vsdc)

Governance was not the blocker; **inputs and one capability were.** A bounded discovery
pilot for any single ticker required all three, and none could be supplied by an agent:

1. **An owner-supplied entry URL.** Every official URL in the repository is a terminal
   document — the retained `https://vsd.vn/en/ad/177392` VSDC notice, issuer IR PDFs. Not one
   is a listing or index page. The 2026-07-30 allowlist sets `discovery: prohibited`, and each
   source's `discovery_path` says "operator-supplied ... URLs only", with `hose` adding
   "no pagination, no search, no link following". An agent constructing a search URL from site
   structure would be supplying the operator's authority to itself.
2. **A decision on whether a listing page is admissible at all.** The registry declares ten
   *document* types and no listing/index/search type, so `admit()` refuses `listing_page` with
   `document_type_not_declared_for_source`. Labelling a listing page `corporate_action_notice`
   to get it past the gate is defeating admission, not passing it. The narrower resolution —
   naming a *notice detail* URL, the shape `vsd.vn/en/ad/177392` already has authority for —
   needs no new type and no new capability.
3. **A listing-page parser, if step 2 goes the listing route.**
   `official_document_discovery.discover()` is a **validator, not a parser**: it checks
   caller-supplied `links` dicts, and there is no HTML link extractor anywhere in first-party
   code. Extracting candidates from a retained page today would mean a human or an agent
   hand-reading HTML and hand-assigning document classes — which is inferred identity, the
   thing the closed-world contract exists to prevent.

## Target pipeline

```
HOSE / HNX / VSDC / issuer IR
  → scheduled bounded crawl (allowlisted hosts, robots-respecting, rate-limited)
  → download + SHA-256, immutable blob retention
  → document classification (notice / resolution / registration-date announcement)
  → event extraction (typed, per document class)
  → cross-document linking (many documents, one event)
  → execution-status confirmation
  → immutable corporate-action event ledger
  → adjustment factors → close_official_event_adjusted series
```

### Why a board resolution alone is not enough

A resolution states an intention: a planned ratio, a method (cash or stock), and an
authorisation to fix the dates later. It is not evidence the event happened. A trustworthy
adjusted series needs the whole chain — approval → issuer disclosure → exchange notice →
VSDC record date → confirmed ex-date and ratio → final execution status. The ledger must
therefore link documents to one event and carry an execution status, not just an event row.

The official sources do carry the needed fields: HNX's per-security pages expose ex-date,
record date, exercise date and event type; VSDC publishes last-registration dates with the
entitlement and execution method; HOSE issues ex-right and dividend notices.

### Event types that must be supported from day one

Cash dividend · stock dividend · bonus issue · rights issue · split · reverse split · capital
return · other securities distribution · cancellation/amendment of a previously announced
event.

**Collecting only cash dividends leaves the price basis wrong**, because a bonus issue or a
rights issue moves the price without any cash ever being paid. A ledger that is complete for
cash and silent on non-cash events produces an adjusted series that is confidently wrong,
which is worse than an unadjusted one.

### Ledger record shape

```
event_id · ticker · event_type
approval_date · ex_date · record_date · payment_or_execution_date
cash_amount · stock_ratio · rights_ratio · subscription_price
official_source_url · document_sha256 · execution_status · superseded_by
```

`superseded_by` and `execution_status` are what make the ledger immutable rather than
mutable: an amended or cancelled event is superseded by a new record, never edited in place.

### Two published series, never one

```
close_raw
close_official_event_adjusted
```

published alongside

```
adjustment_authority     = official_corporate_action_ledger
adjustment_policy_version = 1.0.0
```

Anything derived from adjusted prices stays fail-closed until the ledger covers the period
being adjusted. Partial ledger coverage must degrade to `unavailable` for the affected
window, never to "adjusted with what we happen to have".

## Constraints this pillar inherits

- **Fail-closed by default.** An event that cannot be confirmed does not enter the ledger.
- **`evidence_promotion.py` remains the only evidence write boundary.** The crawler proposes;
  promotion is a separate, audited step.
- **Bounded and allowlisted.** Crawling official sites is an outward-facing action. The host
  allowlist, request rate and retention policy are owner decisions, recorded before the first
  scheduled run, extending `operations-review/official-document-acquisition-allowlist-20260730.json`.
- **Immutable blobs.** Every document is retained by content hash; extraction is re-runnable
  against the retained bytes without re-fetching.
- **Determinism.** Same retained documents → same ledger, same factors, same adjusted series.

## Suggested milestone sequence

1. **B1 — crawl contract and allowlist.** Owner-approved host allowlist, rate limits,
   retention and robots policy. No code.
2. **B2 — bounded scheduled crawler for one source** (HNX per-security event pages are the
   most structured), writing only immutable blobs plus a discovery ledger. No extraction.
3. **B3 — document classification and typed event extraction** over the retained blobs,
   proposing events without promoting them.
4. **B4 — cross-document linking and execution status**, producing the immutable event ledger.
5. **B5 — historical qualification**: replay the ledger against known historical events for a
   validation set of tickers; the exit gate is agreement, not coverage.
6. **B6 — adjustment factors and the dual price series**, then re-open return, risk and
   backtest, which are currently `0 tickers ready` market-wide.

B1–B4 are independent of the market-wide financial pipeline (pillar A) and can proceed in
parallel; only B6 unblocks the current-market tier that pillar A's enterprise-value layer is
waiting on.
