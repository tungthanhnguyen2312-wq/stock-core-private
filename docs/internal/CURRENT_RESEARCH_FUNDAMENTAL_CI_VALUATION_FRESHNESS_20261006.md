# Current research fundamental, CI, and valuation freshness

Milestone: `CURRENT_RESEARCH_FUNDAMENTAL_CI_VALUATION_FRESHNESS_CONVERGENCE_V1`

Authority effect: none. This is a research diagnostic contract. It does not promote
RAW_AS_TRADED or PIT, and it does not emit a recommendation, probability, or target price.

## What was already canonical

Current valuation already separates price, share basis, financial authority, and
provider multiples (`current_valuation_input_authority`, `current_research_valuation_context`,
`current_corporate_event_context`, `current_research_decision_packet`). Those paths
were extended. No parallel valuation engine was added.

The retained 2026-10-06 market-wide valuation artifact
(`operations-review/market-wide-current-valuation-v1-20261006-session20261006`)
reports its own denominator of 1,507 records, not the 1,683 candidate universe:

- official-qualified financial inputs: 13
- provider-research financial inputs, descriptive only: 507
- financial missing: 984
- exact-session price ready: 857
- qualified official shares: 1
- price and share both ready: 0
- P/E research-usable: 5
- P/B, P/S, EV/Sales research-usable: 6 each
- EV/EBITDA research-usable: 0
- sector specialists in that artifact: bank 28, securities 33, insurance 7, finance company 1

Those counts are the retained artifact's coverage. They are not hidden, and this
milestone does not raise them.

## What this contract adds

`current_valuation_denominator_integrity` keeps the provider multiple and, only when
units, currency, share basis, and period permit, computes an arithmetic diagnostic.
A disagreement is `INCONSISTENT_DENOMINATOR`. The provider value is not replaced.

Strict valuation use is quarantined for denominator conflict, pending corporate
actions, unqualified earnings, and specialist methods that are not applicable.
Research presentation of the provider figure remains available except when the
method is `NOT_COMPARABLE`.

Earnings quality emits `NON_RECURRING_COMPONENT_PRESENT_OR_POSSIBLE` when the
retained evidence flags a disposal, unusual provision, one-time item, restatement,
or extraordinary action. It does not invent recurring earnings.

Corporate-event projection copies only qualified dates. It does not infer an
ex-date and does not turn planned issuance into executed shares.

Claim classes are `FACT`, `DATA_WARNING`, `INFERENCE`, `MISSING`, `STALE`,
`PROXY`, and `CONFLICT`. A missing claim blocks only a use that requires that field.
The decision packet includes claim classes only when the caller supplies them, so
existing packet identities stay stable.

The coverage summary takes an explicit universe denominator. Unclassified members
remain visible as no-evidence. Low coverage is not collapsed into a score.

## Forex idea bank

`docs/internal/CROSS_PROJECT_FOREX_IDEA_BANK.md` is
`NON_AUTHORITATIVE_IDEA_BANK / NOT_ROADMAP / NOT_BACKLOG / NO_AUTO_PROMOTION`.
It did not create a roadmap entry.
