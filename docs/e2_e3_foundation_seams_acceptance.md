# E2/E3 local acceptance

Implementation checkpoint `fbbc39f8b4c06741f2da258cdc0dac4361cbe261`; UTF-8 fixture
supplement `224afd0edb86168bad09edaceed0b15f87998213`. The full suite started before the fixture-only supplement;
all production source is identical, and the changed foundation test was rerun:146 PASS.
Baseline E1 merge `e99000494ab52374c01383f4c57891165b58768f`, post-merge CI38148897543:4/4 SUCCESS.

## Local validation

Commands use `python -m pytest -q -rs -p no:cacheprovider`, provider-import-block
`PYTHONPATH=tests/provider_import_block`, `PYTHONDONTWRITEBYTECODE=1`. Expanded commands,
environment, elapsed time, JUnit counts and exit statuses are retained outside Git in
`C:/Projects/StockLookup/codex-reports/e2e3-foundation-seams-20261012/`.
`validate.py` loads the exact `FOCUSED_SELECTION` array from Producer CI YAML;
`focused-inventory.json`, `structural-inventory.json`, `retained-inventory.json`
contain the actual argument arrays, not assumed commands. Local results are not hosted CI.

| Selection | Result |
|---|---|
| Full focused selection; `-m "not retained_evidence and not provider_runtime"` | 5633 PASS, 74 SKIP, 0 failures/errors (103 subtests PASS;49 deselected) |
| Structural/layout/architecture/roadmap/production-call-shape/compact control plane; same marker | 149 PASS, 0 failures/errors/skips |
| Foundation final UTF-8 regression | 146 PASS, 0 failures/errors/skips |
| Initial financial/currency/valuation/integrity integration | 292 PASS |
| Clean-clone retained accounting; `-m retained_evidence`, `STOCKLOOKUP_RETAINED_EVIDENCE_POLICY=skip-if-absent` | 5 PASS, 44 explicit retained-source SKIP |

`python tools/check_architecture.py` and `python tools/check_daily_launchers.py`:PASS.
No exception/baseline expansion. Frozen feedback/provider/launcher Python source hashes
and 120 relocations remain exact. `pip check`:PASS. Global local Python has 10 installed
version drifts against unchanged constraints; provider blocking is effective. Hosted CI
installs the pinned clean environment. No global runtime install/change was performed.

Expanded optional Dashboard suite initially had seven failures from missing August26
retained artifacts or canonical publisher refusal in a feature checkout. Six reproduced
with exact E1 module source in isolated execution; the seventh missing-source failure
was not repeated because that test manipulates a shared release lock and copies other
repositories. These are not claimed as validated real-session publication. No unrelated
fixture, canonical authority or retained record was repaired/relaxed. The additional
compact-budget failure was fixed by removing duplicated navigation prose, retaining
all removed links in ACTIVE_STATE; compact structural checks now pass.

## Artifact and identity parity

Original E1 Git blobs and candidate implementations executed separately with identical
fixed synthetic financial observations and unavailable official-source claims. This is
actual output equality, not source-only evidence. All comparisons are byte-for-byte equal
using sorted compact UTF-8 JSON, ensure_ascii=False, allow_nan=False, no final newline:

- `financial-product`: 42092 bytes; SHA256 `96fc867e057c902f64393b7c619ec895d8595722247c708714d66582adec0ee4`.

- `reporting-currency`: 106189 bytes; SHA256 `2f392cf94437d850ac27c534eca41b72e104ad64e656f90f9ba939f69f20e58d`.

- `valuation-record`: 19828 bytes; SHA256 `ffad025aacbb78a443359f070d67bc5e98684d3b97d4c9a7a2e6ae11bb5ea557`.

- `valuation-axes`: 30987 bytes; SHA256 `b4838817e5d2dabfbc5a70d6e744dd6918f7ccd5e9685a28bafcb4d857f601c8`.


This proves those fixed fixture call shapes, not unexecuted production Daily artifacts.
136 captured E1 temporal envelopes/errors, missing/malformed registry input, import orders,
shared callable/class/mutable-policy identity, lightweight stdlib boundaries and adversarial
new backward-edge rejection are independently tested.

## Architecture and remaining gate

Identical analyzer/settings: internal edges3279->3306; backward194->188; core->root150
unchanged; eagerSCC1/runtimeSCC8 unchanged, exact membership retained, maximum60.
Three financial/valuation consumer connections (package/module import forms) eliminated;
registry orchestration fan-in22->17. Graphs, memberships and affected fan-in/out are in
before/after-metrics.json and before/after-graph.json. Total module count967->971.

Paths and bounded serialization are individually deferred as frozen feedback code_digest
inputs. The scope contract specifies separate E4 versioned identity acceptance and byte/
path/Windows-Linux regression requirements. No automatic E4. Native closeout is local-only;
feature publication is authorized, E2/E3 merge remains separately Owner-gated at exact HEAD.
No Daily, acquisition, deployment, production/evidence write or authority promotion.
