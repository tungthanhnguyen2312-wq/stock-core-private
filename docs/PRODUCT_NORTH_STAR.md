# Stock Lookup — Product North Star

> **Authority relationship (read this first).** This document is the durable strategic
> navigation / operating-model reference. It does **not** replace any existing authority
> document and must never be read as doing so:
>
> - [`docs/STATE.md`](STATE.md) — current operational truth (cached, dated, narrative).
> - [`docs/ROADMAP.md`](ROADMAP.md) — sequencing and historical milestone narrative.
> - [`docs/ROADMAP_STATE.json`](ROADMAP_STATE.json) — machine-readable execution state
>   (queried via `python tools/stocklookup_roadmap.py`).
> - [`docs/DECISIONS.md`](DECISIONS.md) — decision history / ADRs.
> - [`docs/DATA_FIRST_DOCTRINE.md`](DATA_FIRST_DOCTRINE.md) — stable owner doctrine.
>
> This file is the **navigation and priority lens** across those documents so a new
> ChatGPT/Codex/Claude session (or a returning one) can recover the project's direction
> without reconstructing it from chat history. Where this file appears to conflict with
> any of the five documents above, surface the conflict — do not silently resolve it in
> either direction. This document itself must not silently redefine doctrine, operational
> state, sequencing, or decision history.
>
> Installed: 2026-09-13, `PRODUCT_NORTH_STAR_AND_GOVERNANCE_REBASELINE_V1`. Ported into the
> governed baseline 2026-09-14 by `CURRENT_OFFICIAL_RESEARCH_UNIVERSE_PRODUCT_CUTOVER_AND_
> RELEASE_INTEGRATION_V1` (it previously lived only on an unmerged local checkpoint); §10's
> "Active universe authority" row and §11's dated coverage figures are from the original
> 2026-09-13 installation and were not rewritten to match this later milestone's numbers -- per
> this document's own authority note above, `docs/STATE.md` is the current operational truth on
> any point where the two appear to disagree.

---

## 1. Mission / North Star

Stock Lookup is a Vietnamese-equity research operating system that converts:

```
qualified evidence
→ deterministic analysis
→ integrated research decision
→ AI explanation/counter-thesis
→ human decision
→ prospective feedback
```

It is **not primarily**:

- a Dashboard project;
- an AI recommendation engine;
- a provider-integration project;
- a universal ranking/scoring engine.

Progress means more of the market becomes:

`retained → readable → understood → canonical → usable → analyzable → explainable → decision-supportive`

This is consistent with, and does not redefine, `docs/DATA_FIRST_DOCTRINE.md`'s stable
direction: `ACQUIRE BROADLY → PRESERVE RAW → EXTRACT → UNDERSTAND → CANONICALIZE → LABEL
FITNESS FOR USE → DETERMINISTIC ANALYSIS → AI RESEARCH → HUMAN DECISION`.

## 2. Target questions per security

Stock Lookup should eventually answer, for any Vietnamese listed equity:

1. What is the business doing?
2. How is it valued versus peers/history?
3. What is price/volume/market structure doing?
4. What events/catalysts/risks can change the thesis?
5. What is the integrated research posture?
6. What confirms the setup?
7. What invalidates it?
8. What evidence is missing/stale/proxy?
9. How does it interact with the owner's private portfolio?
10. What happened after prior comparable decisions?

Research states remain research states, not execution instructions.

## 3. Authority layering

| Layer | Owns |
|---|---|
| **Evidence authority** | Retained qualified source evidence |
| **Numerical authority** | Deterministic Python engines |
| **AI** | Explanation, synthesis, counter-thesis, anomaly discovery, research questions |
| **Human** | Capital allocation, approval, promotion, execution |

AI must never invent:

- financial values;
- ex-dates;
- probabilities;
- target prices;
- source authority;
- unknown semantics.

## 4. Canonical architecture

```
Market Universe
→ Immutable Raw Evidence
→ Quality / Canonical / Temporal Semantics
→ Feature Engines
→ Feature-Level Fitness
→ Strategy / Research Stance
→ Thesis / Scenario
→ Portfolio / Risk
→ AI Research
→ Dashboard / Human
→ Prospective Outcome Feedback
```

Feature engines own measurements. Strategy owns thresholds/policy. Dashboard owns
presentation, not factual authority. See [`docs/SYSTEM_MAP.md`](SYSTEM_MAP.md) for the
current concrete module-level pipeline that implements this architecture.

## 5. What Stock Lookup must do without AI

At minimum, a useful deterministic research product must exist even with AI unavailable:

- completed-session resolution;
- acquisition/reuse;
- raw evidence retention;
- canonicalization;
- market/breadth/sector state;
- tactical engine;
- Financial V2;
- valuation/peer context;
- Corporate Intelligence;
- thesis/counter-thesis inputs;
- security/opportunity decision;
- Daily Brief;
- Workspace;
- Screener;
- prospective snapshot/outcome framework;
- AI handoff package;
- sanitized Dashboard release.

## 6. AI handoff contract

AI gets compact qualified context, including: session; ticker; source identities;
per-axis freshness; per-axis fitness; fundamental context; valuation methods; tactical
context; trigger/invalidation; market/sector context; catalyst/risk; thesis/counter-thesis;
missing evidence; stance; prior-session change; prospective feedback where mature;
authority boundaries.

AI returns: explanation; thesis; counter-thesis; what changed; what confirms; what
invalidates; contradictions; research questions; scenario interpretation.

No new data authority is created by AI output.

## 7. Public Dashboard boundary

Public Dashboard gets sanitized product projections.

**Allowed:** build/session metadata; Workspace; Screener; tactical research;
market/sector context; fundamental/valuation summaries; triggers/invalidation; component
freshness; selected macro presentation; archives/reports.

**Forbidden by default:** private portfolio; credentials; raw provider dumps; local
paths; execution quantity; hidden stale fallback; fabricated probability/target;
machine enums as primary UX.

Freshness must be **component-specific**. Example current truth (2026-09-11 release):

```
Workspace         2026-09-11 CURRENT
Screener          2026-09-11 CURRENT
Tactical table    2026-09-11 CURRENT
Cockpit           2026-09-11 CURRENT

Candle signals    2026-08-25 STALE
Candlestick       2026-08-25 STALE
Sector heatmap    2026-08-25 STALE
```

A stale optional sidecar must not contaminate an independent current component.

## 8. Private portfolio boundary

Private portfolio stack already exists. Keep local/private:

- `portfolio_snapshot/v1`;
- portfolio-aware decision;
- concentration/risk context;
- shortlist;
- owner packet.

Security attractiveness, portfolio suitability, and execution quantity remain three
separate concepts. Do not reopen Portfolio Foundation merely because later work
references portfolio context.

---

## 9. DO NOT RECREATE — capabilities that already exist

Existing capability should be **reused or corrected**, not reopened under a new
milestone name. Before proposing new work in any of these areas, read the current
module(s) and `docs/STATE.md`/`docs/ROADMAP_STATE.json` first:

| Capability | Current module(s) |
|---|---|
| Core Fundamental / Valuation / Peer Context | `market_wide_fundamental_feature_store.py`, `current_valuation_opportunity_integration.py` |
| Tactical market structure | `tactical_behavior_context.py`, `watchlist_tactical_entry_classifier.py` |
| Integrated Investment Decision | `current_valuation_opportunity_integration.py` (`security_decision_context/v1`) |
| Daily Integrated Decision Brief | `daily_integrated_decision_brief.py` |
| Financial V2 current integration | `financial_analysis_engine_v2.py`, `financial_analysis_product_projection.py` |
| Price Basis semantics/fitness | `PRICE_BASIS_SEMANTICS_AND_FEATURE_FITNESS_V1` (2026-09-10) |
| Private portfolio foundation | `portfolio_snapshot/v1` |
| Portfolio-aware decision | `portfolio_aware_decision.py` |
| Private shortlist/owner packet | `PORTFOLIO_AWARE_OPPORTUNITY_SHORTLIST_V1`, `PRIVATE_PORTFOLIO_DECISION_PACKET_V1` |
| Recurring fundamental context | `canonical_current_product_projections.materialize_current_fundamental_feature_store_context()` |
| Recurring tactical behavior | `canonical_current_product_projections.materialize_current_tactical_behavior_context()` |
| Evidence-bound thesis cases | `current_thesis_case_context.py` |
| Current event/catalyst semantics | `current_event_catalyst_classification.py`, `current_official_event_context/v1` |
| Prospective retention/outcome framework | `prospective_decision_retention.py`, `integrated_decision_prospective_feedback.py` |
| Empirical calibration framework | (retrospective replay/validation milestones, 2026-09-10) |
| Daily production environment guard | `DAILY_PRODUCTION_EXECUTION_ENVIRONMENT_GUARD_V1` |
| Canonical current Workspace/Screener projections | `canonical_current_product_projections.py` |
| Dashboard publication pipeline | `dashboard_release_publisher.py`, `publish_dashboard.py` |

## 10. Current blockers — classified by type

| Capability | Current state | Difficulty | Reopen gate / treatment |
|---|---|---|---|
| **RAW_AS_TRADED / historical PIT** | `NOT_PROMOTED` | VERY HIGH / EVIDENCE-LIMITED | Prospective raw retention + official corporate-action timing. Do not reconstruct authority by guess. |
| **Exact liquidity / position sizing** | `BLOCKED / EVIDENCE_CEILING_REACHED` | VERY HIGH / EVIDENCE-LIMITED | Exact ADTV20 remains 0/1683; FHSC 2026-08-06 gap; never-anchored population (877/1683); unresolved tail conflicts (752). Do not retry exhausted evidence merely to appear active. |
| **Active universe authority** | `UNKNOWN` | HIGH | Reopen only with official listing/status source evidence. `CURRENT_OFFICIAL_RESEARCH_UNIVERSE_PRODUCT_CUTOVER_AND_RELEASE_INTEGRATION_V1` (2026-09-14) added exactly that evidence (current official exchange presence + HNX/UPCoM trading/control status) as a **current research scope**, explicitly distinct from active/tradable status per AGENTS.md ("official exchange presence != active/tradable status") -- this row stays `UNKNOWN` by design, not by omission. |
| **Qualified intrinsic/reverse valuation** | `BLOCKED` | HIGH/VERY HIGH | Research scenario valuation with explicit assumptions is conceptually separate from qualified intrinsic authority. |
| **Financial coverage/currentness** | Partial | MODERATE/HIGH | Default path: structured provider-tier evidence first. Official PDFs/OCR = triggered verification asset, not default market-wide scaleout. |
| **Corporate event timing/currentness** | Partial | MODERATE/HIGH | Never infer ex-date from record date or planned execution. |
| **Prospective calibration** | `SAMPLE-LIMITED` | TIME/EVIDENCE | Accumulate genuine T0 sessions rather than repeatedly changing code. |
| **Production acceptance** | `DEFERRED / NOT_FAILED` | TIME-GATED | See `docs/ROADMAP_STATE.json` `DAILY_BRIEF_PRESEAL_CORRECTIVE_NEW_SESSION_PRODUCTION_ACCEPTANCE`; wait for the first canonical completed session strictly after 2026-09-11. |

Do not treat all missing evidence as one problem — decompose by actual semantics
(active listed / temporarily non-trading / suspended / delisted / provider missing /
genuine no-trade / unknown status), especially for coverage gaps under P2 below.

---

## 11. Current priority stack (2026-09-13)

- **P0 — Governance clarity.** This milestone itself.
- **P1-TIME — First-new-session production acceptance.** No code work until a later
  completed market session exists. Strong preference: keep the Producer released code
  baseline unchanged until this acceptance executes.
- **P2 — Current Research coverage quality** (only after production acceptance).
  Primary questions: price available = 952/1683; tactical available = 951/1683.
  Decompose missing population into actual semantics rather than treating it as one
  problem. Official active-universe/listing evidence is strategically important.
- **P3 — Corporate-event + Financial currentness/coverage.** Product-critical gaps only.
- **P4 — Deterministic scenario valuation / thesis quality.** Explicit assumptions. No
  fake probabilities. No authoritative target price from assumption-driven research
  scenarios.
- **P5 — Prospective learning/calibration.** Accumulate real decisions/outcomes.
- **P6 — Exact-authority hardening.** RAW/PIT/liquidity/sizing/execution only when
  genuinely new evidence exists.

## 12. Anti-loop / milestone selection rule

Before naming a new milestone:

**A. Duplicate-capability check.** Search `docs/STATE.md`, `docs/ROADMAP_STATE.json`,
`docs/SYSTEM_MAP.md`, the relevant module/contract, and tests. Ask: *does this
capability already exist?* If yes, use/modify/fix it — do not create another
milestone. (This rule would have prevented the unnecessary recent Price Basis and
Portfolio loops.)

**B. Milestone value test.** A core milestone must answer at least one:
1. acquire useful missing evidence;
2. extract more from retained raw evidence;
3. resolve important semantics;
4. improve fitness-for-use for a real consumer;
5. create a genuinely new deterministic capability.

If all five are NO, do not open the milestone.

**C. Name the consumer.** Must identify: deterministic decision engine; AI handoff;
Dashboard; private portfolio; audit/PIT; prospective feedback. No consumer = low
priority.

**D. Blocker classification.** Classify first as: CODE/CONTRACT; DATA/EVIDENCE;
TIME/MATURATION; EXTERNAL_PROVIDER; PRESENTATION; AUTHORITY/GOVERNANCE. Do not solve an
evidence/time blocker with more code.

**E. One substantial job.** One meaningful milestone should normally include: trace;
implementation; recoverable fixes; targeted regression; retained replay where
applicable; terminal docs/state; one checkpoint. Do not automatically create a second
generic audit, a separate checkpoint job, a confidence replay, or a sibling V2
capability — only when concrete contradictory evidence exists.

A concise, binding version of this rule also lives in [`docs/AI_RULES.md`](AI_RULES.md)
and is referenced from [`AGENTS.md`](../AGENTS.md).
