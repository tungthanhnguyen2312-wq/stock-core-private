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
development dependency direction: acquisition → evidence → financial → valuation,
evidence → tactical, those analytical layers → research → portfolio → decision.
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
Unknown computed names and file loaders are reported for review; arbitrary
exec/eval, custom import wrappers and interprocedural string assembly are not
proven. No production import or invocation is attempted to fill that gap.

## Reviewed updates

Run `python tools/check_architecture.py --write-candidate <scratch-path>` twice
and compare bytes. The tool refuses to overwrite the enforced baseline. Review
the candidate diff with the existing relocation manifest, importer edits, cycle
impact and this policy. Only a deliberate reviewed source change may replace
`config/architecture_dependency_baseline.json`; ordinary CI only checks it.
Baseline updates do not authorize a module move or a successor milestone.

## Path-launch contract

`config/daily_path_launchers.json` records the research report's 31 resolved
Producer targets, verified against this base: ordinary Daily, legacy CLI,
offline/provider qualification and CI compile paths. These are not 31 ordinary
Daily stages. Unresolved external sibling targets are outside this repository.
`tools/check_daily_launchers.py` checks exact relative file presence, Python
compilation, and path-valued AST references in the 12 reviewed Python callers.
Comments and narrative string mentions do not establish a launch contract.
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
Only one validated local checkpoint commit is authorized. No push, PR, merge,
Daily, module relocation, evidence rewrite or automatic E1.
