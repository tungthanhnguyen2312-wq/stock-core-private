# Preserved agent bootstrap context

Original AGENTS.md current-direction section at bd71cb23013f0175cca22bad7df8632be65e8cad.
Historical reference; native state and current contracts govern execution.
Section SHA256 (LF): 3c6a6c38dac12dfcf34fcdb409f0f4970e77ef6f8a895b96a129d0d1c4ebb25f

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

