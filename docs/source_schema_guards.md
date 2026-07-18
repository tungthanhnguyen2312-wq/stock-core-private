# Source schema guards

Source adapters fail explicitly when an input contract changes. `SourceSchemaError` reports `status=parse_failed` together with `source`, `reason`, `missing_fields`, and observed `payload_keys`; callers must not convert this condition into a silent empty dataset.

## Financial statements

A wide statement requires:

- `ticker`, `report_type`, `source`, and `item`;
- at least one identifier: `item_id` or `source_field`;
- at least one period/value column beginning with a four-digit year.

`raw_unit` or `unit` is reported by the guard. Legacy inputs may omit it and receive `unit_field_status=missing`; strict adapter tests can set `require_unit=True`, which turns the absence into `parse_failed`. Unknown unit text remains explicit as `unit_unknown` during normalization.

## Alias registry

The news alias CSV requires `ticker`, `alias`, `alias_type`, `priority`, `valid_from`, and `valid_to`. A header mismatch raises the same structured source-schema error before any alias row is consumed.

## Financial mapping registry

Registry loading rejects missing columns, duplicate rule IDs, equal-priority ambiguous exact matchers, invalid regex, unknown canonical metrics, unsupported entity/report types, sign multipliers other than `-1` or `1`, non-positive/non-finite unit multipliers, and conflicting exact mappings. The default registry additionally requires `financial_item_map.meta.json` with `registry_version` and provenance fields `source_basis`, `owner`, and `updated_at`.

These guards validate contracts, not source availability. A valid empty provider response is `source_empty`; a non-empty payload that cannot satisfy the contract is `parse_failed`; a provider transport failure is `network_failed`.
