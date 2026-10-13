# Repository guardrails

## Reading contract — start here

Ordinary work runs `python tools/stocklookup_roadmap.py --check --json`, then opens only the compact file the task table names. The navigation set remains, in this order:

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

Core analytical product completion remains the priority. The native roadmap supplies
current/queued state; completed programs are not reopened and queued work never starts
without Owner authorization. Historical completions and supersessions are preserved in
[the original direction section](docs/archive/agent_bootstrap_context_20261014.md), outside ordinary bootstrap.

The architecture remains market universe → immutable raw lake → canonical/semantic/PIT →
feature-level measurements and eligibility → strategy policy → portfolio/risk → AI research
and human decision. Feature engines own measurements; strategy owns thresholds and policy.
See [the product feature spec](docs/ANALYTICS_AND_DECISION_FEATURE_SPEC.md).

Current Research is separate from Audit/PIT/Exact Mode. Missing audit authority blocks the
dependent exact use. Research proxies retain method, provenance, fitness and limitations;
never infer currency/scale, compatible units, PIT or execution authority. Peer methods/scopes
must be comparable; technical structure is deterministic inference, not institutional-flow proof.
Do not open specialist micro-milestones unless they directly block the core analytical product.

Capability-first acquisition, preserved raw evidence, and use-scoped qualification remain
binding. Provider parity is optional; retain existing evidence and route each capability to
sources that actually expose it. The doctrine below governs; no universal scoring system
or independent authority layer is introduced.

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

1. Run `python tools/stocklookup_roadmap.py --check --json`; when an Owner-designated coordinator exists, pass its exact `--state-file` and your `--repo`. Copied state grants no lane admission. `GIT_NOT_CHECKED` is not a live Git pass.
2. Read the authority section of this file. Open only the compact file the task table names.
   Read [`docs/DATA_FIRST_DOCTRINE.md`](docs/DATA_FIRST_DOCTRINE.md) when the task touches evidence or authority.
3. Open `STATE.md`, `DECISIONS.md`, or `ROADMAP.md` only for a heading the JSON or the task names.
   `python tools/handoff.py` skips those files; `--historical` reads them.
4. Do **not** read `STATE.md`, `DECISIONS.md` or `ROADMAP.md` in full, and do not scan all handoffs, all
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
- **Source placement:** New implementation belongs in `stocklookup_core/`, reusable tools in `tools/`; no root helpers. CI enforces `config/repository_layout.json`; root exceptions need a reviewed compatibility reason.
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
