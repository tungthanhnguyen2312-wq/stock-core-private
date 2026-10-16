# Current research priority focus and evidence coherence v1

Status: source-review candidate. No merge, Daily, provider, production write, or authority promotion.

## Source ownership

This milestone adds one opt-in consumer. It does not own a decision, score, valuation, or execution result.

| Question | Owner | This milestone |
|---|---|---|
| Lane and tier | `daily_opportunity_decision_queue/v1`, ordered from `current_opportunity_prioritization/v1` | Read, verify, select |
| Canonical posture | `integrated_investment_decision_product/v1` | Read, never recompute |
| Cross-axis coherence | `evaluate_evidence_axis_coherence` | Quote state and reason codes |
| Confirmation and transition | `next_session_decision_brief` labels and the registered tactical artifact | Describe only |
| Numeric trigger display | Action Center conditional-research withholding | Reuse |
| Bounded verification | `bounded_research_preview` streaming checks | Reuse the same checks in one pass |

The opportunity-queue population and the Integrated Decision population are different source denominators. A count difference is not a missing listing and not a failed analysis.

A ticker symbol plus session is not a join. A selected decision is bound only when `source_identities.priority_queue_record_identity` equals the queue record `content_identity`, the queue's opportunity identity equals the prioritization artifact, and that record's `opportunity_record_content_identity` matches the prioritization record.

The operation manifest output `daily_opportunity_decision_queue` is the sealed queue. It owns lane selection, source order, tier, priority reasons, and blocking reasons.

Integrated Decision records a separate `source_artifacts.priority_queue`. That identity is the in-memory queue built before the operation seal, from the retained Level-2 opportunity plus the retained session triage. The queue file itself is not sealed. Rebuilding it read-only with `daily_opportunity_decision_queue.build` reproduces the identity the decision cites. The rebuild is not written back.

For 2026-10-15 both queues are independently qualified for that session:

- Operation output `daily_opportunity_decision_queue:87b14a11c8981b1cc9da9a7bd68aeb48c5dec549a667d470f0719085cceafee5`, from producer opportunity `current_opportunity_prioritization:4b14527b9d8db76c635de4e9f050bfc4fc651626b42c1f4a3fde4a2ebfa44bef`.
- Decision priority context `daily_opportunity_decision_queue:3a83788d3c6a994a84b48466f991be594a572741c9c87b7242135a56c6880b5b`, reproduced from Level-2 opportunity `current_opportunity_prioritization:d0ce38819967dd30b83ff3fc5f33567c85bffee31045fc804f1b4508559c5de3` and triage `full_universe_entry_candidate_triage:f6ab45d9d3a2f87f56441f6a18d7d0e558edd7277fe1d864b2e7ec7d518581bd`. ANT's operation record is `daily_opportunity_decision_record:f3b48df6ae8fee3c9960426f3e06cd6f50013f90396ae1793ecf70cdc7cb3186`. ANT's decision priority record is `daily_opportunity_decision_record:43e3545b25dc3dc6490b59bb53d3c6e07ccbf3376c8661e85cbb6e293f8db55e`.

For 2026-10-14 the same sibling split holds:

- Operation output `daily_opportunity_decision_queue:67f0c0ac08940ee8a3131ea5830f739520a9856fe887b29a6397812fb205d8b7`, from producer opportunity `current_opportunity_prioritization:dc25e6961540e8f92d9cc9d336ea7aa67330500dcb1c519c720ae4d48200899b`.
- Decision priority context `daily_opportunity_decision_queue:3507e5a7893d1cf9dfd416bab5828a2da8dc740cbacf683265a3410d4afb46e5`, reproduced from Level-2 opportunity `current_opportunity_prioritization:2eee523fa9cc8c8128e2c5cafc784d1e299390aa1c7c11be0075cff825808633` and triage `full_universe_entry_candidate_triage:11574983c4eb8793dfe959950bf350630d4e64d507e586d14f7846708e547ab6`.

On each date the two opportunity artifacts cover the same 1,507 tickers and every record `content_identity` differs. Matching tier and `entry_relevant` are separate field checks. They are not a lineage bridge. No synthetic identity is created.

When the two queue artifact identities differ, the report status is `LANE_SELECTION_QUALIFIED_PRIORITY_RECORD_LINEAGE_UNBOUND`. That status means both lenses may be shown and the per-record hashes are not joined. It does not mean the decision queue is missing or unqualified. Lane order still comes from the operation queue. Posture, evidence axes, counter-thesis, and price or financial fitness still come from the verified decision. Previous and current posture labels stay on the transition contract. A queue `PRIORITY_NOW` beside a decision `WAIT_FOR_CONFIRMATION` or `EARLY_WATCH` is coexistence, with `causal` false. It does not create a veto, a confirmation, or an `AVOID`. Missing fundamental evidence stays insufficient, not deteriorating.

Dossier `thesis` lists are decision-owned. Queue priority reasons and blocking reasons stay in `discovery` and are labeled as queue-owned in Markdown. Each deep dossier prints both record identities. A same-artifact record-hash miss stays a hard mismatch and does not render that dossier.

## Selected architecture

**C. Narrow research-focus projection** over the verified queue and one streaming Integrated Decision pass.

Rejected:

- **A. Extend only the bounded Action Center preview.** The preview is an explicit-ticker renderer. Putting lane discovery and the dossier into its artifact would change the released preview identity.
- **B. A thin adapter that only calls the preview.** The preview keeps full records off the result and sorts tickers. Lane order, queue identity, and one combined overview-plus-dossier pass would still need a second 1.4 GB read or a second decision engine.

The projection keeps full records only for the bounded dossier set. Every other qualified lane member contributes a slim source view from the same verification pass. Full-record retention stays inside the existing selected-payload byte cap. The 1 GiB physical-memory admission floor is unchanged. `artifact_stream.py` and other frozen E4/E5/E6 inputs are not edited.

Filesystem qualification, registry resolution, queue verification, and Action Center helper calls live in `tools/evaluate_current_research_priority_focus.py`. `project_research_focus` accepts already verified envelopes, the queue owner's lane order as `source_lanes`, and owner-produced dossier context. The decision module does not import the queue, session-operation, next-session, or Action Center modules. No architecture baseline exception is added.

## Interface

`current_research_priority_focus/v1`

- Session: one completed, registry-qualified operation, plus the previous qualified operation when the registry chain has one.
- Lanes: any `daily_opportunity_decision_queue.LANES` name. Default `EARLY_REVERSAL`, `BASE_ACCUMULATION`, `BREAKOUT`.
- Tiers: `PRIORITY_NOW`, `SETUP_WATCH`, `MONITOR`, `DATA_LIMITED`, `EXCLUDED`. Default `PRIORITY_NOW` and `SETUP_WATCH`.
- `max_tickers`: deep dossiers only, at most the preview selection cap. Each lane keeps its source order. The cap walks the requested lanes in turn so one lane does not consume the whole bound. That rotation is not a cross-lane score.
- `include_tickers`: optional intersection. It cannot add a name the qualified lane source does not contain.
- `qualified_count` sums each requested lane. A ticker in two lanes is counted twice there and once in `unique_qualified_ticker_count`. Overlaps stay labeled; they do not create a second dossier.
- If the operation manifest has no qualified queue or prioritization output, lane selection stops with an evidence blocker. An explicit ticker list may still render dossiers, labeled as explicit preview rather than lane discovery.

Investor-facing evolution codes (`NEW_CANDIDATE`, `IMPROVING_CANDIDATE`, `AWAITING_CONFIRMATION`, `CONFIRMED_SETUP`, `INVALIDATED_OR_WEAKENING`, `NOT_COMPARABLE`, `SOURCE_LABEL_ONLY`) describe existing posture, phase, fundamental-state, and confirmation labels. They are not trading-policy states and they do not rewrite an earlier session.

No fair value, margin of safety, upside, expected return, target price, probability, or BUY/SELL/HOLD vote is created. Market cap remains size context. Market weakness remains context. Missing fundamental evidence is not a negative business signal. A future trigger is not an observed event.

## Outputs

Deterministic JSON and Vietnamese Markdown, with source identifiers retained. The runner writes only a new directory outside the source tree and the retained evidence root. It does not write runtime evidence.
