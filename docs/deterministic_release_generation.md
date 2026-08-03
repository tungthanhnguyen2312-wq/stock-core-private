# Deterministic release generation: two explicit modes

Earlier closeouts claimed both *"byte-identical with a pinned evaluation time"* and
*"`generated_at` differs by session"*. Both statements are true, of different modes, and
neither is a property of the exporter in general. This document names the two modes and
says exactly what each guarantees. `tests/test_deterministic_release.py` proves both by
running two real shadow exports per mode.

## Why the two collapse into one knob

`export_ai_bundle.py` derives the release timestamp from the evaluation time:

```python
reference_at = datetime.fromisoformat(args.evaluation_at) if args.evaluation_at else datetime.now(timezone.utc)
...
generated_at = reference_at.isoformat(timespec="seconds")
```

So `--evaluation-at` is not only a freshness-envelope control. It pins `generated_at` in
`analysis_bundle.json`, `focus_extract.json` and `bundle_manifest.json`, and through the
manifest it pins `trusted_subset.generated_at` and `trusted_subset.bundle_generated_at`
too. There is one clock in the release, not two.

## Normal production mode — no `--evaluation-at`

This is what the operator command runs.

* `generated_at` is wall-clock, so it moves between two builds, and the artifacts are
  **not** byte-identical. Do not claim byte determinism for this mode.
* Because the bundle body changed, `trusted_subset.bundle_sha256` changes with it. The
  exact-session identity moves *consistently* rather than silently staying the same: the
  new manifest describes the new body and no other.
* `session_identity` / `reference_session_date` do **not** move. The trading session a
  release is about is a property of the data, not of the clock.
* **Business content must be identical for unchanged inputs.** Everything except identity,
  timestamp and hash fields is byte-stable across two wall-clock builds. The identity
  fields are enumerated in the test's `IDENTITY_KEYS`; note that
  `intrinsic_valuation.methods.*.valuation_date` is one of them — it is the model's echo of
  the evaluation instant, not the reporting period it valued (that is `financial_period`).

## Reproducibility mode — `--evaluation-at <ISO timestamp>`

* Evaluation time and generated/session time are the same pinned value.
* The supported artifact set is **byte-identical** across two builds:
  `analysis_bundle.json`, `focus_extract.json`, `bundle_manifest.json`, byte for byte,
  including every timestamp and every manifest/proof identity field.
* `statement_taxonomy_sidecar.json` is byte-identical when built with the same
  `--generated-at` and `--session-identity`, and its `records_fingerprint` is independent of
  the clock entirely — the sidecar's own `--check` mode relies on that.
* `observability_events.jsonl` is an append-only run log, not a release artifact, and is
  outside every determinism claim here.

Use this mode to reproduce a past release for audit, or to prove that a code change did not
alter output. Do not use it to produce a release: pinning the clock would misreport when
the release was actually generated.

## The rule

Never state that a release is byte-identical unless **all** bytes are identical, timestamps
and manifest/session fields included. If any timestamp is wall-clock, the honest claim is
semantic determinism of business content, and that is what normal production mode provides.
