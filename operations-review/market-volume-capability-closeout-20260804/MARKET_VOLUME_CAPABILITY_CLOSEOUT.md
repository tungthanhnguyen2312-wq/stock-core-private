# Market-volume and liquidity availability contract closeout

**Date:** 2026-08-04 · **Starting commit:** `63ecc48` · **Live requests:** 0
**Scope:** contract and consumer gates. No data acquisition, no probing, no provider added.

---

## What this milestone converted

`63ecc48` established the VCI volume facts. This milestone turns them into boundaries a
consumer cannot walk past, and corrects two words that were doing more work than the
evidence supports.

The substantive finding is a **latent** one, not a live defect. Every liquidity gate in the
repository was expressed as *blocked while `volume_basis_verified` is false*. That is a
pending state with an obvious release, and the composition closeout made that release
dangerous: the unit is shares and the provider's own arithmetic closes exactly, so a future
reader has every reason to verify the basis — and would thereby open days-to-liquidate,
participation-rate sizing and backtest liquidity constraints on a figure whose market
composition nobody has established. Whether it includes put-through blocks is unknown, and
no amount of unit qualification answers that.

Nothing in production was open. Everything in production was one plausible edit from being
open.

---

## Part A — corrected and frozen VCI contract

Two terminology corrections, no change to any verdict:

| was | is | why |
| --- | --- | --- |
| `market_scope = partially_qualified` | `overall_market_scope = partially_observed_but_not_qualified` | The old word was accurate about one dimension and readable as "qualified enough to size against". |
| `opening_auction_inclusion = qualified` | `= demonstrated_for_observed_ato_field` | What was demonstrated is that one observed ATO-labelled quantity sits inside the accumulator. |
| `auction_inclusion = qualified` | `general_auction_composition = partially_observed` | A roll-up over one demonstrated leg and one unobserved leg. `qualified` is no longer a reachable value for it. |

And one promotion, which is not a terminology change but a relocation of an existing finding:
`matched_trade_inclusion`, `negotiated_inclusion` and `odd_lot_inclusion` were recorded at
`63ecc48` as `unknown` at the top level with `unavailable_from_observed_vci_surfaces` in a
`unresolved_dimension_resolution` sidecar. They now carry the terminal verdict at the top
level, where a consumer actually reads. A test asserts the old and new records agree on
every dimension.

The narrow ATO result is now stated at the width it was demonstrated at:

```text
opening_auction_labeled_quantity                        = observed
opening_auction_referent                                = qualified_by_exchange_standard_term
opening_auction_included_in_provider_accumulated_volume = demonstrated
closing_auction_inclusion                               = unknown
general_auction_composition                             = partially_observed
```

**Two assertion functions, not one.** `assert_fail_closed()` answers "is this safe" and
accepts the superseded vocabulary, so the frozen artifact at `63ecc48` can still be checked.
`assert_canonical_vocabulary()` answers "may this be active" and refuses it. A contract can
be safe and non-canonical; only the frozen one is.

**No evidence artifact was rewritten.** `composition_summary.json` keeps
`partially_qualified` exactly as written, and `active_contract()` carries a `supersedes`
record naming the artifact, the commit, the retired word and `evidence_changed: false`.
(`tools/audit_vci_evidence.py` rewrites its own output file when run; that write was
reverted, and the audit's substantive counts were unchanged by it.)

Closed probe paths, unchanged and re-asserted under a third key name:
`further_vci_pagination_authorized`, `further_speculative_endpoint_probe_authorized` and the
canonical `further_vci_endpoint_probe_authorized` are all `false`, and must agree.

## Part B — capability matrix

`market_volume_capability_matrix.py`. Twenty-two capabilities in five classes.

**Nine retained** — six descriptive, three analytical. Volume history, moving averages,
provider-scoped relative volume, trend indicators, same-series anomaly detection,
source-labelled comparison; research-only volume indicators, volume confirmation, and the
turnover-tier screening score. Each carries four mandatory warnings, enforced structurally:
`market_composition_unresolved`, `corporate_action_adjustment_unresolved`,
`value_is_provider_scoped`, `not_an_official_exchange_volume_contract`.

**Thirteen unavailable by contract** — eight liquidity-dependent, five execution-dependent.
All carry `reason = complete_market_composition_not_qualified` and
`reopen_condition = new_authoritative_source_contract`, plus a reopen note that names what
does *not* reopen them, so the short form cannot be read as "paginate VCI once more".

`liquidity_actionable` is a constant `False` in every return path. No argument to
`evaluate()` opens a contract-unavailable capability — not `existing_gates_passed=True`, not
a different provider. A test sweeps the cross-product to prove it.

**`turnover_tier_screening_score` is the judgement call in this matrix.** `stock_analyzer`'s
`score_liquidity` bands close × volume into tiers for screening. It is named for liquidity
and it is not a liquidity measure, and the two available responses were to disable it or to
classify it honestly. It is retained as `analytical_not_liquidity_dependent`: a relative
screen over one provider series, never exportable as qualified market liquidity. Disabling
it would have changed production ranking output, which this milestone is forbidden from
doing, and would have been a real cost for no safety gain — the score has never claimed
tradable size. A reader who disagrees should reclassify it as `liquidity_dependent`, at
which point the matrix shuts it and the ranking changes.

## Part C — consumer audit

Twenty-three volume-touching consumers found across Producer and Consumer, all classified in
`CONSUMER_CLASSIFICATION`. An unregistered consumer resolves to `unknown_or_ambiguous` /
`unavailable_pending_classification` — so adding one requires classifying it.

Four files changed, each the smallest change that closes a path:

**`risk_liquidity.py`** — `days_to_liquidate` returned
`missing_inputs=["portfolio_order_size", "participation_rate", "qualified_volume_units"]`.
That shape says *supply these and I will compute it*, and two of the three are things a
caller genuinely has. It now returns `availability: unavailable_by_contract` with an empty
`missing_inputs`, and `participation_rate_sizing` and `market_impact` are reported alongside
it in the same terminal shape rather than being absent and therefore unclaimed.

`dimensions.liquidity` read `"available"` whenever descriptive average volume was computable.
A descriptive mean was making a dimension named *liquidity* report available. It is now
`unavailable_by_contract` unconditionally, and the descriptive fact moved to its own
`descriptive_provider_volume` dimension, which still reports `available`. In production both
readings were already `unavailable` because the basis is unverified — this changes what
happens when that stops being true.

`average_volume` still computes, still returns its value. It now carries `source: "VCI"`,
its capability class, `is_actionable: False` and the four standing warnings.

**`vci_volume_basis.py`** — `forward_gate.action` read
`block_liquidity_activation_when_unverified`, which says, correctly read, that verifying the
basis *activates* liquidity. That is now false. It reads
`block_liquidity_activation_unconditionally`, and `validate_forward()` returns
`liquidity_activation_permitted: False` on success — so a caller wanting liquidity has to
override a stated refusal rather than infer consent from the absence of an exception. The
shares finding is recorded as `observed_volume_unit`, kept separate from `volume_basis`,
which stays `unknown` because corporate-action adjustment is a different question.

**`analysis_lane_eligibility.py`** — Gate 1's `liquidity_claims_blocked:volume_basis=...`
warning lifts when the basis verifies. Correct for adjusted returns, wrong for liquidity.
The existing warning string is untouched (a Consumer fixture quotes it verbatim); a separate
unconditional `LIQUIDITY_CONTRACT_WARNING` is now appended on every lane for every ticker
regardless of basis state, under its own token so nothing that asserted on the old one moved.

**Intentionally not changed:** `stock_analyzer.score_liquidity`, `candlestick_patterns`
relative-volume and volume-confirmation features, `vn_indicators` volume indicators, and
OHLCV volume pass-through in the bundle. All descriptive or analytical, all classified, none
disabled.

## Part D — official authority candidate

`official_authority_candidates.py`. HOSE trading statistics, registered as
`future_qualification_candidate` with `automatic_acquisition_authorized: false` and
`acquisition_state: nothing_acquired`.

Deliberately a separate module from `official_source_registry.py`. That registry gates the
network, its `hose` entry is already `approved` for corporate-action notices, and registering
trading statistics there would have been one JSON edit away from a scraper. This module
performs no I/O, records **no URL** — none has been observed and retained, and a plausible
route written from memory is a fabricated locator — and `assert_not_acquirable()` proves no
approved source admits a trading-statistics document type. A test adds one to the `hose`
entry and asserts the check fails.

Eight open semantic questions recorded: matched volume definition; negotiated volume
definition; relationship between matched and total volume; units and scaling; ticker-level
availability; date coverage; machine-readable access; access and reuse terms.

Recorded as the **preferred currently identified official authority path**, not the sole
theoretically possible authority — no survey of alternatives was done, and a test scans the
snapshot for sole-authority phrasing.

## Part E — terminology audit

| check | result |
| --- | --- |
| ATO described as a narrow inclusion result | yes — three explicit narrow fields, plus prose in `docs/market_volume_capability_contract.md` |
| any active document says full auction composition is qualified | no — `general_auction_composition` cannot take the value `qualified` |
| any active document calls VCI daily volume official exchange volume | no — `not_an_official_exchange_volume_contract` is a mandatory warning; `official_exchange_volume` is a forbidden generic field in two modules |
| any active document calls market scope qualified | no — `partially_qualified` survives only in the frozen artifact, the supersession record, and the code that refuses it |
| any active document says qualification is one pagination away | no — scanned; the reopen note states the opposite explicitly |
| VCI probing recorded as closed | yes — three keys, all `false`, all asserted |
| evidence manifests from `63ecc48` complete | yes — 0 unreferenced raw artifacts, 0 secret findings, all raw names self-verifying |
| evidence artifacts rewritten or deleted | none |

---

## Validation

| suite | result |
| --- | --- |
| `test_market_volume_capability_contract.py` (new) | **46 passed** — all 18 required proofs |
| Producer focused set, 18 modules — the new suite plus VCI volume composition, contract reconciliation, direct basis pilot, risk/liquidity, lane eligibility, price basis contract/events/qualify, ticker capability, candlesticks, opportunity snapshot, bundle export, hash manifest, evidence registry/replay, semantic evidence bridge, official evidence | **435 passed + 11 subtests** |
| Consumer context/readiness/pass-through, 6 modules | **118 passed** |
| `tools/audit_vci_evidence.py` | 155 files, **0** unreferenced raw, **0** secrets, all names self-verifying, 0 removed |
| `compileall` over all 8 changed Python files | exit 0 |

Total **553 passing + 11 subtests**, 0 failing (the 46 are inside the 435). No live
acquisition is a dependency of any test; the
network-free proof is structural — `socket.connect`, `socket.create_connection` and
`urllib.request.urlopen` are patched to raise across the candidate registration path.

## Non-effects

No production database, bundle, dashboard, ranking, recommendation, sizing output,
backtesting output, generic official-exchange field, or `is_actionable` value changed. The
VCI price supersession is intact and tested; P2a remains blocked for the same recorded
reason. No network request was issued by any part of this milestone.

---

**`MARKET_VOLUME_CAPABILITY_CLOSEOUT: PASS`**

## Recommended next bounded milestone

**Qualify the second provider's volume field on its own evidence, or record that it cannot
be.** The matrix now states that KBS, SSI and every other provider inherit nothing — which
is correct and also means the repository has exactly one provider with any volume verdict at
all. The honest next step is to run the same composition question against the retained KBS
OHLCV evidence already in `operations-review/`, from retained artifacts only, and produce
either a KBS volume contract or a recorded `unavailable_from_observed_kbs_surfaces`.

No VCI probing. No HOSE acquisition. No new provider, no live request — retained evidence
only. HOSE's eight questions stay open until a separately authorized milestone answers them.
