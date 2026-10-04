# Repository guardrails

## Reading contract — start here

Normal work reads a **small active set, in this order, completely** (about 100 KB in total):

1. This file (`AGENTS.md`).
2. [`docs/ACTIVE_STATE.md`](docs/ACTIVE_STATE.md) — what is true now: gate, launch conditions, blockers, next action.
3. [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) — every capability's status, contract, authority and blocker.
4. [`docs/AUTHORITY.md`](docs/AUTHORITY.md) — who may speak for what, with the controlling contract.
5. [`docs/DAILY_PIPELINE.md`](docs/DAILY_PIPELINE.md) — what runs Daily, in order.
6. [`docs/ROADMAP_CURRENT.md`](docs/ROADMAP_CURRENT.md) — NOW / NEXT EVIDENCE GATE / AFTER / LATER.
7. Only the specific contract, code and tests the task names (`docs/*_contract.md`, relevant modules).

`docs/STATE.md` (~920 KB), `docs/DECISIONS.md` (~1 MB) and `docs/ROADMAP.md` (~300 KB) are **preserved
history and deep-reference sources, not mandatory full reads and not the default current-state source**.
Search them with `git grep` when a task needs the history of one thing; see
[`docs/HISTORICAL_INDEX.md`](docs/HISTORICAL_INDEX.md). A task that changes authority, history-sensitive
semantics or a machine-parsed file may read the relevant historical sections in full. Do not ignore them
entirely, and never edit them without checking the consumers listed in the index.
`docs/ROADMAP_STATE.json` (~540 KB) is machine state: query it with `python tools/stocklookup_roadmap.py`
rather than reading it whole.

**Authority by domain** (one rule, no ladder and no new authority layer; identical in `docs/ACTIVE_STATE.md`):
- *Milestone execution state* (current / queued / blocked / startable, checkpoint verification):
  `docs/ROADMAP_STATE.json`, queried with `python tools/stocklookup_roadmap.py` (AI_RULES rule 11).
- *Capability semantics and authority limits*: the controlling contract (`docs/*_contract.md`, cited in
  `AUTHORITY.md`) and the code and tests that implement it.
- *Compact current-state docs* (`ACTIVE_STATE`, `CAPABILITIES`, `AUTHORITY`, `DAILY_PIPELINE`,
  `ROADMAP_CURRENT`): maintained navigation views of the two items above. They add **no** authority; if one
  disagrees with the first two, the first two govern and the view is corrected in the same change.
- *Preserved `STATE.md` / `ROADMAP.md` / `DECISIONS.md`*: history, rationale and recorded invariants; not the
  default current-state source. A compact view never overrides a recorded invariant: surface the conflict
  and obtain an explicit owner decision.

| Question | Read |
|---|---|
| What is active? | `ACTIVE_STATE.md` + `CAPABILITIES.md` |
| What is authoritative? | `AUTHORITY.md` + the controlling contract it cites |
| What runs Daily? | `DAILY_PIPELINE.md` |
| What happens next? | `ROADMAP_CURRENT.md` |
| What happened historically? | `HISTORICAL_INDEX.md` → legacy STATE / ROADMAP / DECISIONS / `docs/internal/` |

Chat memory, prior conversation and an agent's own recollection are **never** project authority; if a
prompt conflicts with the rule above or the sources it names, surface the conflict and ask for an explicit
owner override. When you change current state, update `ACTIVE_STATE.md` (and the capability/pipeline files
if they change) in the same change.

## Current direction

*The program doctrine and milestone chain in this section are retained for context; the current
operational state, gate and blockers are in [`docs/ACTIVE_STATE.md`](docs/ACTIVE_STATE.md).*

**CURRENT DEVELOPMENT PRIORITY — CORE ANALYTICAL PRODUCT COMPLETION.** Stock Lookup
optimizes **product-critical analytical completeness** for Current Research / Product
Mode: fundamental context, valuation/peer context, tactical market structure, and
integrated investment decision. This is **PRODUCT-CRITICAL FEATURE EXPANSION ONLY**.
It is not a feature freeze, not a market-wide coverage-expansion program, and not a
specialist-micro-milestone program.

`SUPERSEDED_AS_DEFAULT_WORKFLOW`: ticker-by-ticker qualification before raw ingestion.
Historical ticker cohorts remain golden/regression evidence; they are not the default
development workflow.

`SUPERSEDED_AS_CURRENT_DEVELOPMENT_PRIORITY`: market-wide data expansion as the default
near-term work queue. Coverage, extraction, and specialist work continue only when they
directly block one of the three product milestones below.

**Near-term roadmap (2026-09-02 core-analytical-product rebaseline; updated 2026-09-03):**
`CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1` = COMPLETE
(checkpoint `5e58d79f69810d6800d1f58244c421acb0e4230f`)
→ `TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3` = COMPLETE (checkpoint `01ffdd5`)
→ `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1` = COMPLETE (checkpoint `5227207eec305b8ebfcbba065615e36a27a04b03`)
→ `DAILY_INTEGRATED_DECISION_BRIEF_AND_PROSPECTIVE_FEEDBACK_V1` = COMPLETE (checkpoint `90e3260a5596fa02c210fcc13bb3d1b28d8b329f`)
→ `CANONICAL_DAILY_FINANCIAL_V2_AND_CURRENT_RESEARCH_ENRICHMENT_V1` = COMPLETE
(checkpoint `f3880c589d345ff20e67fd2df84acdaf57f4681e`).
All three original product milestones plus their two owner-authorized follow-ons are
complete; see `docs/ROADMAP_STATE.json` (`python tools/stocklookup_roadmap.py`) for the
authoritative current/queued state. Queued does **not** mean started. Owner authorization
is still required to start a later milestone.

Do **not** open standalone Interest Coverage, Insurance, forensic-accounting,
monetary-basis, VCI-duration, absolute-liquidity, or further specialist
micro-milestones unless they directly block one of those three. No universal scoring
system is required.

The active architecture remains market universe → immutable raw lake →
quality/canonical/semantic/PIT → vectorized feature store → feature-level eligibility
→ strategy → portfolio/risk → AI research → dashboard/human decision. Feature engines
own measurements; the strategy layer owns thresholds and policy. UI/Dashboard stays
frozen until `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1`.

Current Research / Product Mode is separate from Audit / PIT / Exact Mode. Missing
audit-grade authority blocks only the dependent exact use. Provider/research proxies
may be used in Current Research when method, provenance, fitness, and limitations are
explicit. Never invent monetary scale, unit compatibility, PIT authority, or execution
authority. Peer comparisons require comparable metric method/provider/scope. Technical
BOS/CHoCH/VCP are deterministic technical inference, not proof of
institutional/order-flow behavior. Prospective false-negative/false-positive review
is a product capability.

See [`docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md`](docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md)
for the product feature layout. Authority (RAW_AS_TRADED, PIT, liquidity, valuation,
sizing, execution) stays use-case-specific and is never granted merely because a
capability entered a registry or gained a canonical representation — see
`docs/STATE.md` Invariant 6.

**Default sequence (2026-08-21 capability-first rebaseline, still binding):**
`CAPABILITY-FIRST DATA EXPANSION` → `TAXONOMY MAPPING` → `USABILITY` →
`DETERMINISTIC RESEARCH` → `EVIDENCE ACCUMULATION` →
`AUTHORITY HARDENING WHERE REQUIRED`. Route each capability to whichever source(s)
actually expose it; there is no single winning provider to select market-wide.
Provider parity is not a prerequisite for ingestion or for a capability's own
registry presence: a genuinely one-source-only capability (see
`market_capability_taxonomy.py`) must not be blocked merely for lacking a second
source. Overlapping sources are useful for calibration and conflict detection and
are never mandatory. A rebaselined architecture does not by itself reopen a completed
historical milestone, and existing retained evidence is reused, not recreated,
wherever it already answers a question.

## Stable project doctrine

[`docs/DATA_FIRST_DOCTRINE.md`](docs/DATA_FIRST_DOCTRINE.md) is the stable owner doctrine for
Stock Lookup. It defines the non-negotiable direction:

`ACQUIRE BROADLY → PRESERVE RAW → EXTRACT → UNDERSTAND → CANONICALIZE → LABEL FITNESS FOR USE → DETERMINISTIC ANALYSIS → AI RESEARCH → HUMAN DECISION`.

`docs/STATE.md`, `docs/ROADMAP.md` and `docs/DECISIONS.md` are the preserved narrative (recorded
invariants, sequencing history and implementation rationale); current operational state is read through the
Reading contract and its **Authority by domain** rule above. None of them, and no compact current-state doc,
may silently redefine the doctrine. If current operational state appears to conflict with the doctrine, surface the conflict
instead of following the most recent technical thread by inertia.

The doctrine also establishes capability-first source routing: DNSE/Livespeed is the primary
market-data direction, FHSC may supply complementary capabilities, and overlapping DNSE/FHSC
claims should be used for cross-validation rather than artificial provider-parity requirements.
Approved agents may use bounded online discovery/extraction when the task permits it, but retained
source evidence—not AI-generated text—is factual authority.

## Default lightweight bootstrap

For a normal bounded implementation milestone:

1. Read the active set from the **Reading contract** above, in order, in full
   (`AGENTS.md` → `ACTIVE_STATE` → `CAPABILITIES` → `AUTHORITY` → `DAILY_PIPELINE` → `ROADMAP_CURRENT`),
   plus [`docs/DATA_FIRST_DOCTRINE.md`](docs/DATA_FIRST_DOCTRINE.md) when the task touches evidence or authority.
2. Read the specific contract(s), code and tests the milestone names. Read only the `STATE.md` /
   `DECISIONS.md` / `ROADMAP.md` sections explicitly referenced by the active set or directly required.
3. Do **not** read `STATE.md`, `DECISIONS.md` or `ROADMAP.md` in full, and do not scan all handoffs, all
   decisions, or the full roadmap, by default.

Perform a full authority refresh (the active set **plus** the relevant historical sections of `STATE.md`,
`ROADMAP.md`, `DECISIONS.md`, `AI_RULES.md` and the current handoff) only when changing architecture, program
priority, governance, or authority; entering a new major program; promoting/demoting a source or
capability; resolving a conflict with/staleness in the active set; finding contradictory repository
docs; or when the owner explicitly requests a rebaseline/governance audit. A new session, a new
agent, or a normal bounded milestone is not by itself a trigger.

`docs/ACTIVE_STATE.md` is where current-state reading starts; what is authoritative is decided by
**Authority by domain** in the Reading contract above (it is a view, not an authority layer). Operations
reviews, handoffs, historical roadmaps, and Consumer/Dashboard notes are evidence/reference, not competing
current authority. If a prompt conflicts with that rule or the sources it names, surface the conflict and
request an explicit owner override; do not silently change architecture.

## AI context hygiene

To minimize AI context waste and maintain repository cleanliness:

- **No recursive `operations-review/` scan:** Do not recursively scan `operations-review/` by default.
- **Exact evidence paths only:** Read exact evidence paths only when the task requires them.
- **No root helpers:** Never create one-off helper scripts in the repository root.
- **Temporary helpers:** Place temporary helpers outside the repository or in `.stocklookup/scratch/`.
- **Reusable tools:** Reusable runners and developer tools belong in `tools/`.
- **Single production entrypoint:** Do not create a new production entrypoint; `stocklookup.ps1 daily` remains the owner entrypoint.
- **No blanket scans:** Do not scan all handoffs, decisions, or tests for a bounded milestone; use [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) for navigation.
- **Edit over proliferate:** Prefer editing an existing capability module over creating a sibling module unless a distinct contract boundary genuinely exists.

## Repository boundaries

### First-party source-route qualification

Classify each source surface by its explicit role (for example, universe
enumeration, lookup, issuer detail, disclosure index, event calendar,
attachment, or bulk download) before drawing a capability conclusion. Inspect
bounded adjacent first-party surfaces before closing a source family. Retain
broadly supported raw observations with their route provenance, then resolve
and promote each use-case authority fail-closed; a search/autocomplete helper
is never universe-enumeration evidence. Exact upstream parent metadata may
establish provenance only through an exact linkage. A source closure must name
the sibling surfaces checked and the specific evidence that would reopen it.

Codex is the executor. Producer owns raw-source contracts, canonicalization, and artifact
authority. For a cross-repository task, read the directly applicable sibling repository guardrail
and the Producer active set (`docs/ACTIVE_STATE.md` plus the contract the task names); do not reconstruct
project truth from chat memory or old handoffs.

- Work only inside this repository unless the task explicitly names another workspace location.
- Use `STOCK_LOOKUP_RUNTIME_ROOT` for runtime data; do not infer or hard-code a runtime path.
- Keep repository documentation portable, with relative repository links only. Put machine-specific procedures in local operator documentation.
- Do not edit databases, generated artifacts, backups, credentials, or deploy outputs unless explicitly requested.
- Preserve raw observations and provenance when semantics are unknown; mark the affected
  field/feature `UNKNOWN` and fail closed only where that semantic is required.
- Do not add a market-data provider without an explicit owner decision. DNSE/Livespeed is the
  current direction; EODHD remains rejected.
- Do not start a later milestone merely because the current one is ready. Owner authorization is
  still required.
- Detailed agent context, internal validation narratives, and workspace audit records are consolidated in [`docs/internal/`](docs/internal/); historical decision archives reside in [`docs/archive/decisions/`](docs/archive/decisions/).
