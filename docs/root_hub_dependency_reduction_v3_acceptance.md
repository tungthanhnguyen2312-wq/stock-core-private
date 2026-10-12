# Root hub dependency reduction V3 acceptance

Baseline `d53999ba07a080b7fae2104185c56cc9a55ce210` (V2 PR130 merge; post-merge CI
`38222535046` SUCCESS). [Contract](root_hub_dependency_reduction_v3_contract.md).
Interpreter: a venv built only from `requirements.txt` + `requirements-test.txt` under
`constraints.txt`, with the provider import block on; `--installed` dependency tiers PASS.

## Stages

| Stage | Change | Targeted tests (failing IDs before / after / new) |
|---|---|---|
| S1 identity seam | 43 root imports retargeted to `stocklookup_core.evidence.field_identity` | 190 / 190 / 0 |
| C1 relocation | 11 modules: evidence 6, financial 1, valuation 1, research 3; 44 import sites, VERIFY PASS | 223 / 223 / 0 |

Each stage ran its affected tests on unchanged and changed source in the same environment
and compared test IDs, not counts. C1's selection added two files, which were baselined
separately on `d53999b`. The baseline failures come from absent retained/runtime data on
this host and are unchanged. The only new test ID is the V3 seam test, which passes.

## Counts and graph (identical E0 analyzer)

| Measurement | V2 baseline | After |
|---|---:|---:|
| Root Python | 336 | 325 |
| Packaged Python | 285 | 296 |
| Relocations | 260 | 271 |
| Backward edge rows (pairs) | 150 (146) | 150 (146) |
| core-to-root module pairs | 112 | 112 |
| Eager / runtime SCCs (largest; participation) | 1 / 11 (10; 41) | identical membership |
| Unresolved / unsupported dynamic sites | 9 / 16 | 9 / 16 |
| `field_temporal_contract` importers | 81 | 38 |

Ratchet regressions: none. Under one normalization applied to both trees (relocated names
mapped back, package-initializer edges excluded), exactly 43 edges change. The same 43
root sources retarget from `field_temporal_contract` to `stocklookup_core.evidence.field_identity`;
no other edge is added or removed. Unique rows rise only through package-initializer edges.
No existing core-to-root edge consumes only re-exported names, so V3 does not reduce
core-to-root pairs; the one partial case (`multi_period_financial_panel`) needs the temporal types.

## Identity and parity

- In both import orders (hub first, owner first), all 43 module-level bindings are the owner's
  objects (`is`), the hub's three re-exports are the owner's objects, and 2 function-local
  imports resolve to the same owner attribute. No provider module is loaded.
- The 43 modules were imported at the baseline (old names) and the candidate (new names)
  and compared on public names, signatures, function-source hashes and constants. They are
  identical except for: checkout-root default paths (1), function memory addresses in default
  reprs (2), and 4 functions whose only change is a function-local import line.
- No E2/E3 pin, protected source, provider bundle file, Daily launcher target or caller,
  workflow, dependency file, historical executed source or V1/V2 mapping changed.

## CI-equivalent validation

- Structural selection: 137 PASS. Call-shape smoke: 7 PASS. Compile, roadmap JSON and
  `--check`: PASS. Daily launcher guard: PASS. `git diff --check`: clean.
- Focused hermetic selection (267 entries): 6158 PASS, 78 skipped, 49 deselected, 103 subtests.
  Two `windows_only` provider OS-containment tests fail only under the venv launcher, which
  spawns a child interpreter so the job PID differs. Both pass with the system interpreter;
  this was known in V2, V3 does not touch them, and Linux CI skips them.
- Retained accounting: 5 PASS, 44 explicit absent-evidence skips.

## Native state

Admitted at the exact starting HEAD `d53999b` before any source edit (owner-approved
`--owner-override` admission). Local closeout checkpoint
`45af8fcb67fccf04b3f322d400afc8f2793a98bb`: `LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`. Hosted Linux CI and the Owner merge decision remain release
gates; no successor is admitted.
