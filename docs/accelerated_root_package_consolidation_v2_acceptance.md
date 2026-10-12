# Accelerated root package consolidation V2 acceptance

Baseline `9174d2b8b8e13fa3a2a4c696b9e2fb28a39a81ea` (V1 PR129 merge; post-merge CI
`38210255068` four jobs SUCCESS). [Contract](accelerated_root_package_consolidation_v2_contract.md).
Interpreter: a venv built only from `requirements.txt` + `requirements-test.txt` under
`constraints.txt` (no global optional packages), with the provider import block on.
This closes V1's hosted blind spot: `--installed` dependency tiers PASS, 0 violations.

## Cohorts

| Cohort | Destination | Moved | Import sites | Targeted (pass / new failures) |
|---|---|---:|---:|---|
| C1 market-data provider-basis evidence | evidence | 23 | 143 + 5 reviewed | 2149 / 0 |
| C2 temporal, official, share evidence; adapters | evidence 8, acquisition 4 | 12 | 46 + 2 | 1378 / 0 |
| C3 financial, valuation, research, decision | financial 6, valuation 1, research 1, decision 2 | 10 | 65 + 1 | 2179 / 0 |

Each cohort ran its affected tests before and after relocation, in the same environment.
Failing IDs were identical (47/35/71) and all come from absent retained evidence or
runtime data. The expected structural deltas were the relocation pin (now an exact V2
fixture) and the KBS import-set expectations; both were updated before the final run.

## Counts and graph (identical E0 analyzer)

| Measurement | V1 baseline | After |
|---|---:|---:|
| Root Python | 381 | 336 |
| Packaged Python | 240 | 285 |
| Relocations | 215 | 260 |
| Backward edge rows (pairs) | 156 (152) | 150 (146) |
| core-to-root module pairs | 118 | 112 |
| Eager / runtime SCCs (largest; participation) | 1 / 11 (10; 41) | identical membership |
| Unresolved / unsupported dynamic sites | 9 / 16 | 9 / 16 |

Unique edge rows (3662 → 3781) rise only through package-initializer edges. Mapping
relocated names back and excluding those edges, the dependency set is identical:
2567 edges, none added or removed. Ratchet, launcher, placement and loader guards PASS.

## Identity and parity

No E2/E3 byte pin, V1/E4 V2 source, provider bundle, E5/E6 foundation, launcher caller,
workflow or dependency file changed. Of the 45 moved bodies, 28 are byte-identical and
17 differ only in import or root lines. In the CI-equivalent venv, each module imported
at the baseline (old name) and the candidate (new name) gives identical public names,
signatures, function-source hashes and constants. Only checkout-root default paths
differ. The V1 import probe now covers all 140 V1+V2 relocations; `pypdf` remains the
single excused optional import.

## CI-equivalent validation

- Structural selection: 136 PASS. Call-shape smoke: 7 PASS. Compile and roadmap JSON: PASS.
- Focused hermetic selection (267 entries): 6175 PASS, 78 skipped, 49 deselected,
  112 subtests.
- Two `windows_only` provider OS-containment tests fail under the venv. The Windows venv
  launcher spawns the real interpreter as a child, so the job PID differs. Both pass with
  the governed system interpreter; V2 does not touch either file, and Linux CI skips them.
- Retained accounting: 5 PASS, 44 explicit absent-evidence skips.

## Native state

Admitted at the exact starting HEAD `9174d2b` before any source edit. Local closeout
checkpoint `171d14b2b7f483dbb7433cfd0cee8cc6a6d10384`: `LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`.
Hosted Linux CI and the Owner merge decision remain release gates; no successor is admitted.
