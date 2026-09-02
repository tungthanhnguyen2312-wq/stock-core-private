# Repository guardrails

## Current direction

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

**Near-term roadmap (exact order, 2026-09-02 core-analytical-product rebaseline):**
`CORE_FUNDAMENTAL_VALUATION_AND_PEER_CONTEXT_V1` = COMPLETE / COHERENT_PARTIAL_BY_RETAINED_EVIDENCE
(checkpoint `5e58d79f69810d6800d1f58244c421acb0e4230f`, closeout `14cc93ccc5cec97c1de865b69eba958f5f18ee7a`)
→ `TACTICAL_MARKET_STRUCTURE_AND_BREAKOUT_V3` = QUEUED_NEXT (not started)
→ `INTEGRATED_INVESTMENT_DECISION_PRODUCT_V1` = QUEUED_AFTER_TACTICAL (not started).
Queued does **not** mean started. Owner authorization is still required to start a
later milestone.

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

`docs/STATE.md` remains the operational cached truth; `docs/ROADMAP.md` owns sequencing;
`docs/DECISIONS.md` records implementation decisions. None of them may silently redefine the
doctrine. If current operational state appears to conflict with the doctrine, surface the conflict
instead of following the most recent technical thread by inertia.

The doctrine also establishes capability-first source routing: DNSE/Livespeed is the primary
market-data direction, FHSC may supply complementary capabilities, and overlapping DNSE/FHSC
claims should be used for cross-validation rather than artificial provider-parity requirements.
Approved agents may use bounded online discovery/extraction when the task permits it, but retained
source evidence—not AI-generated text—is factual authority.

## Default lightweight bootstrap

For a normal bounded implementation milestone:

1. Read this file, [`docs/DATA_FIRST_DOCTRINE.md`](docs/DATA_FIRST_DOCTRINE.md), and
   [`docs/STATE.md`](docs/STATE.md) in full.
2. Read only the roadmap, decision, and rule sections explicitly referenced by `STATE.md` or
   directly required by the named milestone.
3. Read directly relevant code, tests, and data contracts.
4. Do **not** scan all handoffs, all decisions, or the full roadmap by default.

Perform a full authority refresh (`AGENTS.md`, `DATA_FIRST_DOCTRINE.md`, `STATE.md`, `ROADMAP.md`,
`DECISIONS.md`, `AI_RULES.md`, and the current handoff) only when changing architecture, program
priority, governance, or authority; entering a new major program; promoting/demoting a source or
capability; resolving a conflict with/staleness in `STATE.md`; finding contradictory repository
docs; or when the owner explicitly requests a rebaseline/governance audit. A new session, a new
agent, or a normal bounded milestone is not by itself a trigger.

`docs/STATE.md` is the Producer operational entrypoint and cached current truth. Operations
reviews, handoffs, historical roadmaps, and Consumer/Dashboard notes are evidence/reference,
not competing current authority. If a prompt conflicts with `STATE.md`, surface the conflict and
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
and the Producer `STATE.md`; do not reconstruct project truth from chat memory or old handoffs.

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
