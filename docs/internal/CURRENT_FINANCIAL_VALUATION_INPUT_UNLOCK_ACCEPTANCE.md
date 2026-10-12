# Current financial valuation input unlock — local acceptance

Release input: `288208a6d94b8933bc4d1badfe1e6d27411d3a4f`.
Authority effect NONE. No Daily, session replay, runtime write or source acquisition.

Bounded reads verified the native content digests of the October 12 raw valuation
and evaluated valuation artifacts. The full evaluated cohort is 1,683; raw lane
1,507. The Financial V2 index reports 1,476 available and 207 absent product rows;
that large artifact's full digest was not reverified. Its unrelated peer member
exceeds the existing bounded-reader limit, which was preserved. Ten of 27 retained
official ingress fields already pass the common valuation-use admission; six are
the income/equity denominators consumed by this change. No source promotion.

| Method on the same evaluated cohort | Before | Candidate | Delta |
|---|---:|---:|---:|
| P/E_REPORTED_PERIOD | 0 | 2 | +2 |
| P/S_REPORTED_PERIOD | 0 | 2 | +2 |
| P/B_OFFICIAL_RESEARCH | 0 | 2 | +2 |
| P/B_CURRENT_RESEARCH | 768 | 768 | 0 |
| EV/EBITDA_CALC_READY | 51 | 51 | 0 |
| Ordinary P/E / P/B / P/S / EV-Sales | 5 / 6 / 6 / 6 | unchanged | 0 |
| Market cap | 864 | 864 | 0 |

PNJ and VRE gain reported-H1 income/sales ratios; QNS and VRE gain official-H1
equity research P/B. H1 ratios are explicitly not annual or TTM; equity is an
instant. Original normalized values, display scales, document/citation hashes,
bounds, knowledge cutoff and price/share inputs survive the existing context,
Decision Fitness, Workspace and AI-card path. P3-F remains the numerical owner;
independent Decimal calculations corroborate all six real-input ratios.

Existing numerical methods and Decision Fitness state counts are unchanged:
769 AVAILABLE, 154 PARTIAL, 746 BLOCKED, 14 NON_APPLICABLE. The improvement is six
new computations from already-admitted evidence, not six newly researched issuers,
new evidence coverage, or a rewritten production session. Strict shares remain
zero. Issued shares remain restricted research proxies; annual/TTM/proxy methods
and existing relative-label policy are preserved.

Ceilings: historical-context-only annual rows and USD context are inadmissible
for these inputs; current common-share continuity remains missing; sector-specific
bank/securities identities cannot be aliased to corporate fields; exact EBITDA and
TTM monetary-basis gaps remain. Legacy million-unit values with ambiguous value
representation are not multiplied by guesswork or projected from the shadow lane.
No source retrieval was necessary. Full before/after traces stay in the external
milestone report; no retained source payload is copied into the repository.

Validation: source/scale/scope/bounds/cutoff/conflict/numerator/sector adversaries,
old-method parity, independent real-input numerics and consumer transport; focused
financial/share/valuation/official evidence tests; frozen V1/V2, E0–E6, root V1–V3
and offline production import/call-shape regressions. The new test is part of the
existing focused CI selection; its workflow pin retains the exact normalized hash.
External HANDOFF records exact group results, remaining CI state and checkpoint.
