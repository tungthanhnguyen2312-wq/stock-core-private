# Repository guardrails

## Current direction

**CURRENT DEVELOPMENT PRIORITY — MARKET-WIDE DATA EXPANSION.** Stock Lookup optimizes
**coverage × provenance × reusable dataset contracts** from DNSE/Livespeed, not the number of
individually qualified tickers. The active architecture is market universe → immutable raw lake
→ quality/canonical/semantic/PIT → vectorized feature store → feature-level eligibility →
strategy → portfolio/risk → AI research → dashboard/human decision.

`SUPERSEDED_AS_DEFAULT_WORKFLOW`: ticker-by-ticker qualification before raw ingestion. Historical
ticker cohorts remain golden/regression evidence; they are not the default development workflow.

**Default sequence (2026-08-21 capability-first rebaseline):** `CAPABILITY-FIRST DATA EXPANSION`
→ `TAXONOMY MAPPING` → `USABILITY` → `DETERMINISTIC RESEARCH` → `EVIDENCE ACCUMULATION` →
`AUTHORITY HARDENING WHERE REQUIRED`. Route each capability to whichever source(s) actually
expose it; there is no single winning provider to select market-wide. Provider parity is not a
prerequisite for ingestion or for a capability's own registry presence: a genuinely one-source-only
capability (see `market_capability_taxonomy.py`) must not be blocked merely for lacking a second
source. Overlapping sources are useful for calibration and conflict detection and are never
mandatory. Authority (RAW_AS_TRADED, PIT, liquidity, valuation, sizing, execution) stays
use-case-specific and is never granted merely because a capability entered a registry or gained a
canonical representation — see `docs/STATE.md` Invariant 6. A rebaselined architecture does not by
itself reopen a completed historical milestone, and existing retained evidence is reused, not
recreated, wherever it already answers a question.

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

## Repository boundaries

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
