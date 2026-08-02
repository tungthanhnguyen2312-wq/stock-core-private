# Exact-session analysis-bundle contract

Producer contract version: `stocklookup-producer/2026.08.03`
Trusted-subset proof schema: `1.1.0`

Both sides pin these exact strings. There is no version range and no "compatible enough"
path: a bundle emitted by an older Producer is legacy, and legacy is never presented as
current trusted output.

## Why this exists

Schema `1.0.0` verified that `bundle_manifest.json` was well-shaped and that the bundle
hashed to what the manifest recorded. That is not proof of session association. It accepted:

* a manifest paired with a *different* bundle body that happened to be self-consistent;
* an artifact (focus extract, taxonomy sidecar) rewritten after the manifest was generated;
* an undeclared trusted artifact sitting next to the bundle;
* output from an older Producer whose semantics have since changed;
* a proof covering only `HPG`/`VNM`, which left every production export unverifiable
  because it carried no proof at all.

## What the Producer emits

`bundle_manifest.json → trusted_subset`, written by
`export_ai_bundle.py::build_trusted_subset_proof`:

| field | meaning |
| --- | --- |
| `schema_version` | `1.1.0`, pinned |
| `producer_contract_version` | pinned; bump on any change to shape or verification rules |
| `tickers` | sorted tickers this proof actually covers (one current-session snapshot each) |
| `unproven_tickers` | every other exported ticker, each with an explicit `reason` |
| `bundle_ticker_set` | the full exported set; must equal `tickers ∪ unproven_tickers` |
| `session_identity` | the reference session date this export is anchored to |
| `bundle_filename` / `bundle_sha256` | binds the exact bundle bytes |
| `bundle_reference_session_date` / `bundle_generated_at` | copied from the bundle body |
| `generated_at` | must equal the bundle body's `generated_at` |
| `required_artifacts` | `{file, sha256}` for every session artifact except the manifest |
| `expected_artifact_filenames` | the exact trusted-artifact set, manifest included |
| `per_ticker` | one entry per proven ticker, carrying its session identity and warnings |
| `price_basis` / `volume_basis` / `trust_state` | market-data qualification, a separate axis |

`bundle_manifest.json` itself cannot appear in `required_artifacts` — it cannot hash
itself — so it is proven indirectly: it is the document making the claims, and every claim
it makes about the other artifacts is checked.

A ticker with no current-session snapshot (an index row, a halted or delisted symbol) does
not abort the export. It is excluded from `tickers`, listed under `unproven_tickers` with a
reason, and the Consumer refuses to treat it as exact-session trusted.

## The trusted artifact namespace

```
analysis_bundle.json   bundle_manifest.json   focus_extract.json   statement_taxonomy_sidecar.json
```

The Consumer scans exactly these names beside the bundle. A file in the namespace that the
manifest did not declare is `unexpected_trusted_artifact:<name>` and fails closed. Scoping
the scan to a fixed namespace is deliberate: the runtime root holds hundreds of unrelated
files, and treating any of them as an undeclared session artifact would be noise, not safety.

## What the Consumer verifies

`ai-core-private/builders/build_ticker_context.py::verify_exact_session_bundle`. Every
rejection names one precise cause and carries filenames only — never a filesystem path,
a secret, or bundle content:

```
manifest_invalid_payload          manifest_proof_missing            manifest_schema_unsupported
producer_contract_version_unsupported                                bundle_filename_mismatch
proven_ticker_set_invalid         unproven_ticker_set_missing       bundle_ticker_set_missing
ticker_accounting_incomplete      unproven_ticker_missing_reason    bundle_ticker_set_mismatch
session_identity_missing          bundle_hash_mismatch              bundle_unreadable
bundle_session_mismatch           bundle_generated_at_mismatch      manifest_generated_at_mismatch
manifest_bundle_generated_at_mismatch                                per_ticker_proof_missing
per_ticker_set_mismatch           per_ticker_session_mismatch       bundle_ticker_session_mismatch
required_artifacts_missing        required_artifacts_malformed      required_artifacts_missing_bundle
required_artifact_missing:<f>     required_artifact_hash_mismatch:<f>  required_artifact_unreadable:<f>
expected_artifact_set_missing     expected_artifact_set_inconsistent   unexpected_trusted_artifact:<f>
```

## Two independent axes

`trusted_subset_validation` reports both, and never lets one stand in for the other:

* `integrity_state` — `exact_session_verified` | `unverified` | `legacy_unverified`.
  Structural and cryptographic only. Says nothing about market-data quality.
* `basis_state` — `qualified` | `unqualified`. Price *and* volume basis verified. Says
  nothing about integrity.

`state` remains the pre-existing single verdict (`exact_session_trusted` only when both
pass), so every existing consumer of `state` is unchanged.

Contracts gate on the axis that actually applies:

* `analysis_readiness_contract` gates on **integrity** (per ticker). An unqualified basis
  does not suppress the per-domain readiness the Producer already computed with the basis
  contract in hand; it forces `inferences_allowed = False` and adds an explicit warning.
* `analysis_lane_eligibility_contract` gates on **integrity** (per ticker) only.
  `evaluate_ticker_lanes()` already blocks adjusted-return, liquidity and backtest claims
  per lane with its own reasons; re-suppressing the whole result would hide the lanes it
  correctly allows.

## Legacy bundles

A bundle with no `bundle_manifest.json` beside it yields
`state: legacy_untrusted`, `integrity_state: legacy_unverified`, reason `manifest_missing`,
and the warning code `trusted_subset_legacy_untrusted`. It is loaded and readable; it is
never exact-session trusted, and no contract gated on integrity will accept it.
