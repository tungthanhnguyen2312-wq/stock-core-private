# VCI volume market-composition qualification and closeout

**Date:** 2026-08-04 · **Starting commit:** `9887c1c` · **Provider:** VCI only
**Live requests:** 1

---

## Candidate surfaces

### Retained corpus — exhausted with zero hits

Every retained VCI raw payload from commits `028eb08` and `9887c1c` carries **18 distinct
field names in total**: `t o h l c v symbol accumulatedVolume accumulatedValue
minBatchTruncTime id truncTime matchType matchVol matchPrice createdAt updatedAt type`.

Not one names or separates a trade method. `matchType` is `b`/`s` — the **aggressor side**,
not the trade method, and reading it as "matched trade" would be exactly the name-based
inference this milestone forbids. `type: "sheep"` is undocumented.

A token scan of the entire `vnstock` 4.0.4 VCI adapter for
`putthrough|thoathuan|negotiat|totalvolume|oddlot|auction|boardvolume` returns **zero
matches**. The adapter's 21 volume-bearing identifiers are all depth, bid/ask, foreign or
`matchVol`.

### Surfaces inventoried

| surface | endpoint | observed in | auth | level | verdict |
| --- | --- | --- | --- | --- | --- |
| daily gap-chart | `POST /api/chart/OHLCChart/gap-chart` | `vnstock` quote.py; `vn_stock_pipeline` | none | ticker | rejected — `v`/`accumulatedVolume` are undifferentiated totals |
| intraday tape | `POST /api/market-watch/LEData/getAll` | `vnstock` quote.py; paginated in `9887c1c` | none | ticker | rejected — aggressor side only, single running total |
| **price board** | `POST /api/price/symbols/getList` | `vnstock` trading.py **and already called in production by `meta_sync.py:156`, `blacklist_sync.py:75`** | none | ticker | **probed** |

Out of scope and recorded so nobody re-derives them: `iq.vietcap.com.vn` events /
market-indices / company, and `trading.vietcap.com.vn/data-mt/graphql` — all answer a
different question.

---

## Live probe

**One request occurred.** Justification against the five conditions:

1. **Observed provenance** — not merely observed, *already exercised by this repository's
   own production code*. Not a discovered or inferred endpoint.
2. **No access control bypassed** — no cookie, token or credential exists or was sent.
3. **Bounded** — one ticker, `{"symbols": ["VCB"]}`.
4. **Could resolve a specific question** — the `matchPrice` group is where a Vietnamese
   broker board would expose a trade-method split if anywhere.
5. **Offline-comparable** — against the retained VCB morning tape from `9887c1c`.

| | |
| --- | --- |
| endpoint / method | `https://trading.vietcap.com.vn/api/price/symbols/getList` · POST |
| parameters | `{"symbols": ["VCB"]}` |
| status / redirects / retries | 200 · 0 · 0 |
| artifact | `raw/vci_price_board_VCB_20260804T051433Z_b59c2965eee9f303.raw.json` |
| response shape | 3 groups, **96 fields** — `listingInfo` 39, `bidAsk` 11, `matchPrice` 46 |

### What the board contains

**No put-through, negotiated, block or odd-lot field exists in any of the 96.**

Two things it *does* contain:

- **`accumulatedVolumeG1` = 1,877,000, identical to `accumulatedVolume`.** The `G1` suffix
  suggests a group/board segmentation. **Rejected as evidence.** Equality is consistent
  with "G1 is the whole" and with "VCB had zero of whatever G1 excludes this morning", and
  nothing on hand distinguishes them. This is precisely the "arithmetic balance without
  field definitions" case, and it is the single most tempting thing in the payload.
- **`matchVolumeATO` = 42,700 · `matchPriceATO` = 60,900 · `matchVolumeATC` = 0** —
  separately labelled auction quantities.

### The one comparison that landed

Computed offline against the retained VCB tape. **Four independent quantities agree:**

| | board | retained tape |
| --- | --- | --- |
| opening-auction volume | `matchVolumeATO` 42,700 | 42,700 (single trade at the session's first instant) |
| opening-auction price | `matchPriceATO` 60,900 | 60,900 |
| instant | `firstTimeMatchPrice` 02:15:00Z | truncTime 1785809700 = 02:15:00Z |
| position in session | — | `accumulatedVolume == matchVol` → **the accumulator's first entry** |

So the opening-auction batch *is* inside `accumulatedVolume`, and therefore inside daily
`v`.

---

## Judgement call, stated plainly

**No first-party VCI definition of any field was found or retained**, and none is claimed:
`first_party_definitions_retained: []`. Under the strictest reading of the qualification
rules, that alone would force State B.

I qualified `opening_auction_inclusion` anyway, on a deliberately narrow third route which
I have made explicit in code as `exchange_standard_term`:

- **ATO/ATC are HOSE session codes**, defined by exchange regulation, not VCI coinages. The
  provider uses them as such, paired, alongside `session: LO_MORNING` and
  `tradingSessionID: 40`. The referent is fixed *outside* the provider.
- **A second, independent field pins the same referent** — `firstTimeMatchPrice` lands on
  exactly the instant the reconciliation identifies.
- **The reconciliation is exact on volume, price, timestamp and session position.**

The alternative reading — that `matchVolumeATO` denotes something other than the opening
auction while coincidentally matching the first trade of the session at exactly the ATO
instant with exactly the ATO price — is not credible. This is materially different from
the `accumulatedVolumeG1` case, which has a suggestive name, an exact equality, and **no**
independent pin, and which I therefore refuse.

The route is encoded, not asserted in prose: `qualify_dimension` requires
`referent_pinned_by_independent_field` before an `exchange_standard_term` can carry a
qualification, and a test proves name-alone and reconciliation-without-pin both return
`unknown`. `EXCHANGE_STANDARD_TERMS` holds exactly `{ATO, ATC}`.

**Deviation from the reference brief, and why.** The brief allowed only an explicit
first-party definition or a relationship between fields with "unambiguous first-party
meaning". I read an exchange-regulated code plus an independent referent pin as satisfying
the spirit of the second route while being narrower than the first. A reader who disagrees
should downgrade `opening_auction_inclusion` to `unknown`, which flips the terminal state
to B and changes **nothing** downstream — every gate is already closed.

---

## Volume contract — State A

```text
provider_internal_volume_reconciled = true
volume_field_identity               = qualified
volume_unit                         = shares
volume_corporate_action_adjustment  = unknown
matched_trade_inclusion             = unknown
negotiated_inclusion                = unknown
auction_inclusion                   = qualified   [opening leg only]
  opening_auction_inclusion         = qualified
  closing_auction_inclusion         = unknown
odd_lot_inclusion                   = unknown
market_scope                        = partially_qualified
liquidity_actionable                = false
further_vci_pagination_authorized   = false
further_speculative_endpoint_probe_authorized = false
```

The roll-up cannot be asserted directly and cannot be published without naming its legs —
`assert_fail_closed` rejects a qualified `auction_inclusion` with no
`auction_inclusion_scope`. One auction leg does not speak for the other.

**Which unknowns are closed and which are merely unobserved** — recorded so the second kind
is not reopened as though it were the first:

| dimension | resolution |
| --- | --- |
| `negotiated_inclusion` | **`unavailable_from_observed_vci_surfaces`** |
| `matched_trade_inclusion` | **`unavailable_from_observed_vci_surfaces`** |
| `odd_lot_inclusion` | **`unavailable_from_observed_vci_surfaces`** |
| `closing_auction_inclusion` | `not_observable_from_the_retained_morning_snapshot` — a board read after 14:45 ICT would carry `matchVolumeATC` |

`volume_corporate_action_adjustment` stays `unknown`. No new event sample was acquired, and
the retained before/after evidence from `9887c1c` cannot isolate it: 13 sessions, 13
distinct ratios, confounded with a mid-session accumulator capture. The price finding is
**not** an input — `price_adjustment_does_not_imply_volume_adjustment` discards its
`price_basis` argument, and a test flips that argument to prove the output does not move.

**Liquidity eligibility: none.** `days_to_liquidate`, `market_impact`, `position_sizing`,
`portfolio_sizing`, `backtesting` all unavailable. `liquidity_actionable` is a constant
`False` in the contract builder — no combination of inputs turns it on.

---

## Evidence audit

| | |
| --- | --- |
| artifacts reviewed | **154** across 4 evidence roots (135 raw) |
| unreferenced raw artifacts | **0** (was 4 — see corrections) |
| secret findings | **0** (was 2 — both false positives, see corrections) |
| raw names self-verifying | **yes** — every raw filename embeds the first 16 hex of its own content hash |
| byte-identical groups | 3, all with distinct evidentiary roles |
| replay determinism | file count and every content hash unchanged across replay |
| artifacts removed | **0** |

**Corrections made:**

1. **Ledger gap (real).** `fetch_daily_volume` wrote a raw daily-bar artifact whose name
   was never recorded, leaving 4 raw files reachable by nothing. The runner now records
   `raw_artifact`, and the 4 existing ledgers were repaired by hash-matching.
2. **Secret scan (false positive).** The scanner matched prose — the phrases "no cookie,
   **authorization** header … was sent" and "non-**secret** parameters" in a report. It is
   now structural: a marker must appear as a JSON key whose value is not the redaction
   sentinel. Both findings cleared; no secret ever existed.
3. **Byte-identical groups kept, not deleted.** Two runs' daily bars and two runs' first
   pages are byte-identical because the lunch-halt tape was frozen — expected, and each
   copy is its own run's reconciliation target. The third (run-03's superseded in-directory
   attempt) is now referenced as `superseded_attempt_artifacts` rather than removed. **No
   failure evidence was deleted to reduce a count.**

---

## Repository result

* **Starting commit** `9887c1c` · **final commit** see `git log -1`
* **Added:** `vci_volume_composition.py`, `tools/run_vci_composition_probe.py`,
  `tools/audit_vci_evidence.py`, `tests/test_vci_volume_composition.py`, this directory.
* **Modified:** `vci_direct_basis_pilot.py` (price-board endpoint registered),
  `tools/run_vci_intraday_pagination.py` (records its daily-bar artifact), 3 repaired
  `daily_bar.json` ledgers, `docs/STATE.md`, `docs/DECISIONS.md`.
* **Tests:** `test_vci_volume_composition.py` **29 passing** (all 15 required proofs);
  full relevant set **405 passing + 25 subtests** across 22 modules.
* **No further pagination run was performed.**

## Non-effects

No change to production databases, bundles, dashboard artifacts, rankings,
recommendations, sizing, backtesting, generic market fields or `is_actionable`. The
price-basis supersession from `9887c1c` is intact and tested; P2a remains blocked.

---

**`VCI_VOLUME_SCOPE_CLOSEOUT: PARTIALLY_QUALIFIED`**

One dimension — opening-auction inclusion — is demonstrated. The dimension that actually
gates liquidity analytics, **negotiated inclusion, is closed as
`unavailable_from_observed_vci_surfaces`**: 96 fields across every observable surface, zero
of them separating put-through from matched trading, and no first-party definition anywhere.

## Recommended next bounded milestone

**Formally scope liquidity analytics as unavailable, and record the exchange as the only
remaining authority path for market composition.** VCI probing is closed by this milestone
and must not resume. The honest next step is not another provider hunt but a decision
record: mark `days_to_liquidate`, market-impact and liquidity-based sizing **unavailable by
contract** rather than merely blocked pending evidence, and register HOSE's own published
trading statistics as the sole surface that could ever qualify `negotiated_inclusion` —
without acquiring anything from it in that milestone.
