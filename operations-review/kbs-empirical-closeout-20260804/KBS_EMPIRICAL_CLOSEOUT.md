# KBS empirical-basis closeout and prospective mutability protocol

**Date:** 2026-08-04 · **Starting commit:** `4a07141` · **Provider:** KBS
**Network requests issued: 0.** This milestone is entirely offline. Every number below is
re-derived from the six raw payloads retained at `4a07141`.

---

## 1. The correction

The P0-Z closing report recommended re-requesting the HPG 2026-05-18…06-02 window "after
enough elapsed time" to settle whether KBS rewrites history at a corporate action.

That is wrong, and the arithmetic is not close:

| | |
|---|---|
| HPG share-issue ex-right date | **2026-05-25** |
| Earliest retained KBS payload for that window | **2026-08-04** |
| Gap | 71 days, entirely on the wrong side |

Whatever the provider did to those rows at the event, it had already done before the first
observation existed. A second request — tomorrow, or in a year — produces another
post-event snapshot. Two post-event snapshots measure **post-event stability**. Elapsed
time is not the missing ingredient; a snapshot taken *before* an event is.

The recommendation is retained as `kbs_mutability_protocol.SUPERSEDED_RECOMMENDATION` with
`would_have_settled: []` and an explicit `must_not_be_claimed_to_settle` list.

---

## 2. Unit anchor (Part A)

### What the geometry earns

`implied_average_price = (va × va_scale) / (v × v_scale)` depends only on the **quotient**
of the two scales. `(1, 1)` and `(1000, 1000)` predict the identical implied price for every
session that will ever exist.

- Quotient **1.0**, from 36 discriminating rows, 3 tickers, 3 price levels (~21k / ~55k /
  ~58k VND). All 14 competing quotients rejected outright.
- Mean |implied − range midpoint| = 83.9 VND. Per ticker: HPG 15/15, VNM 15/15, VCB 6/6.
- 2 of 38 eligible rows are explained by no candidate scale; retained as contradictions.

`unit_scale_ratio = 1` is therefore established independently of any anchor. Everything
below concerns only the **absolute** scale.

### Anchor 1 — numeric identity (primary, selected)

`absolute_scale_anchor = numeric_identity_with_an_independently_unit_qualified_series`

| Property | Value |
|---|---|
| Reference | `dashboard-runtime/vn_stock.db:ohlcv[source=VCI]` volumes, read-only, no VCI request issued |
| Reference unit | `shares`, from `vci_volume_composition.active_contract()` |
| How that unit was established | VCI's own per-trade tape: accumulated-volume deltas equal per-trade quantities 99/99, and value deltas equal quantity × price at one scale 99/99 (commit `63ecc48`). Not a plausibility bound. |
| Sessions compared | 66 |
| **Sessions exactly equal** | **34** — HPG 9, VCB 15, VNM 10 |
| Tickers with exact equality | all three |
| Implied `volume_scale` | 1 |
| Authority | `empirically_deduced`, ceiling set by the reference's own tier |
| Transfers | **magnitude only** |
| Does *not* transfer | market composition, adjustment behaviour, historical mutability, source authority |

The argument is arithmetic, not deference. If KBS returns 53,245,200 and VCI returns
53,245,200 for the same ticker-session, and VCI's figure counts individual shares, a
thousand-fold reading of KBS would require the true traded quantity to be both X and 1000X
on every one of 34 matched sessions.

This is **not** the cross-provider authority upgrade the ladder forbids. That rule is about
*semantics* — agreement cannot establish what a field means. Here the borrowed quantity is
magnitude, and `assert_identity_anchor_is_magnitude_only` raises on an anchor carrying
`market_scope`, `composition` or `source_authority`.

### Anchor 2 — issued-share-count falsifier (corroborating)

| Property | Value |
|---|---|
| Observation | `shares_outstanding = 8,442,964,520` |
| Ticker | HPG |
| Observation date | 2026-07-30 16:12 |
| Source | `dashboard-runtime/vn_stock.db:metadata.shares_outstanding`, populated from VCI `Company().overview().issue_share` |
| Qualification tier | `observed_only` — **not official**; P1J.1 measured `qualified_official = 0` |
| Calculation | `(1000,1000)` ⇒ 27,485,500 × 1000 = **27,485,500,000** shares traded on 2026-05-18 vs a 2× ceiling of **16,885,929,040** |
| Margin | implied/issued = **3.26×**; the retained figure would have to understate by **1.63×** for the rejection to fail |
| Direction of error | HPG's issued count *rose* on 2026-07-02 (+767,498,665, `corporate_event_records` AIS), so the count applicable in May was **lower** — which strengthens the rejection |
| Admissible for valuation | **No** (`unit_anchor_admissible_for_valuation = False`) |

Sufficient as a falsifier. Usability against a thousand-fold tie is not a qualification, and
this figure remains inadmissible in a market capitalisation.

### Alternative anchors considered and rejected

- **HOSE board lot (100 shares).** Every observed `v` is a multiple of 100 — under both
  candidate readings. Does not discriminate.
- **Integrality of `v`.** No candidate produces a fractional share count. Does not discriminate.
- **Total market turnover.** No retained HOSE turnover figure exists offline, and obtaining
  one would require a network request.

### Verdict

```
unit_scale_ratio                    = 1
absolute_scale                      = resolved
absolute_scale_anchor               = numeric_identity_with_an_independently_unit_qualified_series
absolute_scale_corroborating_anchor = issued_share_count_plausibility_falsifier
volume_unit                         = shares          qualification = empirically_deduced
trading_value_unit                  = VND             qualification = empirically_deduced
```

Not downgraded. Neither route reaches `documented_verified` and neither can. With both
anchors withheld the result degrades to `scaled_units` / `scaled_units` /
`absolute_scale = unresolved` at `observed_only` — asserted by test 06.

---

## 3. Mutability state (Part B)

| Question | Verdict | Evidence |
|---|---|---|
| **Event-time historical rewriting** | `not_testable_from_retained_pairs` | Retained pair is `both_post_event`: retrievals 2026-08-01 and 2026-08-04 both post-date every qualified ex-right date in every tested window |
| **Post-event snapshot stability** | `observed_for_tested_retrieval_interval` | 9 HPG sessions, 2026-08-01 → 2026-08-04, 0 changed in close, volume or trading value |
| **Volume corporate-action adjustment** | `not_observed` | The pair does not straddle a share event; neither an unchanged nor a changed volume qualifies from it |

Contract field: `historical_mutability = not_observed`, derived by
`contract_historical_mutability` from the **event-time question alone**. Post-event
stability can never feed it.

### Why the retained evidence cannot settle the missing dimensions

Both observations sit on the same side of every candidate event. The restatement under test
would already have been applied before the earlier of them, so the diff between them carries
no information about it. This is a property of *when the observations were taken*, not of
which window was chosen or how much time has passed — which is exactly why the earlier
gloss ("the comparison spans no qualified share event") misleads: it reads as a fixable
selection problem.

### A defect found and fixed

`volume_adjustment_verdict` checked "did the volume change" **before** checking whether the
pair straddled a share event. A changed volume in a non-straddling pair therefore returned
`retrospectively_rewritten_unknown_method` — an ordinary post-event provider revision
reported in the vocabulary of a corporate-action adjustment. The pair-class gate now runs
first, and the caller's own `share_event_window_tested` flag cannot override the pair.

### A finding that is *not* volume adjustment, and is kept separate

On the 13 VCB sessions the VCI lane proved were rewritten (2026-07-01…17), KBS closes match
the stored pre-event rows **0/13** while KBS volumes match them **13/13**. Price restated,
volume not — the two fields move on different schedules. The boundary was a **cash**
distribution, which has no share count to restate, so this says nothing about what a share
event does to volume. `verdict = price_restated_while_volume_unchanged`, explicitly not an
input to `volume_adjustment_basis`.

---

## 4. Prospective protocol (Parts C and D)

`kbs_mutability_protocol.py`. Designed, **not executed**.

**Pre-event requirements** — 16 mandatory manifest fields, and one substantive check:
the snapshot must be retrieved **strictly before** the ex-right date. A same-day or later
retrieval is not a weaker pre-event snapshot, it is a post-event snapshot, and
`build_pre_event_manifest` raises `snapshot_is_not_pre_event`. The historical window must
also close before the ex-date so every compared row is already final.

**Post-event requirements** — identical provider, ticker, endpoint, request parameters and
historical window (`assert_post_event_request_matches`), retrieved on or after the ex-date.
Any drift turns a rewrite test into a comparison of two different questions.

**Comparison fields** — `o`, `h`, `l`, `c`, `v`, `va`, row presence, schema. Presence and
schema are on the list because a disappeared row and a renamed field are both rewrites and
neither shows up in a value diff.

**Control design** — a no-event control ticker or window is required. A provider that
restates everything on a maintenance schedule would move the event window and the control
alike; only the control separates "the event caused this" from "the provider rewrote that
week". A control that also moved yields `comparison_conflicted`, not an event verdict.

**Change classes**, kept apart: `price_rewrite`, `volume_rewrite`, `value_rewrite`,
`schema_change`, `unrelated_provider_correction`.

**Permitted verdicts**, each scoped to the tested event and window:
`event_time_price_rewrite_observed`, `event_time_volume_rewrite_observed`,
`price_rewrite_without_volume_rewrite`, `no_rewrite_observed_for_tested_event`,
`provider_schema_changed`, `comparison_conflicted`, `observation_incomplete`.
`assert_verdict_scoped` refuses a verdict that names a `provider_methodology` or widens
`coverage_generalization` — one event stays one event.

**What a completed observation would change** — written now, before any result exists, so
it is not negotiated after seeing one. `contract_effect` moves `historical_mutability` and
`volume_adjustment_basis` and nothing else: `raw_as_traded_eligible`,
`official_exchange_price`, `liquidity_actionable`, `production_write` and
`capability_activation` all stay false, and `volume_market_scope` stays `unknown`.

**Automation status — none.** `network_access_authorized`, `scheduling_authorized`,
`event_polling_authorized` and `automatic_acquisition_authorized` are all false and asserted
by `assert_protocol_inert`. The module imports only `hashlib`, `json`, `typing` and two
repository modules — verified against its parsed import graph, not by scanning its prose,
which is *about* networks and schedules. Owner authorisation is required per event.

Artifacts: `operations-review/kbs-mutability-observation/<ex-date>-<event-id>/<phase>/`.

---

## 5. Capability preservation (Part E)

Unchanged from `4a07141`. Verified by tests 14–18.

**Available** (15): OHLCV display, historical chart, descriptive price statistics,
descriptive volume statistics, descriptive trading-value statistics, provider-scoped
relative volume, provider-scoped price momentum, anomaly detection, cross-provider
corroboration, moving average, RSI, MACD, Bollinger Bands, technical-pattern research,
shadow analytics.

**Conditional** (2): provider-series return and provider-series technical continuity, behind
`return_type = provider_series_return`. `raw_as_traded_return`, `official_exchange_return`
and `total_shareholder_return` raise.

**Unavailable by contract** (13): days-to-liquidate, market impact, liquidity-adjusted
sizing, negotiated-flow analysis, odd-lot analysis, liquidity-dependent ranking,
volume-derived actionability upgrade, participation-rate sizing, executable-capacity claims,
production backtest, point-in-time valuation, official exchange price claims, official
total-return claims.

An unobserved mutability dimension is not a reason to close a chart. Nothing regressed.

---

## 6. Documentation corrections (Part F)

| Location | Statement | Action |
|---|---|---|
| P0-Z closing report (chat, uncommitted) | "Re-request the HPG window after enough elapsed time" | Superseded — `SUPERSEDED_RECOMMENDATION` |
| `operations-review/kbs-empirical-basis-20260804/KBS_EMPIRICAL_BASIS.md` §3, §5, §8 | "spans no qualified share event" | **Not edited.** Correction recorded in `CORRECTED_FRAMING` with `measurements_changed: false`, `artifact_rewritten: false` |
| `docs/kbs_empirical_basis_qualification.md` | same gloss | Corrected in place — new "three mutability questions" section |
| `docs/STATE.md`, `docs/ROADMAP.md` | same gloss | Corrected in place |
| `docs/DECISIONS.md` | P0-Z entry | Marked `PARTIALLY CORRECTED` in place, pointing to the P0-Z.1 entry |
| `docs/AI_RULES.md` | — | Rules 8d and 8e added |
| `provider_price_basis_registry.py` KBS entry | comment implying a window-selection gap | Corrected; three mutability keys added |

Immutable evidence preserved — verified byte-unchanged by `git status`:
`raw/` (all six payloads), `evidence_manifest.json`, `observations.json` and
`KBS_EMPIRICAL_BASIS.md`. Test 19c asserts the report still exists and still contains its
original wording.

`basis_summary.json` **is** regenerated, and deliberately so: it is the *derived* analysis
output, reproducible at any time by `python tools/run_kbs_empirical_basis.py --offline`
from the unchanged raw bytes. Leaving it stale would have left a file in the tree asserting
mutability conclusions the corrected code no longer supports. No input changed; no
measurement changed; the diff is the three separated mutability keys, the identity anchor
and the protocol record.

---

## 7. Validation

| Suite | Tests |
|---|---|
| `test_kbs_mutability_protocol.py` (new) | 26 |
| `test_kbs_empirical_basis.py` | 36 |
| `test_ohlcv_basis_qualification.py`, `test_vci_direct_basis_pilot.py`, `test_vci_volume_composition.py`, `test_market_volume_capability_contract.py` | 119 |
| `test_corporate_action_factors.py`, `test_export_ai_bundle.py`, `test_risk_liquidity.py`, `test_analysis_lane_eligibility.py`, `test_point_in_time_adjusted_prices.py`, `test_market_data_lineage.py`, `test_ticker_capability.py`, `test_evidence_replay.py` | 216 |
| Consumer readiness and pass-through | 22 |
| **Total** | **419** |

Network-free proof: zero requests issued; `NETWORK_ACCESS_AUTHORIZED = False`; the protocol
module's parsed import graph is exactly `{__future__, hashlib, json, typing,
evidence_qualification_tiers, kbs_empirical_basis}`.

Evidence integrity: all six raw payload hashes unchanged; `evidence_manifest.json`
`manifest_sha256 = 06ef6206e5c1bd3253fdb7dbd89e330ae69207900086dfa8d9c5d2a4052752fc`;
replay deterministic.

---

## 8. Non-effects

No network request. No production database write, bundle or dashboard publication. No change
to valuation outputs, liquidity outputs, sizing, rankings, recommendations, backtesting or
`is_actionable`. No unknown dimension upgraded. The VCI verdict is untouched.

**Observed, and not caused by this milestone.** The runtime artifacts under
`dashboard-runtime/` changed between the P0-Z session and this one: `ta_signals` 17:19,
`vn_stock.db` 17:25, `Market_Scan`/`Focus_Analysis` 17:26, `analysis_bundle.json` /
`bundle_manifest.json` / `focus_extract.json` 17:28 — the ordinary daily market chain.
`reports/operate_stocklookup_latest.json` is still 2026-08-03 20:15, so the supported
operating command did not run. This milestone's earliest write is 18:18:56, fifty minutes
after the last runtime write, and it wrote only to source files and
`operations-review/`. Recorded here because "production artifacts unchanged" would have
been false as stated and true only as intended.

```
KBS_EMPIRICAL_CLOSEOUT: PASS
```
