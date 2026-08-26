# Generated statement-taxonomy sidecar

Artifact: `<runtime-root>/statement_taxonomy_sidecar.json`
Schema: `1.0.0` · Classifier: `statement_taxonomy_classifier` `2.0.0`
Authority level: **`generated_evidence`** — strictly below a manually verified profile.

## Authority order

1. **manually verified entity profile** — `config/ticker_entity_profiles.csv`. Always wins.
2. **generated statement-taxonomy evidence** — this artifact. May only *withhold* a
   corporate model, never grant one.
3. **unknown**.

`resolve_entity_authority()` implements exactly that. `corporate_vas` never resolves an
entity type: a corporate *template* is not evidence that the issuer is a non-financial
corporate, and reading absence of financial markers as "corporate" is the fail-open route
this project refuses. `unknown` and `unresolved` never default to corporate either.

`config/ticker_entity_profiles.csv` is never read for resolution by this module, never
written, and never backfilled. `CANONICAL_PROFILE_BACKFILL_AUTHORIZED` remains `NO`.

## Three concepts, never collapsed

| concept | source | authority |
| --- | --- | --- |
| `statement_taxonomy` | observed item vocabulary in the retained payload | generated |
| `issuer_entity_type` | `config/ticker_entity_profiles.csv` | manual, authoritative |
| `model_applicability` | `altman_applicability.evaluate_altman_applicability` | derived |

## Build

```bash
python tools/build_statement_taxonomy_sidecar.py --runtime-root <path> --session-identity <YYYY-MM-DD>
python tools/build_statement_taxonomy_sidecar.py --runtime-root <path> --check
```

Read-only over `data_bctc/*_balance_sheet_quarter.parquet`. `--check` rebuilds in memory
and compares `records_fingerprint`; it never writes.

## Determinism

`records` are fully sorted and derived only from the input payloads, so
`records_fingerprint` is byte-stable across rebuilds on unchanged inputs.
`generated_at` and `session_identity` are session metadata and are deliberately excluded
from that fingerprint — they are the only fields expected to differ between two runs over
identical inputs. `input_fingerprint` covers the sorted `(filename, sha256)` of every input.

## Record fields

`record_id` (deterministic identity over schema/classifier/ticker/taxonomy/period-range/
source hash), `ticker`, `statement_taxonomy`, `authority_level`, `classification_status`,
`abstention_reason`, `ambiguity_status`, `cross_period_stable`, `distinct_taxonomies`,
`source`, `source_file`, `source_sha256`, `statement_scope`, `classifier_version`,
`periods_evaluated`, `first_observed_period`, `last_observed_period`,
`observed_period_range`, `matched_positive_markers`, `matched_exclusion_markers`.

No record ever carries `entity_type` or `issuer_entity_type`.

## Reconciliation

Every input payload lands in exactly one of `records` or `omitted`, each omission carrying
an explicit reason. `reconciliation.inputs_fully_accounted` asserts this and the build
refuses to write when it is false.

Production run of 2026-08-03 against `dashboard-runtime`:

```
input payloads     1381
classified         1380
omitted               1   BIO — payload_has_no_reporting_period_columns
corporate_vas                     1297
securities_company                  41
credit_institution                  29
financial_specialized_ambiguous     13
```

These match the 2026-08-02 shadow study exactly.

## Session binding

The sidecar carries the `session_identity` it was built for. `generated_at` and
`session_identity` are envelope fields excluded from `records_fingerprint`; they are a
packaging/coherence bind into an exact-session release, not a claim that the Circular
template itself is a same-session market observation. Binding a previous session's sidecar
JSON into a later market session (or rewriting only `session_identity` on those bytes) is
forbidden. Rebuild from retained statement payloads with
`tools/build_statement_taxonomy_sidecar.py` or
`tools/materialize_canonical_trusted_subset_release.py`.

`export_ai_bundle.py` ignores a sidecar whose `session_identity` differs from the export's
reference session, raises the `statement_taxonomy_sidecar_session_mismatch` data-quality
flag, and proceeds with **no** taxonomy evidence — leaving the applicability gate on
`insufficient_evidence` rather than binding a previous session's generated evidence into an
exact-session artifact set.

When it is bound, its sha256 enters `bundle_manifest.json → trusted_subset.required_artifacts`,
so any later edit to the sidecar invalidates the whole bundle at the Consumer.

## Where it is consumed

`export_ai_bundle.py` attaches, per ticker:

* `tickers[t].statement_taxonomy_evidence` — the resolved taxonomy, the authority that
  resolved it, the full generated record as provenance, and a limitation stating this is
  not a verified issuer type;
* the taxonomy is passed to `evaluate_altman_z_score(..., statement_taxonomy=...)`, which
  forwards it to the applicability gate. It can turn `insufficient_evidence` into
  `not_applicable` for a specialized financial filer whose entity type is unresolved. It
  can never produce `eligible`.
