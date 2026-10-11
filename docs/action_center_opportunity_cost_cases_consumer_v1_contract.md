# Action Center opportunity-cost cases consumer V1

Milestone `ACTION_CENTER_OPPORTUNITY_COST_CASES_CONSUMER_V1`.
Starting live main `cd486c4f2af41ac6a89dfbb5b6ad3ac3d5d99698`; PR118 COMPLETE,
four closeout CI jobs passed (38095908308), native ON_TRACK, ACTIVE=0/NEXT=0.
Owner directive dated 2026-10-11 selects this one scope under the recorded
`PROGRAM_LEAD_CONTINUATION_AND_STANDING_DELEGATION` (2026-10-10).
Native `--admit-scope` records the exact owner instruction and empty queue;
prior completion/history remain intact. Implementation/validation/commit/safe PR
are authorized; exact-HEAD merge and production activation remain separate gates.

Authority effect NONE. Offline, opt-in, read-only research presentation.
No ordinary Daily call, second Daily entrypoint, provider request, runtime/private
dataset/session write, AI handoff or Dashboard publication. No winner, ranking,
investment decision, new measurement, allocation, sizing, leverage, target,
probability, forecast, cash return or execution authority.

## Feasibility and existing data path

`personal_investment_decision_action_center.build_artifact` owns the existing
private Action Center, including portfolio and narrower capital-rotation sections.
Its retained resolver loads the same-session IID and optionally the private
workbook snapshot through `private_portfolio_context.portfolio_status` and
`portfolio_aware_decision.evaluate_from_retained_artifacts`. The existing
`portfolio_aware_decision.derive_portfolio_state` projects that snapshot into
`portfolio_state/v1`; no holding may be inferred from Action Center discovery,
watchlist membership or a missing portfolio row. Research role is separate.

The existing opportunity-cost `build_integrated_comparison` owns the v2 cases,
IID scenario binding and workbench correlation/overlap. It had no Action Center
consumer at starting main. The IID's valuation summary omits full peer-method
qualification. Its exact `source_artifacts.current_valuation` points to the
evaluated artifact built by `canonical_daily_financial_v2_materialization`;
that artifact retains methods, READY_RESEARCH_ONLY peer detail and basis.
This permits a truthful optional consumer without changing the ordinary pipeline.

## Optional private library boundary

`build_artifact(..., opportunity_cost_input=None)` preserves the default output,
identity, call shape and Markdown. A supplied input adds `opportunity_cost_research`.
Implementation: `stocklookup_core/portfolio/action_center_opportunity_cost.py`;
presentation contract `action_center_opportunity_cost_cases_consumer/v1`.
The existing private Markdown renderer displays the optional section. Neither
the retained resolver nor Owner Daily supplies this argument. No CLI is added.
If only explicit owner state is supplied, the existing portfolio decision section
is not synthesized; Markdown distinguishes the absent decision artifact from
the available owner state in opportunity research.

Input contract `action_center_opportunity_cost_input/v1`:

- `session`: exact Action Center/IID comparison session.
- `research_frames`: explicit unique uppercase tickers, horizon and portfolio role;
  optional thesis ID/IDs and caller-reported thesis status/source. An asserted
  non-UNKNOWN thesis requires a source. No inference of INTACT from fundamentals.
  Optional current returns/dates retain the PR118 workbench fail-closed path.
  Later observations cannot enter an earlier comparison; date alignment grants
  no source/method, causality or PIT authority to caller-supplied research vectors.
- `owner_portfolio_state`: existing explicit `portfolio_state/v1`. The state must
  carry its snapshot identity, canonical as-of date, typed positions and finite
  nonboolean owner facts/policy values. Earlier owner snapshots are explicitly
  stale research context; later dates fail closed. Missing cash/NAV stays unknown.
- `valuation_artifact`: optional complete evaluated
  `current_research_valuation_context/v1` artifact. Its full native content hash
  is verified using the existing materialization identity function and must
  equal the valuation identity consumed by the complete verified IID. A supplied
  session header must match. Canonical evaluated valuation lacks that header:
  the IID binding establishes consumption, not a fabricated observation date.
  Original method/period/share basis, provider/provenance, blockers and limitations
  remain in the private JSON and view. Intrinsic model outputs are not projected.

All input/lens sessions, sources, IID content/decision identities and released
policy v2/conditions pass the existing `bind_integrated_scenarios` validation.
Caller lenses, decisions or unsupported fields cannot replace these projections.
Optional existing Action Center portfolio artifacts must bind the same snapshot
and session. A mismatch fails closed before output.

## Position truth and research cases

Missing, unavailable or unsupported private state produces an explicit unavailable
section with `comparison=null`, never an empty synthetic portfolio. Invalid state
raises; malformed/unresolved quantity stays unresolved. The engine distinguishes:

- `HELD_CONFIRMED`: explicitly confirmed finite positive current quantity.
- `NOT_HELD_CONFIRMED`: explicit closed or confirmed zero-quantity row.
- `CURRENT_POSITION_UNRESOLVED`: omitted ticker or unresolved position.
- `EXCLUDED_INACTIVE`: owner research exclusion; no position case.

Omitted tickers may be reviewed as alternatives with an unresolved holding gap;
an explicitly unresolved position gets no holding/alternative case. Hold/add/trim
require confirmed holdings. Owner limits only narrow. Hold research exposes
structural gaps, reported thesis and independent tactical counter-evidence.

The view presents HOLD_CORE_REVIEW, ADD_CORE_REVIEW, VALUATION_TRIM_REVIEW,
ALTERNATIVE_INVESTMENT_REVIEW, CASH_OPTIONALITY_REVIEW and
INSUFFICIENT_COMPARABLE_EVIDENCE. Cases keep supporting/counter-evidence, gaps,
source fitness, horizon/role/thesis and decision changers. Source invalidation,
currency, temporal limits, financial synthesis and corporate event identities
remain available alongside the cases. A thesis break never becomes valuation trim.
Thesis assertions never gain multi-year structural authority.

The consumer narrows ADD when structural comparability or qualified relative
valuation is missing; it never relabels the reported thesis. Relative labels
need the existing workspace-qualified methods and supporting percentiles;
malformed READY percentile/count/basis claims fail closed. Pairwise strategic
comparability additionally needs matching method basis. COMPARABLE,
PARTIALLY_COMPARABLE and NOT_COMPARABLE remain distinct; side-by-side values,
overlap and finite date-aligned correlation have no winner/superiority.

The original v2 engine and legacy v1 behavior are unchanged. The narrowed
presentation preserves `source_engine_comparison_identity` and gets its own
consumer `comparison_identity`; no modified object claims the engine's identity.
Cash remains facts and uncertainty, with no invented return. Presentation order
is the engine's stable ticker/case order, never investment merit.

## Privacy and acceptance

Opt-in JSON/Markdown writers require the existing private Action Center root or
its descendants; public/other destinations and unsafe session paths fail before
any write. Default legacy writers stay compatible. The caller must not upload
the resulting private artifact. The GitHub repository is PUBLIC despite its
name: only implementation/docs and synthetic tests belong in this PR.

Synthetic acceptance covers position truth, owner gaps/invalidity, all six cases,
independent lenses, thesis-break trim suppression, source/session/hash rejection,
qualified-method gaps, PR118 nonfinite/date guards, default compatibility,
production/public isolation and private output boundaries. Existing deterministic,
consumer and structural suites plus all four hosted jobs are required.
[Acceptance and continuation](internal/ACTION_CENTER_OPPORTUNITY_COST_CONSUMER_ACCEPTANCE_20261011.md).
No future live acceptance is claimed. Production activation requires separate
review; this does not amend the upstream offline-only contract.
