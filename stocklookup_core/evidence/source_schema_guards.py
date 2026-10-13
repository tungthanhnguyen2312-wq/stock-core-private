"""Small, deterministic schema guards for offline source adapters."""

from __future__ import annotations

import re
from typing import Any, Iterable


FINANCIAL_REQUIRED = {"ticker", "report_type", "source", "item"}
ALIAS_REQUIRED = {"ticker", "alias", "alias_type", "priority", "valid_from", "valid_to"}
IDENTIFIER_FIELDS = {"item_id", "source_field"}
UNIT_FIELDS = {"raw_unit", "unit"}


class SourceSchemaError(ValueError):
    """A parse failure that retains enough context for audit and triage."""

    status = "parse_failed"

    def __init__(
        self,
        source: str,
        *,
        missing_fields: Iterable[str] = (),
        payload_keys: Iterable[str] = (),
        reason: str = "source_schema_mismatch",
    ) -> None:
        self.source = str(source)
        self.missing_fields = sorted(set(missing_fields))
        self.payload_keys = sorted(set(payload_keys))
        self.reason = reason
        super().__init__(
            f"{self.status}: source={self.source}; reason={reason}; "
            f"missing_fields={self.missing_fields}; payload_keys={self.payload_keys}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "reason": self.reason,
            "missing_fields": self.missing_fields,
            "payload_keys": self.payload_keys,
        }


def guard_financial_statement_columns(
    columns: Iterable[Any], source: str, *, require_unit: bool = False
) -> dict[str, Any]:
    """Validate a wide financial statement without assuming a provider schema."""
    keys = {str(column).strip() for column in columns}
    missing = FINANCIAL_REQUIRED - keys
    if not keys & IDENTIFIER_FIELDS:
        missing.add("item_id|source_field")
    period_fields = sorted(key for key in keys if re.match(r"^\d{4}", key))
    if not period_fields:
        missing.add("period/value")
    if require_unit and not keys & UNIT_FIELDS:
        missing.add("raw_unit|unit")
    if missing:
        raise SourceSchemaError(source, missing_fields=missing, payload_keys=keys)
    return {
        "status": "valid",
        "source": str(source),
        "identifier_fields": sorted(keys & IDENTIFIER_FIELDS),
        "period_fields": period_fields,
        "unit_fields": sorted(keys & UNIT_FIELDS),
        "unit_field_status": "present" if keys & UNIT_FIELDS else "missing",
    }


def guard_alias_columns(columns: Iterable[Any], source: str) -> dict[str, Any]:
    keys = {str(column).strip() for column in columns}
    missing = ALIAS_REQUIRED - keys
    if missing:
        raise SourceSchemaError(source, missing_fields=missing, payload_keys=keys)
    return {"status": "valid", "source": str(source), "payload_keys": sorted(keys)}
