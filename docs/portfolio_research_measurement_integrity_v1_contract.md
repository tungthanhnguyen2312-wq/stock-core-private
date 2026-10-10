# Portfolio research measurement integrity V1

Milestone PORTFOLIO_RESEARCH_MEASUREMENT_INTEGRITY_V1. Starting main
1b7c10c9a0f6037b0e289ea48ab0b56d90cc07c9, PR117 exact approved candidate
1a0330d8b217a7e8e17a96328bcaedbdbbe40fba. Four PR jobs/run38060391739 and
four post-merge jobs/run38064845939 SUCCESS. Routine closeout is part of this scope,
not a separate bookkeeping milestone. All prior evidence and authority limits remain.

Owner WEEKEND_PRODUCT_VALUE_CONTINUATION and standing program delegation explicitly
authorize selection, recorded native admission, implementation, offline validation,
local commits and a safe feature PR. One writer in a clean dedicated C: checkout.
Exact-HEAD merge remains Owner-only. No USB drive access, Daily/deploy, private/runtime
write, heavy production data workload, deletion or authority promotion.

## Pre-execution challenge and demonstrated gap

Existing owner: stocklookup_core/portfolio/portfolio_research_decision_workbench.py,
portfolio_research_decision_workbench/v1, consumed by Portfolio Opportunity Cost
v1/v2 through build_workbench. No new workbench, packet, engine or inspection CLI.
Controlling [workbench contract](internal/PORTFOLIO_RESEARCH_DECISION_WORKBENCH_FOUNDATION_20261006.md)
and [opportunity-cost contract](portfolio_opportunity_cost_research_contract.md) remain.

Released-code adversarial fixtures reproduce four consequential investor-facing errors:
strings x/y/z are accepted as verified shared dates; NaN correlation is CURRENT_RESEARCH_ONLY
and comparable=true but fails strict JSON; boolean objective values enter numeric ranking;
conflicting duplicate tickers silently keep the first row, changing concentration/identity
when input order reverses. Malformed numeric returns can also abort unrelated comparisons.
These are synthetic boundary fixtures, not issuer facts or observations of a real portfolio.

Investor outcome: pairwise evidence is either a valid finite calculation on canonical
shared dates or explicitly unusable, with no bad-point deletion/imputation. An explicit
objective cannot rank boolean/nonfinite/malformed measurements. Conflicting observations
cannot silently choose a winner by input order. Opportunity Cost must preserve those
limits without changing held-position, independent lenses, cases or owner constraints.

This improves fitness for a real downstream comparative consumer, rather than adding
another presentation layer or lowering root count. Source/method compatibility, source
authenticity, economic causality, PIT, owner exposure and execution remain separate gates.
Date alignment proves only alignment, never those other properties.

## Smallest coherent implementation

Extend the existing workbench: typed finite/nonboolean return and objective validation;
canonical real ISO dates, unique dates and declared-length alignment; numerical failure
as component-local NOT_COMPARABLE, never NaN/infinity; exact duplicates still collapse
after ticker normalization, conflicting duplicates fail before emitting an identity.
Retain every point or refuse the affected pair; no rows silently filtered to improve it.
Undated valid legacy series remain caller-asserted and unverified. Missing dates never
become verified. Preserve the existing Pearson formula for ordinary valid inputs,
minimum three points, explicit-objective ordering and nonallocation boundary.
Strict output JSON must be finite. Invalid objective measurements retain explicit reasons,
separate from omitted/null/real-zero values; existing missing-member reporting survives.

Tests cover real/invalid/compact/duplicate dates, finite/type failures on shared and
unshared points, no silent pruning, numerical overflow/underflow, constant/short series,
input order, conflicting/exact duplicates, signed/zero objective values, released valid
golden parity and Opportunity Cost integration. Existing v1/v2 source/policy/session,
production call-shape, native/layout/active and all four hosted CI gates are required.

Offline deterministic validation fully establishes these input/numerical defects and
their correction. No future Daily is needed or fabricated. This does not create genuine
2026-10-12 completion or claim new live acceptance. Fiscal mapping, structural economics,
normalization, strict shares/valuation and genuine future outcome maturity stay blocked
by their existing evidence. October9 incident remains closed.
