"""Fail-closed reader linking cited official evidence to canonical observation records."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from financial_observations import read_observations, store_path

VERSION = "1.0.0"
MANIFEST_RELATIVE = Path("data") / "official-evidence" / "manifest.json"
CITATIONS_RELATIVE = Path("data") / "official-evidence" / "qualification_citations.jsonl"
MANIFEST_SCHEMA_VERSION = "1.0.0"
_SUPPORTED_SCOPES = {"consolidated"}
_RESOLVED_WARNINGS = {"statement_scope_unknown", "currency_or_scale_unknown"}
_REQUIRED_CITATION_FIELDS = ("citation_id", "observation_id", "evidence_id", "ticker", "reporting_frequency",
    "reporting_period", "raw_statement_type", "raw_item_id", "raw_value", "official_value",
    "statement_scope", "currency", "unit_scale")

# Metric-level source-presentation sign rules -- never ticker-specific. Each entry
# must be independently cited and tested before being added. Absent an entry here,
# verification requires an exact signed match; this module never compares by
# absolute value.
_SIGN_RULES: dict[tuple[str, str], dict[str, Any]] = {
    ("income_statement", "interest_expenses"): {
        "version": "v1",
        "citation": "Circular 202/2014/TT-BTC consolidated income statement (form B02-DN/HN) prints "
                    "'Trong do: Chi phi di vay' as an unsigned breakdown of Chi phi tai chinh; VCI's "
                    "income_statement raw_value sign convention for this item is negative.",
        "reconcile": lambda raw, official: raw == -official,
    },
}

# Generic derived-metric composition, mirroring cash_flow_debt_mapping._derive_total_debt's
# own component set. Not ticker-specific: applies to any ticker's canonical records.
_DERIVED_COMPONENTS: dict[str, tuple[str, ...]] = {
    "total_interest_bearing_debt": ("short_term_borrowings", "long_term_borrowings"),
}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_value(statement_type: str, raw_item_id: str, raw_value: Any, official_value: Any) -> tuple[bool, str]:
    rule = _SIGN_RULES.get((statement_type, raw_item_id))
    if rule is None:
        return raw_value == official_value, "exact"
    return bool(rule["reconcile"](raw_value, official_value)), rule["version"]


def _load_manifest(runtime_root: Path) -> dict[str, dict[str, Any]] | None:
    """Return {evidence_id: record} restricted to hash-verified, qualified evidence.

    None means the manifest itself is missing/malformed (fail closed globally).
    An empty dict is a distinct, valid state: the manifest parsed fine but no
    entry hash-verified -- callers must still report per-citation rejections.
    """
    path = runtime_root / MANIFEST_RELATIVE
    if not path.exists():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        return None
    verified: dict[str, dict[str, Any]] = {}
    for record in manifest.get("records", []):
        if not isinstance(record, dict):
            continue
        evidence_id, filename = record.get("evidence_id"), record.get("filename")
        if not evidence_id or not filename or record.get("qualification_state") != "qualified":
            continue
        document = path.parent / str(filename)
        if not document.is_file() or _sha256_file(document) != record.get("sha256"):
            continue
        verified[evidence_id] = record
    return verified


def _load_citation_rows(runtime_root: Path) -> list[Any] | None:
    """Return parsed JSONL rows, or None if the file is missing or malformed (fail closed)."""
    path = runtime_root / CITATIONS_RELATIVE
    if not path.exists():
        return None
    rows: list[Any] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return None
    return rows


def load_verified_citations(runtime_root: Path) -> dict[str, Any]:
    """Read and verify the evidence manifest and citation file; fails closed per record.

    Returns {"status": "available"|"unavailable", "version": VERSION,
    "by_observation_id": {observation_id: verified_citation}, "rejected": [...]}.
    A missing manifest or citations file yields an empty by_observation_id, so
    canonical projection behaves exactly as it did before this module existed.
    """
    evidence_by_id = _load_manifest(runtime_root)
    rows = _load_citation_rows(runtime_root)
    rejected: list[dict[str, Any]] = []
    if evidence_by_id is None or rows is None:
        return {"status": "unavailable", "version": VERSION, "by_observation_id": {}, "rejected": rejected}

    observations_by_id = {row["observation_id"]: row for row in read_observations(store_path(runtime_root))}

    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or not all(field in raw for field in _REQUIRED_CITATION_FIELDS):
            rejected.append({"citation": raw, "reason": "malformed_citation"})
            continue
        grouped.setdefault(raw["observation_id"], []).append(raw)

    by_observation: dict[str, dict[str, Any]] = {}
    for observation_id, citations in grouped.items():
        unique_by_content = {_hash(c): c for c in citations}
        if len(unique_by_content) > 1:
            rejected.append({"observation_id": observation_id, "reason": "conflicting_citations"})
            continue
        citation = next(iter(unique_by_content.values()))

        expected_id = _hash({"observation_id": citation["observation_id"], "evidence_id": citation["evidence_id"],
                              "raw_item_id": citation["raw_item_id"], "matched_value": citation["official_value"]})
        if citation["citation_id"] != expected_id:
            rejected.append({"observation_id": observation_id, "reason": "citation_id_not_deterministic"})
            continue

        evidence = evidence_by_id.get(citation["evidence_id"])
        if evidence is None:
            rejected.append({"observation_id": observation_id, "reason": "evidence_missing_or_hash_mismatch"})
            continue

        if citation["statement_scope"] not in _SUPPORTED_SCOPES:
            rejected.append({"observation_id": observation_id, "reason": "unsupported_scope"})
            continue

        observation = observations_by_id.get(observation_id)
        if observation is None:
            rejected.append({"observation_id": observation_id, "reason": "observation_id_not_found_in_current_store"})
            continue

        identity_fields = ("ticker", "reporting_frequency", "reporting_period", "raw_statement_type", "raw_item_id")
        if any(observation.get(field) != citation.get(field) for field in identity_fields):
            rejected.append({"observation_id": observation_id, "reason": "observation_identity_mismatch"})
            continue

        if observation.get("raw_value") != citation["raw_value"]:
            rejected.append({"observation_id": observation_id, "reason": "raw_value_drifted_from_citation"})
            continue

        ok, rule_version = _verify_value(citation["raw_statement_type"], citation["raw_item_id"], observation["raw_value"], citation["official_value"])
        if not ok:
            rejected.append({"observation_id": observation_id, "reason": "value_mismatch_after_sign_rule"})
            continue

        by_observation[observation_id] = {
            "observation_id": observation_id,
            "evidence_id": citation["evidence_id"],
            "citation_id": citation["citation_id"],
            "statement_scope": citation["statement_scope"],
            "currency": citation["currency"],
            "unit_scale": citation["unit_scale"],
            "match_method": citation.get("match_method", "exact_numeric_match"),
            "sign_rule_version": rule_version,
            "citation": citation.get("citation"),
            "qualification_version": VERSION,
            "verified_at": citation.get("verified_at"),
        }

    return {"status": "available" if by_observation else "unavailable", "version": VERSION,
            "by_observation_id": by_observation, "rejected": rejected}


def _clear_resolved_reason(reason: Any) -> str | None:
    if not reason:
        return None
    remaining = [warning for warning in str(reason).split(";") if warning not in _RESOLVED_WARNINGS]
    return ";".join(remaining) or None


def _enrich_direct(record: dict[str, Any], by_observation_id: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    if record.get("derivation_status") != "direct":
        return record
    observation_ids = record.get("observation_ids") or []
    if len(observation_ids) != 1:
        return record
    verified = by_observation_id.get(observation_ids[0])
    if verified is None:
        return record
    enriched = dict(record)
    enriched["statement_scope"] = verified["statement_scope"]
    enriched["currency"] = verified["currency"]
    enriched["unit_scale"] = verified["unit_scale"]
    enriched["quality_state"] = "available"
    enriched["reason"] = _clear_resolved_reason(record.get("reason"))
    enriched["evidence"] = {
        "evidence_id": verified["evidence_id"],
        "citation_id": verified["citation_id"],
        "match_method": verified["match_method"],
        "sign_rule_version": verified["sign_rule_version"],
        "citation": verified["citation"],
        "qualification_version": verified["qualification_version"],
    }
    return enriched


def _enrich_derived(record: dict[str, Any], siblings: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if record.get("derivation_status") != "derived":
        return record
    components = _DERIVED_COMPONENTS.get(record.get("canonical_metric"))
    if not components:
        return record
    period_identity = record.get("period_identity")
    matches: list[dict[str, Any]] = []
    for metric in components:
        sibling = next((s for s in siblings if s.get("canonical_metric") == metric
                         and s.get("period_identity") == period_identity
                         and s.get("derivation_status") == "direct"), None)
        if sibling is None or "evidence" not in sibling:
            return record
        matches.append(sibling)
    scopes, currencies, scales = ({m["statement_scope"] for m in matches}, {m["currency"] for m in matches}, {m["unit_scale"] for m in matches})
    if len(scopes) != 1 or len(currencies) != 1 or len(scales) != 1:
        return record
    enriched = dict(record)
    enriched["statement_scope"], enriched["currency"], enriched["unit_scale"] = scopes.pop(), currencies.pop(), scales.pop()
    enriched["quality_state"] = "available"
    enriched["reason"] = _clear_resolved_reason(record.get("reason"))
    enriched["observation_ids"] = sorted({obs_id for m in matches for obs_id in (m.get("observation_ids") or [])})
    enriched["evidence"] = {"components": [
        {"canonical_metric": m["canonical_metric"], "observation_ids": m.get("observation_ids"), **m["evidence"]}
        for m in matches
    ]}
    return enriched


def enrich_canonical_records(by_ticker: Mapping[str, list[dict[str, Any]]], runtime_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return a new by_ticker structure enriched only where citation linkage is exact.

    Never mutates the input records or observations.jsonl. Contains no
    ticker-specific logic: a record is enriched only when its backing
    observation_id (or, for a derived record, every required component's
    observation_id) has a verified, uniquely-cited, compatible-scope entry in
    qualification_citations.jsonl. Everything else passes through unchanged.
    """
    verified = load_verified_citations(runtime_root)
    by_observation_id = verified["by_observation_id"]
    if not by_observation_id:
        return {ticker: [dict(record) for record in records] for ticker, records in by_ticker.items()}
    result: dict[str, list[dict[str, Any]]] = {}
    for ticker, records in by_ticker.items():
        direct_pass = [_enrich_direct(dict(record), by_observation_id) for record in records]
        result[ticker] = [_enrich_derived(record, direct_pass) for record in direct_pass]
    return result
