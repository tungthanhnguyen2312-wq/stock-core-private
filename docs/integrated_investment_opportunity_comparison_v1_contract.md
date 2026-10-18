# Integrated investment opportunity comparison V1 — contract

Milestone `INTEGRATED_INVESTMENT_OPPORTUNITY_COMPARISON_V1`, Owner-directed 2026-10-18,
from verified `a12517d3` (sector-relative resilience closed). Started by Codex and
completed by Claude Code as lead executor after Codex's quota ran out. Local only.

## Product

An explicit request for 2–5 unique uppercase tickers from one research session gets an
evidence-linked comparison of investment opportunities. It covers six areas:

- **Valuation and compatible peers:** research P/B, peer percentile, cohort, and the divergence finding.
- **Financial strength:** deterioration and recovery from the existing multi-period trajectories.
- **Sector-relative context:** the existing resilience assessment.
- **Technical structure and timing:** existing triggers and invalidations, with machine-evaluability.
- **Liquidity:** the existing research liquidity dimension. Execution capacity stays BLOCKED.
- **Downside and conflict:** bull, base and bear cases from the existing scenario binder, plus counter-thesis and material uncertainties.

Owner: `stocklookup_core/research/evidence_aware_candidate_comparison.py`, in the
existing shortlist-comparison module (`mode=INTEGRATED_CURRENT_RESEARCH`). It computes
no new measurements. Profiles quote the verified Integrated Decision record. Each finding
code is a deterministic conjunction of existing assessments, explained in
`INTEGRATED_EXPLANATIONS`:

- Discount with deterioration, which is a value-trap check.
- Discount with a resilience counter-thesis.
- Financial strength without fresh entry confirmation.
- A qualified entry condition, which can carry financial counterevidence.
- Weakness shared with the retained sector sample.
- An observed adverse structure, which sets the downside condition.
- Unknown timing, or unknown qualified valuation-versus-financial evidence.

Pairwise numerical axes are published only when the existing peer owner's
source/accounting signature matches. For P/B that means the same sector key, method,
period, scope, share basis and monetary basis. For a financial ratio it means the same
comparability basis, periods and peer members. Otherwise the pair is
`INDEPENDENT_RESEARCH_CONTEXT_ONLY` and each exclusion reason is listed. Pairs also show
contrasts in conditions. There is no winner, score, ranking, probability, target price,
return estimate, sizing or execution authority. Every profile has `is_actionable=false`.
The comparison never assumes a portfolio or holdings.

## Boundaries and identity

- The request accepts only `tickers` and `research_session`. Anything else is refused:
  bad counts, duplicates, lowercase or unknown names, a mixed session, or an unverified
  Integrated Decision.
- The source is verified once through the existing
  `current_evidence_bound_scenario.bind_integrated_scenarios`. The composition root injects
  it, so the core module takes no backward dependency (architecture ratchet).
- The binder's output is re-checked against the source. The checks cover identity,
  session, policy v2, ticker set and per-record decision identity.
- `comparison_identity` and `output_identity` are content hashes.
  `verified_integrated_comparison` re-verifies them before AI and Markdown delivery.
  The Workspace embeds only a pre-built comparison whose identity, source and scope verify.

## Delivery (all opt-in and additive; the default outputs do not change)

| Surface | Entry |
|---|---|
| Action Center | `python stocklookup.py action-center --compare HPG,FPT,PNJ`. It reads only retained artifacts. The Markdown gains a "Selected investment opportunity research" section. The console reports only `selected_opportunity_comparison_status` and never names tickers. Owner research exclusions are refused. |
| Research packet | `current_research_decision_packet.build_artifact(..., opportunity_comparison_request=)`. It must stay within the packet scope. |
| Workspace | `investment_decision_workspace_projection.build_artifacts(..., selected_opportunity_comparison=)` |
| AI delivery | `ai_research_session_delivery.build_delivery(..., opportunity_comparison_request=)`. The comparison appears as `selected_opportunity_comparison` in the primary bundle. |

The Daily pipeline does not change, and Daily is not invoked. The launcher contract hash
for `stocklookup.py` was updated only for the opt-in `--compare` argument.

## Retained acceptance (2026-10-16, isolated, read-only)

- The completed sector-relative replay reproduced its engine and divergence identities.
  Its 14 input hashes, 1,683 issuers and 337/317 cohorts were unchanged.
- The full-source research Integrated Decision was rebuilt from the session's retained
  technical, tactical, liquidity, corporate and market artifacts plus the research valuation derivative.
- The retained entity-aware operational-fundamental context was omitted. It is bound to the
  retained financial-product identity, not to the derivative, and was refused fail-closed.
- Compared with the retained Daily product, trigger, invalidation and evidence currency
  are equal for 1,683/1,683 issuers. Posture is equal for 1,675.
- The 8 posture differences are all banks, securities and insurance issuers (BHI, EIB, HAC,
  PGI, PHS, PVI, TVB, UPS). They come from that omitted entity-aware input. This capability
  does not change any posture.
- Four real groups passed the packet, Action Center, AI projection and Markdown checks:
  DL1/ITC/NO1, PAN/AAA, HPG/FPT/PNJ/VNM/MWG and VCB/HPG.
- Retained input hashes were unchanged.

Representative 2026-10-16 research findings:

- **DL1:** P/B 0.346, peer percentile 0.08. It has a resilience counter-thesis: cash/assets
  is recovering against weakening peers. The existing policy is AVOID / BEARISH_STRUCTURE_ADVERSE,
  so the observed adverse structure governs the downside.
- **ITC:** P/B 0.307. The discount comes with persistent, company-specific leverage
  deterioration (a value-trap check). Its pivot trigger fired, but participation contradicts
  the entry, so the bull case is not admitted.
- **NO1:** the discount comes with deterioration that is shared with its sector sample.
- **DL1 and NO1** were the only pair with a fully qualified numerical comparison: P/B,
  cash/assets, debt/assets and debt/equity on the same sector basis.

## Known limits

- Numerical pairwise axes need same-sector, same-basis peers. Only 1 of the 15 accepted
  pairs qualified; cross-sector selections stay independent-context-only by design.
- Margin peer comparisons are still UNKNOWN upstream.
- The companion JSON is about 400 KB per security, because it carries full
  financial-measure provenance. The Markdown is about 4 KB per security.
- Live use needs a Daily whose Integrated Decision carries the divergence, multi-period and
  sector-relative fields. That requires releasing the predecessor capabilities. Push, merge,
  release and promotion stay behind their Owner gates.
