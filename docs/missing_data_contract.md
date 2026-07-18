# Missing data contract v2

Schema v2 keeps legacy scalar fields and adds parallel status/provenance. Consumers must distinguish a numeric zero, a null value, and a metric object/status.

Statuses are `reported`, `derived`, `proxy`, `source_empty`, `mapping_missing`, `insufficient_periods`, `parse_failed`, `stale`, `not_applicable`, `not_queried`, `network_failed`, `unsupported`, `derivation_not_implemented`, `unit_unknown`, and `period_basis_unknown`.

- `derived` must retain formula and input names.
- `proxy` is usable only when the selected validation profile allows it.
- `not_applicable` is excluded from coverage denominators.
- `source_empty` means a source was queried and returned no usable rows; it differs from `not_queried` and `parse_failed`.
- Missing is null, never zero.
- An unknown unit remains explicit and blocks cross-source unit assumptions.

The AI context layer preserves scalar compatibility while exposing `*_meta`. Purpose suitability is `profile_valid`; legacy `valid` only describes structural compatibility.
