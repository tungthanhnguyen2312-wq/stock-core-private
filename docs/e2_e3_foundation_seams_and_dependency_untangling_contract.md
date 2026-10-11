# E2/E3 foundation seams and dependency untangling

Explicit Owner admission: attachment 8d6cc579-cea3-4867-a035-cf3c602aa479, 2026-10-11.
Base is E1 PR124 merge e99000494ab52374c01383f4c57891165b58768f; post-merge
Producer CI 38148897543 has four SUCCESS jobs. Native execution authority remains
ROADMAP_STATE.json. Local edit/test/checkpoint/closeout, feature push/PR and scoped
CI corrections authorized; E2/E3 merge requires separate review. No E4 admission.

## Ownership and compatibility

`stocklookup_core/evidence/session_registry.py` owns only the explicit UTF-8 Daily
input-registry load and existing contract-version check. Defaults, override,
JSON/error/return behavior are unchanged. No cache, glob/latest resolution or write.
`daily_research_session_operations.load_registry` re-exports the same callable;
five pure registry importers bind the evidence owner directly. Existing mixed,
frozen and pinned imports remain valid. Official source-registry admission is separate.

`evidence/temporal_freshness.py` owns completed-quarter measurement, explicit reporting
bounds/native-label relation, future-session guard/shared exception, vocabulary and
caller-policy envelopes. It has only stdlib imports and owns no axis eligibility,
investment threshold, provider authority or domain registry.
`financial/period_freshness.py` owns the existing financial older-usable contract
and explicit caller maximum-quarter-lag classification. `valuation/freshness.py`
owns valuation older-usable policy and the research-usability predicate.
`decision/opportunity_axis_freshness.py` retains other axis policy, its public
classifier and exact compatibility exports. Fundamental/valuation contract dictionaries,
functions and exception classes are shared objects; no star export/module-name rewrite.
Financial/valuation consumers now bind the appropriate lower/domain owners.
Portfolio opportunity integration still requires decision policy; its remaining
backward dependency is reported honestly, not hidden through a compatibility alias.

## Ratchet and acceptance invariants

Same stdlib AST analyzer/settings before/after: 3279 -> 3306 import edges, backward
edges 194 -> 188; core->root 150 -> 150; eager SCC count 1, runtime SCC count 8
unchanged (largest 60). More edges reflect explicit ownership/import forms, not a
claim of overall graph shrinkage. Daily registry orchestration fan-in 22 -> 17.
The sealed E0 baseline, E1 carry policy and all 120 relocation mappings remain unchanged.
No new backward edge, eager/runtime cycle, unresolved or unsupported loader is admitted.
No baseline refresh, exception expansion or new utility package. Production Python
launcher ASTs/provider bundle/frozen feedback source files stay unchanged. Only CI
selection adds foundation tests; its single normalized workflow digest is reviewed
and updated in the Daily launcher manifest; executable commands/targets are unchanged.

136 frozen E1 behavior cases cover temporal/error/envelope output; synthetic registry
fixtures cover foreign cwd, defaults/override, missing/malformed/nonmapping JSON,
Unicode/null/zero and preserved errors. Tests check both import orders, callable/class/
mutable-policy identity, absent transitive orchestration imports, stdlib-only foundations,
new upward-edge rejection, frozen source bytes and all relocation mappings. Existing
financial/currency/valuation/qualification tests preserve semantic and integrity gates.
Actual acceptance counts/commands and parity evidence are recorded in local reports
and the compact acceptance note at closeout; local tests are not hosted CI.

## Deferred E3 seams / precise E4 gate

`daily_session_level2_package.session_artifact_paths`, `bounded_artifact_stream` and
`prospective_decision_retention._json_bytes` belong to the feedback code_digest input
set. An import-only edit changes immutable reuse identity. No versioned digest migration
is authorized here. These files are byte-preserved. E4 needs separate explicit scope,
versioned reuse/compatibility contract and bounded read-only proof: every fixed/session
path and cpc.level2 monkeypatch surface, both retention/stream import orders, and compact/
pretty bytes/hashes for Unicode, ordering, separators, floats/NaN/nonfinite, mixed keys,
record map/list, 64KiB boundaries and Windows/Linux newlines. Never unify unrelated
canonical-JSON variants or rewrite historical artifacts. E4 does not start automatically.

No acquisition, Owner Daily, production configuration/data/database/evidence write,
Consumer/Dashboard repository edit, deployment, authority promotion or worktree deletion.
