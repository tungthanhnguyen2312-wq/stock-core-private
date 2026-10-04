# Stock Lookup — Historical Index

Pointer only. The files below hold the **history** of Stock Lookup. They are preserved byte-for-byte
(Phase A of the control-plane simplification did not move, truncate or rewrite any of them) and they
are **deep-reference sources, not default active-state authority**. Do not copy their contents into
prompts or into the active files; search them when a task needs the history of one thing.

Active reading set (read these instead): [AGENTS.md](../AGENTS.md) → [ACTIVE_STATE.md](ACTIVE_STATE.md) →
[CAPABILITIES.md](CAPABILITIES.md) → [AUTHORITY.md](AUTHORITY.md) → [DAILY_PIPELINE.md](DAILY_PIPELINE.md) →
[ROADMAP_CURRENT.md](ROADMAP_CURRENT.md) → only the contract the task names.

## What each legacy source holds

| Source | Holds | Size at Phase A | Treat as |
|---|---|---|---|
| [STATE.md](STATE.md) | Operational narrative, newest section first: dated milestone sections, invariants, runbook fragments, superseded pointers | ~920 KB / ~6,000 lines | history + invariants; **not** current-state authority (its banners can pre-date current facts — see ACTIVE_STATE §6) |
| [DECISIONS.md](DECISIONS.md) | Decision record: rationale, measured evidence and trade-offs per milestone | ~1.0 MB / ~8,700 lines | rationale lookup |
| [ROADMAP.md](ROADMAP.md) | Strategic roadmap and numbered milestone history | ~300 KB / ~1,600 lines | history; use ROADMAP_CURRENT for what is next |
| [ROADMAP_STATE.json](ROADMAP_STATE.json) | **Machine** execution state: current/queued/blocked milestones and git-verified checkpoints (`python tools/stocklookup_roadmap.py`, `--check`, `--can-start ID`) | ~540 KB | **live machine authority for milestone state** — query it with the tool, do not read it whole |
| [internal/](internal/) | Per-milestone acceptance artifacts, closeouts, validation records (~48 files) | — | evidence for one milestone |
| [archive/](archive/) | Older changelogs, July decision archive, manifests | — | history |
| [SYSTEM_MAP.md](SYSTEM_MAP.md) | Navigation map of modules and prior milestones | — | orientation |
| Contracts `docs/*_contract.md` | The controlling contract for each capability | small each | **authoritative** — read the one the task touches |

## Machine consumers of the legacy files (audited in Phase A)

Why Phase A left the giant files untouched. Do not reformat, reorder or delete these when editing legacy files:
- `docs/ROADMAP_STATE.json` — schema `stocklookup_roadmap_execution_state/1.0.0`, milestone IDs and
  `implementation_lineage_head`, checked against git by `tools/stocklookup_roadmap.py --check` (a CI step).
- `tests/test_kbs_trading_value_coverage.py` — scans `STATE.md`, `ROADMAP.md`, `DECISIONS.md` and `AI_RULES.md`
  for forbidden KBS causal-overclaim phrases; any edit to those four files must keep it green.
- `docs/STATE.md` banners are delimited by `<!-- *_CURRENT_START -->` / `<!-- *_CURRENT_END -->`; no code parser
  was found, but milestone-update workflows rely on the convention — keep it.
- `tools/handoff.py` (legacy) expects `- Active phase` / `- Active milestone` / `- Production state` lines in
  `STATE.md` and `- Exit gates:` lines in `ROADMAP.md`. Those lines **no longer exist**, so its test
  (`tests/test_governance_tools.py`) already fails on main; it is not in CI. This index does not repair it.

## How to search history without reading it

```bash
# one milestone or term, with line numbers
git grep -n "MILESTONE_OR_TERM" -- docs/STATE.md docs/DECISIONS.md docs/ROADMAP.md docs/internal
# machine state of a milestone, what is blocked, whether one may start
python tools/stocklookup_roadmap.py
python tools/stocklookup_roadmap.py --can-start MILESTONE_ID
# the contract for a capability
ls docs/*_contract.md
# the newest banners only (top of STATE.md)
sed -n '1,40p' docs/STATE.md
# who changed a line and why
git log -S"phrase" --oneline -- docs/STATE.md
```

Rules: do not recursively scan `operations-review/` (retained evidence, gitignored, huge); read exact
evidence paths only. A task that changes authority, history-sensitive semantics or a parser may inspect
the relevant historical sections in full — a task that does not should not.

## Questions → sources

| Question | Source |
|---|---|
| What is active? | [ACTIVE_STATE.md](ACTIVE_STATE.md) + [CAPABILITIES.md](CAPABILITIES.md) |
| What is authoritative? | [AUTHORITY.md](AUTHORITY.md) + the controlling contract |
| What runs Daily? | [DAILY_PIPELINE.md](DAILY_PIPELINE.md) |
| What happens next? | [ROADMAP_CURRENT.md](ROADMAP_CURRENT.md) |
| What happened historically? | this index → STATE / ROADMAP / DECISIONS / `internal/` / `archive/` |
