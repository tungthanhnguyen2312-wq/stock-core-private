# KBS empirical basis and capability contract

Active as of 2026-08-04. Evidence:
`operations-review/kbs-empirical-basis-20260804/` (report, summary, manifest, six raw payloads).

Implemented by `evidence_qualification_tiers.py`, `kbs_empirical_basis.py`,
`kbs_capability_matrix.py`, and the `KBS` entry in `provider_price_basis_registry.py`.

---

## The qualification ladder

`evidence_qualification_tiers.py` holds one vocabulary for *how well* a claim is evidenced,
separate from *what* it claims:

| Tier | Meaning |
|---|---|
| `documented_verified` | The provider or an authoritative first-party source explicitly defines the field or methodology. **Only this tier speaks for the source.** |
| `empirically_deduced` | A reproducible, falsifiable test supports a narrowly scoped conclusion. The scope is part of the verdict. |
| `observed_only` | The field exists and its identity is known; its economic basis is unresolved. |
| `unknown` | Evidence is insufficient. |
| `conflicted` | Two live evidence paths disagree and no justified supersession resolves them. |
| `invalidated` | A prior verdict was demonstrated false. |

`empirically_deduced` is not a cheaper `documented_verified`. A verdict at that tier must
carry all thirteen fields in `EMPIRICAL_RECORD_FIELDS` — method, tested fields, tickers,
windows, event evidence, artifact hashes, transformation version, alternatives considered,
falsification attempts, confidence, scope limits, retrieval timestamps, mutability status —
and `assert_empirically_deduced` refuses one that does not, including one whose
alternatives or falsifications lists are merely empty. Claiming the tier is deliberately
more work than claiming `unknown`.

Three rules the ladder enforces rather than merely documents:

- `may_claim_official_semantics` is true only for `documented_verified`. No number of
  agreeing windows converts an observation into a provider statement.
- `apply_corroboration` attaches evidence and copies the tier through unchanged, recording
  `corroboration_upgraded_qualification: false`. Cross-source agreement is compatibility.
- `resolve_active` returns `conflicted` when live records disagree. Recency does not
  resolve a conflict, and neither does tier strength — a justified `supersede()` does, and
  it must state what the superseded verdict was right about.

## KBS contract

```
provider              = KBS
source_authority      = observed_public_web_endpoint
documented_semantics  = absent
field_identity        = qualified        (t, o, h, l, c, v, va)

price_basis                    = empirically_event_adjusted
price_basis_qualification      = empirically_deduced
historical_mutability          = not_observed
observed_adjustment_dimensions = cash_distribution, share_related_event
provider_methodology           = unknown
coverage_generalization        = limited_to_tested_windows
raw_as_traded_eligible         = false
official_exchange_price        = false

volume_unit               = shares         qualification = empirically_deduced
trading_value_unit        = VND            qualification = empirically_deduced
volume_adjustment_basis   = not_observed
volume_market_scope       = unknown
liquidity_actionable      = false
```

Tested on HPG, VNM and VCB, HOSE, 2026 only, across three qualified ex-right boundaries and
two no-event controls.

## The three mutability questions

`historical_mutability = not_observed` is one answer to one of three separate questions.
They were previously described in a way that ran them together, and the distinction is the
whole reason the last of them is still open:

| Question | Status | What would settle it |
|---|---|---|
| **Event-time historical rewriting** — do historical rows change when a corporate action becomes effective? | `not_testable_from_retained_pairs` | A snapshot retained **before** a future event plus a matching one after it |
| **Post-event snapshot stability** — do repeated post-event requests return the same values? | `observed_for_tested_retrieval_interval` (9 sessions, 2026-08-01 → 2026-08-04, no change) | Already answered, for that interval only |
| **Volume corporate-action adjustment** — is historical `v` rescaled by a share event? | `not_observed` | A pre/post as-of pair straddling a **share** event, or an independent direct contract |

**Correction (2026-08-04).** Earlier wording said the retained comparison "spans no
qualified share event". That is true and it misleads, because it implies the gap was a
choice of window. It was not. Both retrievals post-date every qualified ex-right date in
every tested window, so no window selection and no amount of further elapsed time can
produce a pre/post pair from this evidence. **Event-time historical mutability requires a
snapshot retained before a future event and a matching snapshot retained after the event.**
A second request against an already-post-event window measures post-event stability and
nothing else.

`classify_snapshot_pair` enforces this: a pair whose retrievals sit on the same side of the
event returns `both_post_event`, and `historical_rewrite_test` then reports
`event_time_rewriting = not_testable_from_this_pair` however clean the diff is.
`kbs_mutability_protocol.assert_not_a_retrospective_substitute` raises outright.

The prospective protocol is `kbs_mutability_protocol.py`. It is inert: no network, no
scheduling, no polling, no automatic acquisition. See the table under "Prospective
protocol" below.

## What the evidence supports, and where each result stops

**Price.** Pre-event sessions sit off the HOSE tick lattice, so they were never matched
order prices; the off-lattice prefix terminates exactly at a qualified ex-right date in
three windows across three tickers. Independently, the provider omits `va` over exactly the
off-lattice runs — presence tracks the boundary, not the calendar. This says the series is
event-adjusted. It does not say by what method, nor which events the provider silently
does not adjust for.

**Units.** The VWAP identity constrains only the *quotient* of the two scales;
`(1, 1)` and `(1000, 1000)` are indistinguishable by it in principle. The quotient (1.0)
is earned from 36 discriminating rows across three tickers and three price levels. Two rows
are explained by no candidate scale and are retained as contradictions.

The **absolute** scale is earned separately, by two independent routes. Without either, the
units report `scaled_units` at `observed_only` and `absolute_scale = unresolved`.

| Route | Evidence | Authority |
|---|---|---|
| `numeric_identity_with_an_independently_unit_qualified_series` (**primary**) | KBS returns integers exactly equal to locally stored VCI volumes on **34 sessions across all three tickers**. VCI's volume unit was established from its own per-trade tape (commit `63ecc48`), not from a plausibility bound. Equality is arithmetically impossible under a thousand-fold unit difference. | `empirically_deduced`, capped by the reference verdict's own tier. Transfers **magnitude only** — VCI's market scope, adjustment behaviour and source authority are *not* inherited (`assert_identity_anchor_is_magnitude_only`). |
| `issued_share_count_plausibility_falsifier` (corroborating) | `(1000, 1000)` implies HPG trading 27,485,500,000 shares on 2026-05-18 against a retained 8,442,964,520 issued — rejected past a deliberately loose 2× ceiling, with a 1.63× margin. | `observed_only`. The share count is a **falsifier, not a measurement**, and stays inadmissible for valuation (`unit_anchor_admissible_for_valuation = False`). |

Neither route reaches `documented_verified`, and no route can.

**Volume.** Not derived from the price finding, in either direction.
`volume_adjustment_verdict` takes the price verdict as an argument solely so the refusal is
explicit. A separate observation — KBS restated prices on 13 VCB sessions while returning
volumes byte-identical to the independently retained pre-event series — shows the two fields
move on different schedules, and is not the same claim as knowing what a share event does.

**Market scope.** Every dimension is `unknown`. Upgrading one needs two admissible
independent observations with all six confounders eliminated; secondary media are counted
and never qualify. The unit result cannot touch this, and
`assert_unit_does_not_qualify_scope` raises if a caller tries.

## Capability classes

| Class | Availability |
|---|---|
| `descriptive_provider_scoped` | available under existing gates |
| `technical_provider_scoped` | available under existing gates |
| `conditional_labelled_provider_series` | available only with `return_type = provider_series_return` |
| `shadow_only_eligibility` | eligibility defined, **not implemented** |
| `liquidity_dependent` / `execution_dependent` | unavailable by contract |
| `point_in_time_dependent` | unavailable by contract |
| `unknown_or_ambiguous` | refused |

Every available capability carries `REQUIRED_WARNINGS` and `REQUIRED_PROVENANCE_FIELDS`.
They are not decoration: the capability stays open *because* the caller must carry them, and
`assert_matrix_fail_closed` refuses a matrix that opened one without them.

"Unavailable by contract" is terminal, not pending. There is no field a caller can set and
no argument to `evaluate()` that opens it. The stated way out is a new authoritative source
contract defining what the volume figure counts, or a first-party methodology / immutable
point-in-time source for the historical-truth class.

The three forbidden return labels — `raw_as_traded_return`, `official_exchange_return`,
`total_shareholder_return` — raise rather than returning unavailable, because a mislabelled
return is worse than a missing one.

## Prospective protocol — `kbs_mutability_protocol.py`

Designed, not executed. It issues no request, schedules nothing, watches for no event and
polls nothing; `assert_protocol_inert` refuses a record that switched any of that on, and
the test suite checks the module's parsed import graph rather than trusting the prose.

| Requirement | Enforced by |
|---|---|
| Pre-event snapshot retrieved **strictly before** the ex-right date | `build_pre_event_manifest` raises `snapshot_is_not_pre_event` otherwise |
| Historical window closed before the ex-date, so every row is already final | `build_pre_event_manifest` |
| Post-event request identical in provider, ticker, endpoint, parameters and window | `assert_post_event_request_matches` |
| Immutable raw bytes, hash, schema fingerprint, parameters, retrieval instant | `PRE_EVENT_MANIFEST_FIELDS` (16 required) |
| Field-by-field diff of `o` `h` `l` `c` `v` `va`, row presence and schema | `compare_snapshots` |
| A no-event control ticker or window | `control_required`; a control that also moved yields `comparison_conflicted` |
| Change classes kept apart | `price_rewrite`, `volume_rewrite`, `value_rewrite`, `schema_change`, `unrelated_provider_correction` |
| One event stays one event | `assert_verdict_scoped` refuses a verdict that names a methodology or widens coverage |
| Nothing is activated by a result | `contract_effect` moves the mutability dimensions only |

Permitted verdicts: `event_time_price_rewrite_observed`, `event_time_volume_rewrite_observed`,
`price_rewrite_without_volume_rewrite`, `no_rewrite_observed_for_tested_event`,
`provider_schema_changed`, `comparison_conflicted`, `observation_incomplete`.

Artifacts land at `operations-review/kbs-mutability-observation/<ex-date>-<event-id>/<phase>/`,
with the phase in the path — a file whose name does not say which side of the event it came
from is one filesystem accident away from being useless.

Identifying a suitable future event and authorising the pre-event snapshot is an owner
decision. The protocol is inert until one is taken.

## Boundaries

- Six requests, three tickers, windows capped at 45 days by `daily_params`. `acquire` is the
  only network-touching function; both contract modules are pure and import no database
  driver.
- Raw bytes are stored verbatim and hash-addressed with the retrieval instant in the name,
  so a differing later observation lands beside the earlier one rather than replacing it.
- `assert_no_generic_upgrade` refuses a generic or foreign-provider namespace;
  `assert_no_provider_inheritance` refuses to let the verdict travel.
- No production database write, no bundle or dashboard publication, no `is_actionable`
  effect.

See also: [price_basis_qualification_contract.md](price_basis_qualification_contract.md),
[market_volume_capability_contract.md](market_volume_capability_contract.md),
[vci_volume_basis_qualification.md](vci_volume_basis_qualification.md).
