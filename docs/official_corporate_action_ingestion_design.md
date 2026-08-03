# Official corporate-action ingestion and price-adjustment engine — design

Status: **design only, 2026-08-03. Nothing in this document is implemented.**
It is recorded now so the pillar is a named roadmap item with a written contract rather
than an intention, and so the next milestone starts from a decision rather than a debate.

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
| `official_document_discovery.py` | closed-world discovery: caller supplies a finite set of qualified listing/detail pages; never searches, crawls or paginates |
| `official_document_acquisition.py` | bounded acquisition against an allowlist, with hashing |
| `official_document_retrieval.py`, `official_document_ocr_handoff.py` | retrieval and OCR handoff |
| `corporate_action_evidence_registry.py`, `evidence_registry.py`, `evidence_replay.py` | evidence registry with replay parity (`docs/adr/ADR-002`) |
| `corporate_action_ledger.py` | ledger MVP over qualified cash-dividend / stock-dividend / bonus events, deterministic ordering, immutable lineage, emits **0** adjustment factors by design |
| `evidence_promotion.py` | the only approved evidence write boundary (`docs/DECISIONS.md`) |
| `corporate_action_factors.py`, `point_in_time_adjusted_prices.py` | factor and adjusted-price computation, currently fed nothing |

The gap is not the ledger and not the adjustment maths. The gap is a **production ingestion
path**: today a human supplies each URL. Pillar B is the step from closed-world discovery to
a periodic, bounded crawler with an immutable event ledger behind it.

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
