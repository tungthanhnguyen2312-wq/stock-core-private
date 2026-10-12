# Accelerated root package consolidation V1 acceptance

Baseline `3f1be104386a218899b7dcb4bdeaa154be17ce06` (E6 PR128 merge; post-merge CI
`38194697661` four jobs SUCCESS). [Contract](accelerated_root_package_consolidation_v1_contract.md).
Interpreter: governed system CPython 3.13, provider import block on `PYTHONPATH`.

## Cohorts

| Cohort | Destination | Moved | Import sites | Targeted tests (pass / new failures) |
|---|---|---:|---:|---|
| C1 official source and corporate-action evidence | evidence | 20 | 75 + 3 reviewed | 1913 / 0 |
| C2 market, session and universe evidence; breadth | evidence 25, tactical 3 | 28 | 154 + 3 | 2641 / 0 |
| C3 financial research components | financial | 19 | 87 + 2 | 1846 / 0 |
| C4 research, portfolio and decision projections | research 20, portfolio 2, decision 6 | 28 | 93 | 1707 / 0 |

Each cohort ran its affected tests on the unchanged tree and after relocation; failing IDs
were identical (62/168/70/167), all absent retained evidence or local runtime data in this
worktree (FileNotFound under `operations-review/`/`data/`, export-bundle runtime DB,
`LATEST_COMPLETED_RUN.json` fixture assumptions). Nothing was regenerated or copied.
A first C1 attempt exposed E5 parity sources importing `official_acquisition_budget` by
name; the cohort was reset and re-applied without the three historically bound modules.

## Counts and graph (identical E0 analyzer)

| Measurement | E6 baseline | After |
|---|---:|---:|
| Root Python | 476 | 381 |
| Packaged Python | 145 | 240 |
| Relocations / grandfathered root names | 120 / 488 | 215 / 393 |
| Modules | 982 | 982 |
| Backward edge rows (pairs) | 176 (172) | 156 (152) |
| core-to-root module pairs | 138 | 118 |
| Eager / runtime SCCs (largest; participation) | 1 / 11 (10; 41) | identical membership |
| Unresolved / unsupported dynamic sites | 9 / 16 | 9 / 16 |

Unique edge rows rise 3374 → 3662 only through package-initializer edges recorded for
package-form imports. Mapping relocated names back and excluding initializer edges, the
dependency set is identical: 2567 edges before and after, none added or removed.
Ratchet, Daily launcher guard and placement guards PASS without baseline, policy or
grandfathering edits.

## Identity and parity

No E2/E3 byte pin, V1/E4 V2 source, provider bundle file, E5/E6 pinned foundation,
AST-pinned launcher caller, workflow or dependency file changed. Of 95 moved bodies,
76 are byte-identical and 19 differ only in import lines or the `parents[2]` root line.
Every moved module imported at the baseline (old name) and candidate (new name) in
separate processes yields identical public names, signatures, function-source hashes and
constant values; the only differences are object addresses and checkout-root paths.
Frozen V1 `fa79baad…` and E4 V2 `07c2a363…` digests are asserted by E5/E6 tests (PASS).

## CI-equivalent validation

Structural job selection 135 PASS; call-shape smoke 7 PASS; focused hermetic selection
(267 entries, four local chunks) 6180 PASS, 74 skipped, 49 deselected, 112 subtests,
zero failures; retained accounting 5 PASS, 44 explicit absent-evidence skips. Static
dependency tiers PASS; `--installed` reports host package drift only (no file changed).
Roadmap `--check` ON_TRACK. `git diff --check` clean.

## Native state

Admission recorded at the exact starting HEAD `3f1be10` (first attempt refused by tool
permission; rerun after Owner approval). Local closeout checkpoint
`69160a150a882d4dd40c6ba7a147e4c7a8e43eff`: `LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`.
Hosted CI and the Owner merge decision remain release gates; no successor is admitted.

## Hosted CI corrective

Hosted run `38205381308` on `959b0d2` failed Structural and Focused jobs (6076 pass, 1 fail)
on `test_bulk_relocated_modules_import_cleanly_and_keep_checkout_root`; its subprocess
output was captured but not shown. The local runs above used an interpreter with extra
packages, so they did not reproduce it. In a venv built only from the CI install contract
the old test fails identically. Root cause: `stocklookup_core.evidence.cited_evidence_backup`
imports `official_document_retrieval`, whose line 7 `from pypdf import PdfReader` raises
`ModuleNotFoundError: No module named 'pypdf'`. The chain is byte-identical to the E6 root
module, and `pypdf` is a documented undeclared optional import; this is a clean-clone
limitation the new harness exposed, not a relocation regression.

Only the harness changed. It imports all 95 in the original order and reports per-module
tracebacks, stdout/stderr, ROOT mismatches and provider modules. One exact pair
(`cited_evidence_backup` -> `pypdf`) is excused, and only while `pypdf` is absent.
Negative controls prove missing required dependencies and wrong roots still fail.
CI-equivalent venv: probe 94 imported + 1 excused, 0 failures; structural selection
136 PASS; E4/E5/E6/foundation/call-shape/fitness/price/control-plane 725 PASS, 3 skips;
ratchet, launcher guard and roadmap check PASS. Moved code and the native checkpoint are unchanged.
