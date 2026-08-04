# Market-volume capability contract

**Status:** active · **Established:** 2026-08-04 · **Provider scope:** VCI only
**Modules:** `market_volume_capability_matrix.py`, `vci_volume_composition.py`,
`official_authority_candidates.py`

This is the contract that says what may be computed from a volume figure. It exists because
every liquidity gate before it was phrased as *pending*, and the VCI composition closeout
made "pending" the wrong shape.

---

## The one-sentence version

VCI's volume field is internally consistent, denominated in shares, and includes one
demonstrated opening-auction quantity — and none of that says which trades it counts, so
liquidity and execution analytics are unavailable **by contract**, while descriptive
provider-scoped volume stays available.

---

## Canonical active VCI volume contract

Assembled once, by `vci_volume_composition.active_contract()`. Consumers read it; they do
not re-derive it from an evidence file.

```text
provider_internal_volume_reconciled                     = true
volume_unit                                             = shares
volume_field_identity                                   = qualified
volume_corporate_action_adjustment                      = unknown

opening_auction_inclusion                               = demonstrated_for_observed_ato_field
  opening_auction_labeled_quantity                      = observed
  opening_auction_referent                              = qualified_by_exchange_standard_term
  opening_auction_included_in_provider_accumulated_volume = demonstrated
closing_auction_inclusion                               = unknown
general_auction_composition                             = partially_observed
matched_trade_inclusion                                 = unavailable_from_observed_vci_surfaces
negotiated_inclusion                                    = unavailable_from_observed_vci_surfaces
odd_lot_inclusion                                       = unavailable_from_observed_vci_surfaces

overall_market_scope                                    = partially_observed_but_not_qualified
liquidity_actionable                                    = false
further_vci_pagination_authorized                       = false
further_vci_endpoint_probe_authorized                   = false
```

### What "partially" is doing in that sentence

The qualified component is **the inclusion of one observed opening-auction-labelled quantity
in the VCI accumulator**. It is not the composition of the volume field.

`partially_qualified` was the previous spelling and has been retired. It was accurate about
one dimension and readable as "qualified enough to size against", and that second reading is
the one the evidence does not support.
`assert_canonical_vocabulary()` refuses it in an active contract.
`assert_fail_closed()` still accepts it, so that the frozen artifact at `63ecc48` can be
checked for safety without being rewritten.

### What the ATO finding is, stated narrowly

The price board carried `matchVolumeATO`, `matchPriceATO` and a `firstTimeMatchPrice` that
all landed on the retained tape's first trade of the session, which is the accumulator's
first entry. ATO is a HOSE session code — the referent is fixed by exchange regulation, not
by a VCI field name — and a second independent field pinned the same instant.

That demonstrates **one observed quantity is inside the accumulator**. It does not
demonstrate what fraction of the day's auction activity the field represents, it says nothing
about the closing auction, and it is not a decomposition of anything.

---

## Capability classes

### Available, provider-namespaced, under existing gates

These keep working. Disabling them would cost real utility and buy no safety — a mean over
one provider's own series was never a claim about executable depth.

| capability | class |
| --- | --- |
| `provider_volume_history_display` | descriptive |
| `provider_volume_moving_average` | descriptive |
| `provider_relative_volume` | descriptive |
| `provider_volume_trend_indicator` | descriptive |
| `provider_volume_anomaly_detection` | descriptive (same-series only) |
| `source_labeled_volume_comparison` | descriptive |
| `research_only_volume_technical_indicator` | analytical |
| `volume_confirmation_signal` | analytical |
| `turnover_tier_screening_score` | analytical |

Each carries four standing warnings, enforced by `assert_matrix_fail_closed()`:

```text
market_composition_unresolved
corporate_action_adjustment_unresolved
value_is_provider_scoped
not_an_official_exchange_volume_contract
```

"Under existing gates" means this contract does not open them either. Freshness and
provenance still decide; this matrix only says they are not forbidden.

### Unavailable by contract

```text
availability     = unavailable_by_contract
reason           = complete_market_composition_not_qualified
reopen_condition = new_authoritative_source_contract
```

| capability | class |
| --- | --- |
| `days_to_liquidate` | liquidity |
| `market_impact_estimation` | liquidity |
| `capacity_estimation` | liquidity |
| `negotiated_versus_matched_flow_analysis` | liquidity |
| `odd_lot_analysis` | liquidity |
| `auction_versus_continuous_decomposition` | liquidity |
| `volume_based_ranking_or_recommendation` | liquidity |
| `volume_derived_actionability_upgrade` | liquidity |
| `participation_rate_sizing` | execution |
| `liquidity_adjusted_position_sizing` | execution |
| `average_daily_volume_portfolio_sizing` | execution |
| `execution_simulation` | execution |
| `production_backtest_liquidity_constraint` | execution |

**Not** "pending more VCI pagination". The reopen note is carried in the record itself:

> Not reopenable by further VCI pagination, further VCI endpoint probing, or by verifying
> the volume unit or basis. Only a source that publishes what its volume figure counts —
> matched versus negotiated, auction versus continuous — can reopen these, and no such
> source is active.

There is no argument to `evaluate()` that opens one. `existing_gates_passed=True` does not.
A different provider does not.

### Unknown or ambiguous

A consumer absent from `CONSUMER_CLASSIFICATION` resolves to `unknown_or_ambiguous` and
`unavailable_pending_classification`. Adding a volume consumer therefore requires classifying
it, which is what keeps this document true.

---

## Inheritance boundaries

* **Generic fields do not inherit.** `volume`, `market_volume`, `total_volume`,
  `exchange_volume`, `official_exchange_volume`, `matched_volume` and `traded_volume` raise
  from `assert_no_generic_field_upgrade()`. The VCI closeout is a statement about `vci.v`; a
  field that does not name its provider cannot receive it.
* **Other providers do not inherit.** KBS, SSI, EODHD and anyone else get
  `contract_applies: false` and `volume_composition: unknown` — unqualified because nobody
  qualified them, not because VCI's verdict was copied across. Each is owed its own closeout.

---

## Future official authority candidate

`official_authority_candidates.py` — registered, not active, and structurally unable to
fetch.

```text
source                            = HOSE
authority                         = official_exchange
authority_position                = preferred_currently_identified_official_authority_path
status                            = future_qualification_candidate
automatic_acquisition_authorized  = false
acquisition_state                 = nothing_acquired
locator                           = null
```

HOSE publicly distinguishes matched-order trading statistics, negotiated/put-through
trading statistics, and end-of-day matched volume — the exact distinction absent from all 96
observed VCI fields. That is why it is the preferred path. It is *the preferred currently
identified* path, not the sole theoretically possible authority; no survey of alternatives
has been done.

**Eight open questions**, all unanswered:

1. matched volume definition
2. negotiated volume definition
3. relationship between matched and total volume
4. units and scaling
5. ticker-level availability
6. date coverage
7. machine-readable access
8. access and reuse terms

**No URL is recorded**, because none has been observed and retained in this repository.
A plausible-looking route written from memory is a fabricated locator. A future milestone
must obtain the locator, not compose it.

`assert_not_acquirable()` checks that no source in `config/official_source_registry.json`
admits a trading-statistics document type. The `hose` entry there is approved for corporate
action notices only; adding a trading-statistics type to it fails a test rather than quietly
enabling a scraper.

---

## What this contract did not change

Nothing in the price lane. VCI's price verdict remains `empirically_event_adjusted`, the
Phase 3A `raw_as_quoted` verdict remains superseded, and P2a historical valuation remains
blocked — `raw_as_traded_eligible("VCI")` is still false for the same reason it was before.

No production database, bundle, dashboard, ranking, recommendation, sizing or backtest
output, and no `is_actionable` value.
