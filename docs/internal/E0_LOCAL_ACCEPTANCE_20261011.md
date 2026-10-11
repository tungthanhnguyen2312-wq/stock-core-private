# E0 local acceptance — 2026-10-11

Implementation checkpoint: `1f9ee05ba057a73178b17dc8d60ca2c9a827163a`.
Native disposition: `LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED`; no E1.

Broad hermetic replay: 427 selected / 427 passed / 0 failed / 0 errors / 0 skipped / 8 explicitly deselected; exit 0.
Python 3.13.12; provider imports blocked; runtime is an empty C: scratch fixture.

Durable host-local evidence: `codex-reports/e0-final-hardening-and-release-20261011/`
in the workspace, outside Git. `accepted-metadata.json` retains exact argv, environment,
versions, HEAD and counts; `accepted-selection.json` retains selected and deselected node IDs.

JUnit SHA256 (`accepted.xml`): `ec73a5ffaee612af3762c02383702439649eb595324bb753eccfc2e0a5f382a7`.
Selection SHA256: `4e0dfe0941feec10a45ff9e3682c83277b3be190fd807787c77303c14b87b200`.
Replay runner SHA256: `2628e5e4a63b0f81b00cfd16c08569231d3963fcd2885be76f0821b2e86087a2`.

Replay with `python <local-report-directory>/replay_acceptance.py replay`; inspect its
recorded HEAD before comparing results. Final closeout verification and native JSON
are retained separately with the final report; broad counts are never summed across runs.

107 relocation entries, production application source, provider bindings and authority
remain unchanged from the accepted E0 start. Only local checkpoints are authorized;
Owner review/push/PR is the next gate, with separate exact-HEAD merge authorization.
