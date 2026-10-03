# Thesis Evidence Matrix and Conflict Engine — offline Stage 1

`THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_1` is an owner-authorized
offline, deterministic, non-voting evidence organizer from main
`ac50ef09cc2c42b4aa6cd83cc114696269cf2f5d`. Authority effect is
`NONE / OFFLINE_DETERMINISTIC_THESIS_ORGANIZATION_ONLY`.

The graph is source products → versioned adapters → `evidence_item/v1` →
correlation groups → axis reducers → separate investor lenses → conflicts →
quality explanations/counter-thesis/condition registers → decision card.
Producers and action policy are unchanged. Nothing imports Stage 1 from Daily,
Dashboard, production handoff, CurrentResearch construction or T0 writing.
Stage 2 production integration requires its own owner authorization.

## Contracts and provenance

`thesis_evidence_contract.py` owns `evidence_item/v1`, closed states, identity,
schema, typed facts, forbidden-field checks and verified snapshot bindings.
`thesis_evidence_adapters.py` owns `thesis_adapter_registry/v1` and source adapters.
`thesis_evidence_matrix.py` owns `thesis_evidence_matrix/v1`, semantic reducers,
conflicts and `offline_thesis_decision_card/v1`. One streamed
`thesis_evidence_matrix_session/v1` NDJSON artifact contains a source-bound header
and 1,683 individually identified records. Full source payloads are never embedded.

Each item includes ticker/session, source contract/version/identity/pointer,
axis/sub-axis, per-lens role, state/unknown class, reasons/blockers, knowledge stage,
horizon, correlation/canonical/common-cause keys, freshness, basis, authority ceiling,
fact/direction fitness, source-owned relations, condition pointers, coverage,
materiality and small factual values. Numbers require exact semantic, unit,
fitness and source pointer. No materiality inference is introduced: absent source
materiality is `UNASSESSED`.

States: SUPPORTS, OPPOSES, NEUTRAL, MIXED, UNKNOWN, NOT_APPLICABLE. Roles:
PRIMARY, SECONDARY, CONTEXT. Unknown classes: MISSING, IMMATURE, UNQUALIFIED,
STALE, POLICY_NOT_AUTHORIZED, PRIMARY_EVIDENCE_MISSING, CONTEXT_ONLY,
HIGHER_TIMEFRAME_UNKNOWN, UNRESOLVED, AUTHORITY_LIMITED.

Unknown enum values/versions/methods fail explicitly. Source reason/blocker strings
pass through as explanations; they are not interpreted as new directional rules.
The exact registry and observed vocabulary distributions are retained in the
[single acceptance](internal/THESIS_EVIDENCE_MATRIX_STAGE_1_ACCEPTANCE.json).
Tests bind registry vocabularies to standing Producer declarations.

Recursive checks reject score, weight, confidence, probability, rank, rating,
conviction, target, priority_score and aliases, including camelCase/nested forms
and judgment names smuggled inside factual metadata. Unknown item schema fields
are rejected. There is no overall verdict, universal numerical measure or second
research action posture.

## Bounded source reconciliation and adapter policy

Only the current Integrated Decision axes, standing Fundamental/Valuation,
market/sector, portfolio/liquidity, legacy participation and existing conditions
were reconciled. No unrelated producer audit or producer modification is required.

| Input | Exact offline interpretation |
|---|---|
| FUNDAMENTAL synthesis | Current directional IMPROVING/TURNAROUND → SUPPORTS; DETERIORATING → OPPOSES; STABLE → NEUTRAL; MIXED → MIXED. Availability separately gates stale/absent/non-directional/entity-inapplicable evidence. No new financial thresholds. |
| VALUATION peer state | Source CHEAP/EXPENSIVE/MID_RANGE → SUPPORTS/OPPOSES/NEUTRAL, only with standing usable fitness and current price evidence. No intrinsic value or target is derived. |
| MARKET_SECTOR | Qualified exact-session BROAD_PARTICIPATION/DETERIORATING_BREADTH → SUPPORTS/OPPOSES; narrow/mixed breadth → NEUTRAL. Sector LEADING/WEAKENING/MIXED → SUPPORTS/OPPOSES/NEUTRAL only with the standing AVAILABLE sector scope. Cohort denominators stay explicit. |
| PORTFOLIO_FIT and liquidity | Facts, coverage and blockers only; neither changes the underlying thesis. Unknown private portfolio is never treated as not held. |
| Legacy PARTICIPATION_CONFIRMATION | Readable closed vocabulary, CONTEXT only. It adds no independent vote beside V2 participation. |
| CORPORATE_FORWARD | Dormant directional policy. Existing event/catalyst descriptions cannot establish a new forward directional contract. |

Technical dispatch verifies V1/V2 through the released dispatcher, then uses the
neutral relationship view. Qualified fresh trend, clean swing and confirmed setup
semantics map direction; equal/expanding/contracting swings and unconfirmed repair
remain neutral/unknown as appropriate. Trend, swings and setup share one close-series
cause per timeframe. Morphology and volatility remain CONTEXT. Selected levels/ranges
have no newly authorized polarity. Technical native-volume copies are CONTEXT and
share canonical/common-cause keys with Volume/Flow.

Stale or unqualified technical evidence is direction-ineligible. RAW multi-bar
direction requires explicit comparable authority; absent that proof it is
UNKNOWN/AUTHORITY_LIMITED. RETROSPECTIVE_ADJUSTED can describe CURRENT_RESEARCH_VIEW
only. V1-derived bridge semantics remain POST. October 2 V2 inputs retain their
`REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE` labels.

Volume/Flow V2 policy is `FACTS_ONLY`. Qualified exact zero net VALUE is NEUTRAL.
Qualified non-zero foreign flow is UNKNOWN/POLICY_NOT_AUTHORIZED with
`facts_present=true`, irrespective of sign. Outside cohort is UNKNOWN/MISSING;
immature windows are UNKNOWN/IMMATURE; unqualified participants are
UNKNOWN/UNQUALIFIED. Native volume and trajectories carry factual context, no
direction. Qualified values retain VND/ratio/count units and exact pointers.

The source price×flow owner remains `flow_price_divergence_shadow/v1`; the
structure×participation owner remains Volume/Flow V2. Matrix copies their
annotations by identity/pointer and never recalculates either relationship.
An available owner-produced price-flow relationship is a separate neutral context
item, allowing its already-qualified divergence annotation without converting
foreign-flow sign into thesis polarity.

## Correlation, axes and lenses

One semantic representative exists per correlation group × lens × knowledge stage.
Nested windows and copied native volume cannot add votes. A group with eligible
members of both directions is MIXED; no member has hidden precedence. Exact duplicate
inputs and input order leave the complete matrix unchanged. Volume/Flow owns the
canonical participation group; Technical copies remain visible corroborating context.

Axes are TECHNICAL, VOLUME, PARTICIPANT_FLOW, FUNDAMENTAL, VALUATION,
CORPORATE_FORWARD, MACRO_SECTOR, LIQUIDITY_PORTFOLIO, EVIDENCE_QUALITY. Stable source
axis names are recorded in the registry; each normalized mapping is explicit.

Reducers operate on eligible PRIMARY groups. All supporting/opposing/neutral groups
reduce to their state; opposite directions or a mixed primary group produce MIXED.
Directional plus neutral retains direction with a qualifier. Unknown primary groups
stay visible and never become opposing. Only SECONDARY gives
UNKNOWN/PRIMARY_EVIDENCE_MISSING; only CONTEXT gives UNKNOWN/CONTEXT_ONLY.
Required unavailable higher timeframe gives UNKNOWN/HIGHER_TIMEFRAME_UNKNOWN.
All inapplicable primary evidence stays NOT_APPLICABLE. There is no signal arithmetic.

LONG_TERM_INVESTOR anchors FUNDAMENTAL and uses FUNDAMENTAL, VALUATION and qualified
1W/1M TECHNICAL. 1D technical, macro/sector, volume, participants and portfolio are
context. SHORT_TERM_INVESTOR anchors 1D TECHNICAL and adds MACRO_SECTOR only where its
standing semantics qualify; the other axes remain context.

An unknown/inapplicable anchor yields INSUFFICIENT_EVIDENCE. Mixed decision evidence
or known opposite decision directions yield CONTESTED. An opposing anchor without
opposite support yields ADVERSE. A supporting anchor with all required decision axes
supporting/neutral yields SUPPORTIVE. Otherwise the lens is NOT_CONFIRMED.
LONG SUPPORTIVE with SHORT NOT_CONFIRMED is a normal independent lens outcome.

## Conflicts and explanation

Active deterministic predicates cover technical intra-timeframe disagreement;
1W/1M disagreement within LONG; technical/fundamental and fundamental/valuation
opposition within their decision lens; standing price-flow divergence;
technical/macro-sector opposition within SHORT; explicit horizon misbinding;
freshness inconsistency for the same canonical evidence/stage; requested-use versus
authority mismatch; and known portfolio constraint versus a supportive thesis.

Metadata anomalies require known comparable facts. UNKNOWN never emits a conflict.
Ordinary 1D versus W/M horizon separation never emits a divergence conflict.
Forward-expectation conflicts remain dormant. Price-flow predicates read only
qualified owner annotations. Cross-stage opposing groups produce CURRENT_RESEARCH
annotations only; they cannot change the T0 view.

Quality explains source authority, temporal/freshness/basis, coverage, missing
denominators, stage and source conflict; its axis remains explanatory context.
Each lens counter-thesis references exact eligible opposing items, mixed groups,
state-changing conflicts and missing/unverified evidence. Missing evidence is
never listed as opposing evidence.

Five registers expose thesis confirmation, setup confirmation, thesis invalidation,
setup invalidation and evidence staleness. Existing serialized structural and
watchlist conditions are referenced exactly by source decision, pointer, version,
identity and status. No new trigger/operator/level is computed. Absent thesis
conditions remain UNKNOWN.

The card has HEADER, MARKET / SECTOR CONTEXT, LONG TERM, SHORT TERM, CONFLICTS,
EVIDENCE QUALITY and ACTION SUPPORT REFERENCE. Lens summaries include axis states
and exact group/counter-thesis references. The final section contains only the
existing decision identity/posture and `second_posture=false`.

## Knowledge separation, acceptance and release

T0_THESIS_VIEW requires full existing snapshot verification plus exact ticker,
session and source identity binding. A claimed stage or ticker/session match is
insufficient. Retrospective basis and V1-derived concepts never enter T0. Derived
Volume/Flow products that were not themselves retained are conservatively POST.
CURRENT_RESEARCH_VIEW may include both stages with explicit annotations. Neither
view advances the real completed-capture clock or writes a sidecar/snapshot.

`tools/run_thesis_evidence_matrix_acceptance.py` reads exact explicit source/runtime
roots and released October 2 V2 diagnostic artifacts. Each source is parsed once;
JSON members are bounded to 16 MiB. It verifies source identities, all 1,683
decision identities, exact input non-mutation, complete record replay/dedup/order
invariance, all final public matrix verifiers and historical T0/PIT byte hashes.
Outputs are separate scratch/session evidence and one portable acceptance.
Network/provider imports and transports are guarded; Daily and publication are absent.

Acceptance reports axis/lens states by view, item and axis unknown classes, roles,
materiality, factual coverage, correlation folds, conflict counts, quality blockers,
foreign cohort maturity and representative cards. Cases use first ticker per
state-pair combination in sorted source order, never investment outcomes.
Universal contested/mixed, nearly universal short NOT_CONFIRMED and conflict
explosion are semantic warnings; correctness violations fail acceptance.

Focused tests, affected standing Producer regressions, all four exact-candidate
CI jobs and all four merged-main jobs gate release. FIRST_REAL_POST_RELEASE_CAPTURE
acceptance remains pending. The exact successor is
`THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_2_PRODUCTION_INTEGRATION`;
it is not started automatically.
