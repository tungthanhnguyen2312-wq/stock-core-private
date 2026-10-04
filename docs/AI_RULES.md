# AI authority and safety rules

## Bootstrap and authority

1. Codex is the implementation executor. For a normal bounded milestone, read the active set in
   [AGENTS.md](../AGENTS.md) "Reading contract" in full (AGENTS, [ACTIVE_STATE.md](ACTIVE_STATE.md),
   [CAPABILITIES.md](CAPABILITIES.md), [AUTHORITY.md](AUTHORITY.md), [DAILY_PIPELINE.md](DAILY_PIPELINE.md),
   [ROADMAP_CURRENT.md](ROADMAP_CURRENT.md)), then only the contracts/sections/files the milestone directly
   needs, plus relevant code/tests. `STATE.md`, `DECISIONS.md` and `ROADMAP.md` are preserved history, not
   mandatory full reads ([HISTORICAL_INDEX.md](HISTORICAL_INDEX.md)).
2. Do not scan all handoffs, all decisions, or the full roadmap by default. Full authority
   refresh (the active set plus the relevant historical sections of STATE, ROADMAP, DECISIONS, AI_RULES and
   the current handoff) is only for architecture/program-priority/governance/authority changes, a new major
   program, stale/ambiguous/conflicting state, or an owner-requested rebaseline.
3. **Authority by domain** (the same rule as in [AGENTS.md](../AGENTS.md) "Reading contract" and
   [ACTIVE_STATE.md](ACTIVE_STATE.md); no new authority layer): milestone execution state is
   `ROADMAP_STATE.json` queried with its tool (rule 11); capability semantics are the controlling contract and
   its code/tests; the compact current-state docs are navigation views that add no authority and yield to those
   two; `STATE.md` / `ROADMAP.md` / `DECISIONS.md` are preserved history, rationale and recorded invariants,
   not the default current-state source. Do not reconstruct authority from chat memory. If a prompt
   conflicts with state, identify the conflict and obtain explicit owner direction.
4. One session is one substantial bounded milestone. `READY_FOR_NEXT_MILESTONE` does not authorize
   its execution. Commit, push, publish, deploy, or an authority promotion requires explicit
   authorization.

4a. `docs/NORTH_STAR.md` is strategic product/program intent, not execution authority. Read it only
    for architecture, program-priority, product-roadmap, or owner rebaseline work. Do not load or
    paste it into normal bounded milestone prompts. Milestone execution state is governed by
    `ROADMAP_STATE.json` and capability semantics by the controlling contracts (rule 3); `STATE.md`,
    `ROADMAP.md` and `DECISIONS.md` remain preserved history, rationale and recorded invariants.
    `NORTH_STAR.md` never overrides any of them or this file. Analytical reference frameworks it names (for example CFA/CMA-style
    concepts) guide method design only and are never an authority layer, engine or score.

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

- Separate source discovery from authority promotion: retain first-party raw
  data whenever its route contract supports acquisition, then qualify each
  identity/semantic/use-case independently. Search helpers are `LOOKUP`, not
  `UNIVERSE_ENUMERATION`; terminal source conclusions must record the adjacent
  source surfaces checked and a concrete reopening gate.

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

## Roadmap execution authority

11. `docs/ROADMAP_STATE.json` is the machine-readable roadmap EXECUTION-STATE authority
    (current/active/next/blocked/deferred/superseded milestone sequencing and Git-checkpoint
    verification), queried via `python tools/stocklookup_roadmap.py` (`--check`,
    `--can-start MILESTONE_ID`). No new roadmap milestone may start unless it reports
    NEXT/ALLOWED, except an explicit, recorded owner override -- never inferred from a Git
    commit, a completed dependency alone, or an agent's own judgment that a milestone is ready.
    It governs milestone execution state only; it does not restate or override the technical content, rationale
    or recorded invariants of `docs/ROADMAP.md`/`docs/STATE.md`/`docs/DECISIONS.md`.
