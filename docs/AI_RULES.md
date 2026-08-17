# AI authority and safety rules

## Bootstrap and authority

1. Codex is the implementation executor. For a normal bounded milestone, read
   [AGENTS.md](../AGENTS.md) and [STATE.md](STATE.md) in full, then only the sections/files
   STATE names or the milestone directly needs, plus relevant code/tests/contracts.
2. Do not scan all handoffs, all decisions, or the full roadmap by default. Full authority
   refresh (AGENTS, STATE, ROADMAP, DECISIONS, AI_RULES, current handoff) is only for
   architecture/program-priority/governance/authority changes, a new major program,
   stale/ambiguous/conflicting state, or an owner-requested rebaseline.
3. `STATE.md` is cached current truth. Do not reconstruct authority from chat memory. If a prompt
   conflicts with state, identify the conflict and obtain explicit owner direction.
4. One session is one substantial bounded milestone. `READY_FOR_NEXT_MILESTONE` does not authorize
   its execution. Commit, push, publish, deploy, or an authority promotion requires explicit
   authorization.

## Market-data doctrine

5. **MARKET-WIDE INGEST-FIRST:** retain immutable, provenance-bearing raw observations before
   semantics are complete. `SUPERSEDED_AS_DEFAULT_WORKFLOW`: whole-ticker qualification before raw
   ingestion. Historical ticker cohorts are golden/regression evidence, not a default work queue.
6. Qualification is field/feature/use-case level. `UNKNOWN` is not rejection: preserve raw data
   and provenance, mark the affected semantic unknown, and fail closed only where it is required.
   Never turn a missing debt field or an unqualified price basis into global ticker rejection.
7. Feature/strategy use must declare accepted feature status, method, quality, provenance,
   freshness, PIT semantics, price/share basis, blockers, lineage, and sector/instrument
   applicability. Python/deterministic engines own formalizable calculations and eligibility.
8. DNSE/Livespeed is the provider direction. Do not add another provider without a new owner
   decision; EODHD is rejected. Do not reopen arbitrary evidence cohorts or ticker-by-ticker
   qualification merely to increase coverage.
9. Price basis, volume basis, current shares, corporate-action timing, and PIT remain persistent
   blockers only for dependent features. Resolve price basis at dataset/provider-contract/
   representative-cohort/corporate-action level; never fabricate or over-generalize a verdict.
10. Do not enable valuation, ranking, recommendations, sizing, execution, or backtesting from
    unqualified inputs. A fallback is a separately named `DERIVED_PROXY`, never an exact canonical
    metric.

## Evidence and semantic discipline

- `documented_verified` is the only tier that can speak for a source. An
  `empirically_deduced` verdict is provider-, field-, ticker-, and window-scoped; preserve its
  methods, alternatives, falsifications, retained artifacts, timestamps, and scope limits.
- To test event-time rewriting, retain a snapshot from before the event. Two post-event snapshots
  measure only post-event stability; re-requesting an old post-event window is not a substitute.
- A ratio constrains only the ratio. Do not invent absolute terms without an independent anchor.
  A cross-provider magnitude anchor carries no composition, adjustment, or authority claim.
- Whole-window claims require `coverage_state = complete`. Otherwise expose
  `observed_rows_only`, covered/excluded sessions, and no imputation. Keep field-omitted,
  present-null, real-zero, malformed, and missing-row states distinct.
- Correlation is an observed association, not a causal explanation. Trace an actual data path
  before writing a consumer/capability contract; record absence when no consumer exists.
- Consumers pass through Producer verdicts. They may narrow a verdict but never widen it or drop
  a required warning.

## AI boundary

AI may research semantics, extract candidate evidence, explain deterministic outputs, identify
counter-theses, and surface anomalies. AI may **not** invent facts, convert `UNKNOWN` to
`QUALIFIED`, fabricate values/target prices/probabilities, infer source semantics from labels, or
override deterministic risk gates. Strategy/portfolio/dashboard output must preserve the source
status and lineage that bounds it.
