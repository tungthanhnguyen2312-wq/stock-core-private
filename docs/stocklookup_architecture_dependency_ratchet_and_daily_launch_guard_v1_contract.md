# Architecture dependency ratchet and Daily launch guard V1

Owner-admitted E0, based on main `6f0c483eed41ca9b3ffdcd2f918ab21138b50124`.
Bootstrap PR122 is released at that commit; all four post-merge jobs succeeded
in run `38126328546`. Native execution state remains `ROADMAP_STATE.json`.
No production activation, analytical authority, successor or E1 admission follows.

## Dependency regression boundary

`tools/check_architecture.py` uses stdlib AST over root Python, `tools/` and
`stocklookup_core/`, without importing application modules or reading evidence.
The existing `config/repository_layout.json` remains the relocation authority;
its 107 entries and compatibility launchers are unchanged.

`config/architecture_dependency_policy.json` defines the initial conservative
development dependency direction: acquisition ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ evidence ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ financial ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ valuation,
evidence ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ tactical, those analytical layers ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ research ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ portfolio ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ decision.
Arrows mean upstream input may be consumed by the downstream layer. Root legacy
orchestration and tools may consume domain packages; domain packages may not add
root/tool dependencies. This is an E0 source regression policy, not evidence,
feature, source or roadmap authority. Existing opposite-direction edges are debt.

The deterministic baseline records modules, unique internal edges, module-load,
function-local/lazy and TYPE_CHECKING contexts, resolved dynamic imports,
unresolved dynamic expressions, violations, eager SCCs and runtime SCCs. Repeated
identical edges are deduplicated; counts differ from the research site inventory.
Eager and runtime cycle edges are compared separately, including new cyclic edges
inside an old SCC. Moving a lazy edge into module-load can introduce an eager
cycle and is rejected. TYPE_CHECKING edges are excluded from runtime cycles.
New prohibited edges and new unresolved dynamic expressions fail the guard.
Grandfathering is regression tolerance, never architectural approval.

This is static coverage, not complete runtime reachability. Literal imports,
relative imports, importlib aliases and literal import-name tuples are resolved.
Module aliases, from-import aliases, plain/annotated callable assignments, constant getattr,
import_module, __import__, spec_from_file_location, SourceFileLoader, run_path and run_module
are classified as internal, external, unresolved or unsupported. Computed targets
fail closed against exact site identities; exec/eval, loader execution and computed
loader attributes, builtin dictionary calls and loader-library wildcard imports
are unsupported and require exact grandfathering. Non-loader
importlib use is not a dependency. Custom wrappers, reflective rebinding and
interprocedural assembly are not proven; E0 is not a Python interpreter. No production import or invocation is attempted to fill that gap.

## Reviewed updates

Schema 2 is a one-time measurement migration from accepted checkpoint
`d2ba70324a5d458091ac54549466a9bec57d6434`, whose prior baseline SHA256 is
`749a59996a4d245ea3056289c5d59f443bf2ca60f7b61fe8dc4217f951772b26`.
`--migrate-baseline-from <that-checkpoint> --write-candidate <scratch-path>` reads
immutable Git blobs only. It retains old exact debt plus newly exposed historical
sites. Ordinary checking verifies its sealed canonical-JSON digest (including in shallow CI)
and rejects baseline changes;
current-source candidate generation cannot silently authorize new debt. The
candidate cannot overwrite the enforced baseline. Any later debt-policy migration
requires explicit review of the anchor, prior digest, analyzer and source diff.
No wildcard site exemption or automatic baseline refresh is permitted.

## Path-launch contract

`config/daily_path_launchers.json` records the research report's 31 resolved
Producer targets, verified against this base: ordinary Daily, legacy CLI,
offline/provider qualification and CI compile paths. These are not 31 ordinary
Daily stages. Unresolved external sibling targets are outside this repository.
`tools/check_daily_launchers.py` checks exact relative file presence, Python
compilation, and backward slices of argv at subprocess dispatch or recognized
local wrappers. Python flags and script position are distinguished; stale lists,
prose and undispatched argv are not proof. All 12 reviewed Python callers also
carry exact AST digests: a changed root, dispatcher, executable or dead branch
cannot reuse a reviewed contract. Complex loops, injected runners, inline imports,
bundle copying and delegated command plans remain explicit bounded contracts,
not claims of resolved runtime reachability. Four shell/CI callers have normalized
source digests (one is an owner instruction, not executable dispatch). Updating a digest requires reviewing actual dispatch, target map
and regression tests; matching a filename alone never authorizes an update.
The check is bounded static protection, not a claim that every branch is active.

Deleting or moving `macro_sync.py` without its canonical root launcher fails
CI. Changing its reviewed launch path also fails. Canonical subprocess argv,
cwd, fail-soft behavior, provider bundle membership, source/transformation
identities and code digests remain byte-identical. No conversion to `python -m`.

## Acceptance and release

Existing layout tests integrate both guards; structural CI also runs adversarial
tests for backward dependencies, eager/lazy cycle promotion, old SCCs, dynamics,
portable parsing and missing/mislocated launchers. Governance and offline Daily
call-shape tests remain required. Report baseline failures separately from E0.
The 2026-10-11 end-to-end owner directive supersedes the earlier one-commit limit:
validated implementation and local closeout commits are authorized. Native
`--complete-local-scope <current-id> --owner-override --checkpoint-at <full-live-HEAD>
--scope-note <owner-directive>` requires ON_TRACK, tracked-clean Git and an empty
queue; it preserves historical JSON and records LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED.
It neither releases main nor admits a successor. Acceptance commands, counts,
environment, exact tested HEAD and JUnit digests are retained with the final report.
No push, PR, merge, Daily, module relocation, evidence rewrite or automatic E1.

Local implementation is COMPLETE, not promoted. [Retained acceptance](internal/E0_LOCAL_ACCEPTANCE_20261011.md).
