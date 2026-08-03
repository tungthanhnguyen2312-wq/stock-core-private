# P1E — market-wide canonical financial facts + official corporate-action foundation

Milestone operations review. Date: **2026-08-03**. Base commit: `1e691ad`.
Runtime root: `C:\Projects\StockLookup\dashboard-runtime`.

This is the detailed evidence record for the milestone. The chat summary is deliberately short;
everything reproducible lives here.

---

## 1. Production state — unchanged

SHA-256 recorded before any work and re-verified after everything below.
`baseline_hashes.txt` in this directory holds the recorded values; `sha256sum -c` re-verified
all seven after the milestone.

| artifact | state |
| --- | --- |
| `vn_stock.db` | **unchanged** |
| `analysis_bundle.json` | **unchanged** |
| `bundle_manifest.json` | **unchanged** |
| `focus_extract.json` | **unchanged** |
| `statement_taxonomy_sidecar.json` | **unchanged** |
| `screen_snapshot.csv` | **unchanged** |
| `data/official-evidence/manifest.json` | **unchanged** |

Nothing was published or deployed. `config/ticker_entity_profiles.csv` was not modified;
`CANONICAL_PROFILE_BACKFILL_AUTHORIZED` remains `NO`. No write to `data/official-evidence/`
occurred — `evidence_promotion.py` remains the only evidence write boundary.

All new artifacts are generated runtime data under
`dashboard-runtime/data/canonical-financial-facts/`,
`dashboard-runtime/data/official-corporate-actions/` and two new files under
`dashboard-runtime/data/market-wide-financials/`.

---

## 2. Findings that changed the design

These were discovered against the retained data and are the reason several parts of this
milestone do not look like the contract predicted.

### 2.1 Provider is not dialect

`docs/market_wide_financial_normalization_contract.md` describes the vocabulary split as two
providers with two vocabularies. The retained bytes disagree: **HPG's income statement carries
`source = KBS` and the full VCI vocabulary** (`of_which_interest_expense`,
`deduction_from_revenue`, `net_profit`). A mapping keyed on the `source` column drops every
metric on that payload — verified before the mapper was written.

Candidate matching therefore keys on the raw item id, which is what actually discriminates,
and `detect_dialect()` reports the dialect a payload's *vocabulary* evidences so the coverage
report can still break every metric down by dialect.

### 2.2 Cash-flow period labels are not trustworthy

HPG's cash-flow payload column labelled `2025-Q2` carries
`cash_and_cash_equivalents_at_the_end_of_the_period = 11,455,231,039,000`, which matches the
**2026-Q1** balance sheet (`11,455,231,038,505`), not 2025-Q2.

End-of-period cash is the only cross-check the retained payloads offer between a balance sheet
and a cash-flow statement, so it is used as a **period-attribution gate**, not merely a scale
check:

| cross-statement cash | effect on cash-flow facts |
| --- | --- |
| `coherent` / `coherent_thousand_rounded` | usable |
| `divergent` | `conflicted` — `cash_flow_period_attribution_unverified` |
| `unknown` (line absent on either side) | capped at `partial` |

Over a 250-ticker sample the check holds exactly for 347 ticker-periods, within
thousand-rounding for 17, and **diverges for 314**. Without this gate a depreciation figure
from one quarter would silently be added to a profit figure from another inside EBITDA.

### 2.3 The provider tier caps retention at 8 periods

The reconciliation probe surfaced the provider's own banner:

> Community edition: Financial statements limited to 8 periods.

That explains a structural property of the store that was previously unexplained: **every
ticker has at most 8 quarterly periods and there are no annual periods at all** (4,194 of
4,195 payloads are `*_quarter`). Annual figures are therefore not retained and cannot be
derived without a cumulative-basis resolution that the payloads mostly do not support.

### 2.4 `scrape_meta.csv` conflates "source is empty" with "the call broke"

All 131 active-universe tickers with no retained payload are recorded `status = empty`,
`source = NaN`. That reads as "the provider confirmed it has no data". It does not mean that:
`bctc_sync.call_api` returns `None` — which `fetch_report` turns into `EMPTY_DATA` — for **any**
exception that is neither a rate-limit nor a recognised network error:

```python
else:
    print(f"   [Lỗi Hệ Thống] {label}: ...")
    return None
```

A schema change, a parse error and a genuinely empty source are indistinguishable in the
recorded state. `missing_payload_reconciliation.py` separates them.

---

## 3. Workstream A — canonical financial facts

New modules: `canonical_financial_resolvers.py`, `canonical_financial_facts.py`,
`canonical_fact_store.py`. Tool: `tools/ingest_canonical_financial_facts.py`.

### 3.1 What each resolver can actually demonstrate

| dimension | resolved from | outcome |
| --- | --- | --- |
| `statement_scope` | non-zero minority interest | `consolidated` on positive evidence only; zero/absent never grants `separate` |
| `sign_convention` | the gross-profit identity | `expenses_positive` / `expenses_negative` / `unknown` |
| balance identity | `total_assets = liabilities + owners_equity` | 848/850 hold in sample; violations conflict every balance-sheet metric |
| cross-statement scale | balance-sheet cash vs cash-flow end cash | see 2.2 |
| `cumulative_state` | beginning-of-period cash across quarters of one year | frequently and correctly `unknown` |
| `currency`, `scale` | **nothing in the payloads** | `unknown` unless an official citation agrees |

The retained payloads carry no currency column, no unit header and no anchor fixing the
absolute unit. Vietnamese issuers do file in VND under VAS — that is a convention, and the
contract forbids promoting a convention to a qualified fact. Hence `provider_reported` is the
honest market-wide ceiling.

### 3.2 The one route to `qualified`, and it works

An annual official citation and a Q4 provider value name the same instant for a **stock**
metric (a balance sheet dated 31 Dec 2024 is both FY2024 year-end and 2024-Q4 end); the alias
is emitted only for balance-sheet metrics, never for flows.

HPG's provider-reported 2024-Q4 `undistributed_earnings` is **49,599,124,109,203**, matching
the audited FY2024 citation **digit for digit**. VNM's is **3,471,224,745,772**, likewise.
Those two facts carry `currency = VND`, `scale = units`,
`unit_authority = official_citation_agreement`. A disagreement would have produced
`conflicted`, not an override — tested.

### 3.3 Market-wide result

```
tickers                 1,493
canonical facts       195,552
qualified                   2
provider_reported      93,749
partial                 5,004
conflicted             12,501
unavailable            84,296
unresolved metric queue 101,801   (per metric, never per ticker)
conflict queue          12,619
```

Store: `dashboard-runtime/data/canonical-financial-facts/`. Shards are gzip `mtime=0` over
canonical JSONL, byte-identical across rebuilds.

### 3.4 A staleness trap this milestone walked into, on purpose worth recording

After fixing the cross-statement candidate lookup, a re-run reported **`rebuilt: 0,
unchanged: 1493`** — the store kept serving facts built by code that no longer existed. The
`inputs_fingerprint` covers `MAPPER_VERSION`, and the mapper had changed without the version
moving. The rule is therefore operational, not decorative: **bump `MAPPER_VERSION` on any
mapping change**. The store was force-rebuilt for this milestone; `unavailable` fell from
86,724 to 84,296 once the fix actually took effect.

---

## 4. Workstream B — market-wide calculation readiness

New module `market_wide_calculation_readiness.py`, tool
`tools/report_market_wide_readiness.py`, artifact
`data/canonical-financial-facts/calculation_readiness_report.json`.

Measured over 1,492 tickers after the §3.4 rebuild:

```
ebitda                 ready = 231    not_applicable = 83
roe                    ready = 1,321
market_capitalisation  ready = 0
enterprise_value       ready = 0      balance-sheet components ready = 1,338
ev_ebitda              ready = 0      not_applicable = 83
pe                     ready = 0
pb                     ready = 0
```

See `data/canonical-financial-facts/calculation_readiness_report.json` for the full blocker
histogram.

**EBITDA moves from 2 to 231 tickers.** `docs/STATE.md` recorded EBITDA as computable for 2
tickers market-wide. The reconciliation contract is
`profit_before_tax + interest_expense + depreciation_and_amortization`, and every result
carries the three source `fact_id`s, each term's status, and the identity itself.

It is 231 and not ~1,000 because of a real constraint, not a mapping gap: the cash-flow
payloads carry very few periods (mode 2 per ticker), and where a cash-flow period cannot be
attributed against the balance sheet (§2.2) its facts are refused. That is the correct number
under the evidence available.

**Market capitalisation is blocked by two independent causes, reported separately**: no
retained provider line carries a share count (`common_shares` is a paid-in capital amount in
currency; converting it needs an assumed par value), and the price basis is unknown and
unverified universe-wide. EV, EV/EBITDA, P/E and P/B all inherit that block. The EV
balance-sheet half — interest-bearing debt and cash — is ready for **1,338** tickers, reported
because it is what becomes immediately computable once pillar B qualifies a price basis, and
labelled so it cannot be read as EV being available.

**ROE is the one ratio needing no price**, and it is reported as a single-period ratio,
explicitly never annualised: the payloads are quarterly and their cumulative basis is
frequently `unknown`, so multiplying by four would manufacture a TTM the evidence does not
support.

Nothing here produces a score or a ranking, and `is_actionable` is untouched.

---

## 5. Workstream C — missing-payload reconciliation

New module `missing_payload_reconciliation.py`, tool `tools/reconcile_missing_payloads.py`.
Artifacts: `missing_payload_reconciliation.json`, `missing_payload_report.json`.

Bounded (`--max-tickers`, fixed inter-request delay, at most 2 attempts per source),
resumable (state written after every ticker), and it **never writes a payload** — acting on
`payload_available` is a separate, explicit run of the authorized `bctc_sync.py`.

All 131 tickers are UPCOM listed equities (`instrument_type = STOCK`), so none is resolved as
`unsupported_entity`. Probing through the same authorized `vnstock` `Finance` path used by
`bctc_sync.py` classified every ticker probed so far as **`source_empty_confirmed`** — the
provider genuinely carries no statements for them, across both KBS and VCI, for all three
statement families. No `payload_available`, no `provider_error`, no `retrieval_failure`.

That is a definitive answer for the tickers covered: the gap is in the source, and no
acquisition work will close it. See `missing_payload_report.json` for the per-ticker record
and the count actually reached.

---

## 6. Workstream D — official corporate-action foundation

New: `config/official_source_registry.json`, `official_source_registry.py`,
`official_document_store.py`, `corporate_action_events.py`,
`official_corporate_action_ledger.py`, `tools/run_official_corporate_action_slice.py`.

### 6.1 Source registry (B1) — declared, not activated

HOSE, HNX, VSDC and qualified issuer IR domains, each with allowed hosts, document types,
discovery path, request rate, timeout, bounded retry, robots/terms considerations, retrieval
timestamp, content hash, retention policy, parser version and failure classification.

`approval_state = AWAITING_OWNER_APPROVAL` and **every source is `declared`, not `approved`**.
`admit()` refuses a declared source, so the reviewable JSON is what actually gates the network
rather than a comment asking a future agent to be careful. An agent may not flip `activation`
to `approved`; that is an owner decision recorded in the registry and in `docs/DECISIONS.md`.

Host matching is exact after lower-casing and port-stripping — not suffix matching, because
`evil-hnx.vn` passes a naive suffix test. EODHD is recorded in the registry itself as
`REJECTED_BY_OWNER` and excluded.

### 6.2 Immutable document store

Content-addressed by SHA-256, re-hashed at adoption time (a hash recorded in another manifest
is metadata about a past retrieval, not evidence about the bytes on disk now). Writing
different bytes to an existing content path raises `HashConflict`; `read_document` re-verifies
before returning; a correction is a **new record** with `supersedes_document_id` and the
superseded record keeps its identity and content forever. There is no delete function, and a
test asserts there is none.

### 6.3 Bounded vertical slice — HPG, offline

Two independent retained official documents describing one HPG stock dividend, reused from the
2026-07-30 owner-approved allowlist with **no network request**:

| document | class | sha256 | parser |
| --- | --- | --- | --- |
| issuer change-of-voting-shares notice, 2026-06-04 | `corporate_action_notice` (PDF) | `8bbae21f…` | direct text |
| issuer recital of HOSE notice 1475/TB-SGDHCM, 2026-07-07 | `listing_change_notice` (HTML) | `cb41c96e…` | direct text |

Result:

```
documents adopted        2   (immutable, verify ok=True checked=2)
observations extracted   2
ledger entries           1   (2 repeat observations deduplicated)
unlinked observations    1   (the scan, with a stated reason)
qualified events         1
replay fingerprint       stable across two runs (MATCH)
```

The ledger entry: `HPG stock_dividend`, `lifecycle = executed`,
`shares_issued = 767,498,665`, `shares_after = 8,442,964,520`,
`stock_ratio = 0.0999937567`, five field-level citations, both source hashes,
`qualification_state = qualified`.

**Adjustment factor: `not_ready`, blocked by `missing_explicit_official_ex_date`.** Neither
document states an ex-date. `docs/DECISIONS.md` already fixes that a record date never
substitutes for one, and this extends it to payment, listing and trading dates. This is the
fail-closed case the milestone asked the slice to demonstrate, and it is the correct outcome.

**The scanned issuer notice is refused, correctly.** Its text extraction corrupts the
post-change count to `8.M2.964.520`, which tokenises as `2.964.520` — a value that parses
cleanly and lies inside any plausible share range, so no bounds check would catch it. The
extractor requires the form's own English column headers in order (they are scrambled by the
extractor) and cross-agreement between two labelled rows, so it emits **no** share count from
that document rather than the charter-capital figure `76,764,658` an earlier cue-based pass
produced. Both wrong values are asserted against in the test suite.

Amendment/supersession, cross-document arithmetic corroboration, document-disagreement
conflicts, and factor derivation with an explicit ex-date are covered by unit tests rather
than by the slice, because no retained document provides those cases.

---

## 7. Workstream E — integration boundary

`canonical_financial_bundle_section.py` plus one new **disabled-by-default** flag
`--include-canonical-financial-facts` on `export_ai_bundle.py`, following the Phase 5A/6A
opt-in precedent exactly.

* Additive only: the single new key is `tickers[<T>].canonical_financial_facts`. No
  pre-existing field is read, written or reordered.
* A metric crosses only with status, provenance, period, scope, unit, basis and limitations.
  **`conflicted` and `unavailable` facts cross as status and reason with `value: null` and
  `value_withheld: true`** — a consumer that sees a number will eventually use it.
* Raw observations never cross; only `source_observation_ids` pointers do.
* No ranking, no score, no `is_actionable` change.

### Deterministic double-build and exact artifact diff

Both runs into isolated shadow directories via `--output-dir`; production artifacts were never
written.

| comparison | result |
| --- | --- |
| shadow build A vs shadow build B (new code, flag off) | **IDENTICAL** on content |
| production-equivalent shadow (new code, flag off, production ticker set and flags) vs the live production artifacts | **IDENTICAL** on content |

The only differing leaves between two runs are the documented clock fields — `generated_at`,
`reference_at`, `valuation_date` — and the artifact hashes that necessarily move with them.
`compare_bundles.py` in this directory performs the normalised comparison and is re-runnable.

The second row is the important one: the Producer carrying this milestone's changes, with the
new flag off, reproduces the shipped bundle exactly. The change is provably additive.

With the flag **on** (`HPG,VNM,VCB`), the section is present and behaves: HPG 2026-Q1 shows
1 qualified / 65 provider_reported / 14 conflicted / 64 unavailable with values withheld on the
last two, and VCB — a bank — shows `ebitda: not_applicable` while `roe` is `ready`.

---

## 8. Validation

```
tests/test_canonical_financial_facts.py            52 passed
tests/test_official_corporate_action_pillar.py     51 passed
```

Covering: resolver evidence rules and every `unknown` path; both cash-flow dialects mapping to
the same canonical metrics; dialect detection independent of the provider column; label match
never upgrading a status; official-citation agreement and disagreement; restated period-column
conflicts; balance-identity violations; the cash-flow period-attribution gate and its
`partial` cap; concept substitution; derived-metric blocking; gross-vs-net revenue
reconciliation; malformed and empty input; financial-institution applicability;
shard determinism and double-build byte-identity; the mapper-version fingerprint guard;
per-metric (never per-ticker) queues; registry admission including exact-host matching, rate
limits and the unapproved-source refusal; document-store immutability, hash-conflict and
source-hash-mismatch detection, and supersession-without-edit; OCR damage refusal; ex-date
never substituted; lifecycle ceilings; ledger deduplication, cross-document linking,
disagreement conflicts, cancellation and amendment supersession, order-independent replay;
factor fail-closed and factor derivation; reconciliation classification of all five outcomes,
bounded runs, terminal-state skipping and interrupted-run resume.

Also run: `git diff --check` (clean), `python -m compileall` on every new module (clean),
document-store `verify()` (ok), fact-store `--check` re-derivation.

---

## 9. What this milestone does **not** claim

* No price basis is qualified. Price and volume basis remain `unknown / verified: false`.
* No market capitalisation, enterprise value, EV/EBITDA, P/E or P/B is available for any
  ticker.
* No adjusted price series, adjusted return, beta, correlation, backtest, volatility, risk
  ranking or position sizing is unlocked. The readiness artifact lists these explicitly under
  `still_blocked_by_price_basis`.
* No crawl was performed and no source was activated. Pillar B step B1 is delivered as a
  reviewable artifact awaiting an owner decision.
* `provider_reported` is not an evidence-qualified value. Only 2 facts market-wide are
  `qualified`, and both come from an official citation.
* The issuer-entity-type blocker is unchanged: it still needs an authoritative issuer-type
  source, which generated taxonomy cannot supply by construction.

## 10. Exact next blocker

**Owner approval of `config/official_source_registry.json` (pillar B step B1).** Every source
is `declared`; `admit()` refuses all of them; no document can be acquired from HOSE, HNX or
VSDC until `activation` is set to `approved` by the owner. That gate blocks B2–B6, and B6 is
the only remaining route to a qualified price basis now that EODHD is closed — which in turn
is what unblocks market capitalisation, and therefore EV, EV/EBITDA, P/E and P/B, all currently
at 0 tickers.
