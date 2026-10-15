# Current research priority focus and evidence coherence v1

Status: local implementation contract. No release, push, Daily, provider, or authority promotion.

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

The Integrated Decision root records `source_artifacts.priority_queue`. When that artifact identity differs from the operation's sealed queue, record hashes are not comparable. The report status is `LANE_SELECTION_QUALIFIED_PRIORITY_RECORD_LINEAGE_UNBOUND`. Lane order still comes from the operation queue. Dossiers still use the verified decision, and they say the priority record was not the same object. Embedded tier and entry relevance are still checked. A same-artifact record-hash miss stays a hard mismatch and does not render that dossier.

## Selected architecture

**C. Narrow research-focus projection** over the verified queue and one streaming Integrated Decision pass.

Rejected:

- **A. Extend only the bounded Action Center preview.** The preview is an explicit-ticker renderer. Putting lane discovery and the dossier into its artifact would change the released preview identity.
- **B. A thin adapter that only calls the preview.** The preview keeps full records off the result and sorts tickers. Lane order, queue identity, and one combined overview-plus-dossier pass would still need a second 1.4 GB read or a second decision engine.

The projection keeps full records only for the bounded dossier set. Every other qualified lane member contributes a slim source view from the same verification pass. Full-record retention stays inside the existing selected-payload byte cap. The 1 GiB physical-memory admission floor is unchanged. `artifact_stream.py` and other frozen E4/E5/E6 inputs are not edited.

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
