"""Generic, fail-closed reconciliation of retained official values to provider observations.

This is an ephemeral qualification projection, not a fact store and not a PDF scraper.
Its caller supplies only exact, already-retained document spans and provider observations.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


VERSION = "1.0.0"
CONTRACT_VERSION = "official_financial_value_evidence/v1"
EXACT_MATCH = "EXACT_MATCH"
EXACT_UNIT_MATCH = "EXACT_MATCH_AFTER_EXPLICIT_UNIT_NORMALIZATION"
SIGN_MATCH = "APPROVED_SIGN_POLICY_MATCH"
BLOCKED_STATES = {"VALUE_MISMATCH", "SEMANTIC_IDENTITY_MISMATCH", "PERIOD_MISMATCH", "SCOPE_MISMATCH",
                  "CURRENCY_SCALE_BLOCKED", "AMBIGUOUS_OFFICIAL_VALUE", "PROVIDER_OBSERVATION_MISSING",
                  "OFFICIAL_VALUE_MISSING", "SECTOR_NOT_APPLICABLE"}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def stable_id(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def parse_accounting_integer(raw: Any) -> int:
    """Parse only an explicitly printed accounting integer; decimals are intentionally refused."""
    text = str(raw).strip()
    negative = text.startswith("(") and text.endswith(")")
    body = text[1:-1] if negative else text
    if not re.fullmatch(r"[0-9]{1,3}(?:[,.][0-9]{3})*|[0-9]+", body):
        raise ValueError("NUMERIC_TEXT_AMBIGUOUS")
    if len({ch for ch in body if ch in ",."}) > 1:
        raise ValueError("NUMERIC_TEXT_AMBIGUOUS")
    if any(len(part) != 3 for part in re.split(r"[,.]", body)[1:]):
        raise ValueError("NUMERIC_TEXT_AMBIGUOUS")
    return -int(body.replace(",", "").replace(".", "")) if negative else int(body.replace(",", "").replace(".", ""))


def _period_compatible(official: Mapping[str, Any], provider: Mapping[str, Any]) -> bool:
    if official.get("reporting_period") == provider.get("reporting_period"):
        return True
    # Existing, narrowly-scoped canonical policy: a FY balance-sheet instant is the Q4 instant.
    period = str(official.get("reporting_period") or "")
    return (official.get("statement_family") == "balance_sheet" and period.isdigit()
            and provider.get("reporting_period") == f"{period}-Q4")


def _value(record: Mapping[str, Any], prefix: str) -> int | None:
    try:
        raw = record.get("normalized_numeric_value")
        return int(raw) * int(record.get("unit_scale", 1)) if raw is not None else None
    except (TypeError, ValueError):
        return None


def qualify_value_evidence(official: Mapping[str, Any], provider: Mapping[str, Any] | None,
                           *, applicable_entity_types: set[str] | frozenset[str] | None = None,
                           sign_policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Reconcile exactly; no tolerance, magnitude heuristics, or scope inference exists here."""
    blockers: list[str] = []
    required = ("document_sha256", "issuer_identity", "reporting_period", "periodicity", "statement_scope",
                "currency", "unit_scale", "canonical_metric", "raw_label", "raw_value_text", "source_page",
                "statement_family", "extraction_method", "source_span")
    if any(official.get(key) in (None, "") for key in required):
        blockers.append("OFFICIAL_VALUE_MISSING")
    if official.get("source_span", {}).get("document_sha256") != official.get("document_sha256"):
        blockers.append("OFFICIAL_SOURCE_SPAN_UNBOUND")
    if applicable_entity_types is not None and official.get("entity_type") not in applicable_entity_types:
        blockers.append("SECTOR_NOT_APPLICABLE")
    try:
        raw_number = parse_accounting_integer(official.get("raw_value_text"))
    except ValueError:
        raw_number = None
        blockers.append("OFFICIAL_VALUE_MISSING")
    if raw_number is not None and official.get("normalized_numeric_value") != raw_number:
        blockers.append("OFFICIAL_NORMALIZATION_UNVERIFIED")
    official_value = _value(official, "official")
    comparison = None
    if provider is None:
        blockers.append("PROVIDER_OBSERVATION_MISSING")
    else:
        if provider.get("canonical_metric") != official.get("canonical_metric") or provider.get("statement_family") != official.get("statement_family"):
            blockers.append("SEMANTIC_IDENTITY_MISMATCH")
        if not _period_compatible(official, provider):
            blockers.append("PERIOD_MISMATCH")
        if provider.get("issuer_identity") != official.get("issuer_identity"):
            blockers.append("SEMANTIC_IDENTITY_MISMATCH")
        # Provider scope/currency metadata is optional in the legacy raw layer.  When it
        # is supplied, disagreement is a hard gate; absence is never silently invented.
        if provider.get("statement_scope") not in (None, "") and provider.get("statement_scope") != official.get("statement_scope"):
            blockers.append("SCOPE_MISMATCH")
        if provider.get("currency") not in (None, "") and provider.get("currency") != official.get("currency"):
            blockers.append("CURRENCY_SCALE_BLOCKED")
        provider_value = _value(provider, "provider")
        if provider_value is None or official_value is None:
            blockers.append("OFFICIAL_VALUE_MISSING")
        elif not blockers:
            if provider_value == official_value:
                comparison = EXACT_MATCH if int(provider.get("unit_scale", 1)) == int(official.get("unit_scale", 1)) else EXACT_UNIT_MATCH
            elif sign_policy and sign_policy.get("version") and provider_value == -official_value:
                comparison = SIGN_MATCH
            else:
                blockers.append("VALUE_MISMATCH")
    blockers = sorted(set(blockers))
    state = comparison or (blockers[0] if blockers else "OFFICIAL_VALUE_MISSING")
    qualified = comparison in {EXACT_MATCH, EXACT_UNIT_MATCH, SIGN_MATCH} and not blockers
    identity = {key: official.get(key) for key in ("issuer_identity", "reporting_period", "canonical_metric", "document_sha256")}
    result = {
        "schema_version": VERSION, "contract_version": CONTRACT_VERSION,
        "value_evidence_id": stable_id({"identity": identity, "source_span": official.get("source_span"), "raw_value_text": official.get("raw_value_text")}),
        "official_value_evidence": {**dict(official), "normalized_value": official_value},
        "provider_observation": dict(provider) if provider else None,
        "reconciliation_status": state, "blockers": blockers,
        "canonical_qualification": "CANONICAL_QUALIFIED" if qualified else "CANONICAL_BLOCKED",
        "provider_observation_created": False, "canonical_store_mutated": False,
    }
    result["qualification_id"] = stable_id({"value_evidence_id": result["value_evidence_id"], "status": state,
                                               "provider_observation_id": provider.get("observation_id") if provider else None})
    return result
