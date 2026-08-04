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
two no-event controls. `historical_mutability = not_observed` records the absence of a
rewrite test spanning an event, not an immutable history.

## What the evidence supports, and where each result stops

**Price.** Pre-event sessions sit off the HOSE tick lattice, so they were never matched
order prices; the off-lattice prefix terminates exactly at a qualified ex-right date in
three windows across three tickers. Independently, the provider omits `va` over exactly the
off-lattice runs — presence tracks the boundary, not the calendar. This says the series is
event-adjusted. It does not say by what method, nor which events the provider silently
does not adjust for.

**Units.** The VWAP identity constrains only the *quotient* of the two scales;
`(1, 1)` and `(1000, 1000)` are indistinguishable by it in principle. The quotient (1.0)
is earned from 36 discriminating rows across three tickers and three price levels. The
absolute anchor is earned separately, from a retained issued-share count used strictly as an
order-of-magnitude falsifier — admissible because the tie is a factor of a thousand, and
recorded as a falsifier rather than a measurement. Two rows are explained by no candidate
scale and are retained as contradictions.

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
