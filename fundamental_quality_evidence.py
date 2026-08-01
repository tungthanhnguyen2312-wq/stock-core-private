"""Generic, source-qualified single-period earnings-quality / cash-conversion contract
(Phase 6A). Selected as the sole candidate model from {single-period earnings quality/cash
conversion, DuPont, Altman, Piotroski, Beneish} because it is the only one whose required
inputs are qualified from currently retained evidence without a verified comparative
period: DuPont needs average-balance semantics (a verified prior-period closing balance),
Piotroski/Beneish need verified comparative periods, and Altman needs balance-sheet
identities (EBIT, retained earnings, working capital) that are not qualified canonical
metrics for these tickers. Never derives yield, payout ratio, CAGR, return, a composite
score, a rating, or a recommendation. Always is_actionable=false.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

FUNDAMENTAL_QUALITY_EVIDENCE_SCHEMA_VERSION = "1.0.0"
MODEL_NAME = "earnings_quality_cash_conversion"
MODEL_VERSION = "1.0.0"

_APPLICABLE_ENTITY_TYPES = frozenset({"corporate"})
_REQUIRED_METRICS = ("operating_cash_flow", "net_income")
_REQUIRED_SCOPE = "consolidated"
_REQUIRED_PERIOD_TYPE = "annual"
MANIFEST_RELATIVE = Path("data") / "official-evidence" / "manifest.json"

_STANDING_LIMITATIONS: tuple[str, ...] = (
    "This contract reports a single-period cash-conversion ratio and accrual gap only; it "
    "does not derive a trend, growth rate, rating, score, ranking, or recommendation.",
    "net_income is income attributable to parent-company shareholders (the same convention "
    "used elsewhere in this system's ratio analysis), not total consolidated net income "
    "including non-controlling interest.",
    "is_actionable is always false.",
)


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _load_manifest_hashes(runtime_root: Path) -> dict[str, str] | None:
    """Resolve evidence_id -> sha256 from the retained manifest. Returns None (fail closed)
    if the manifest is missing or malformed."""
    manifest_path = runtime_root / MANIFEST_RELATIVE
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    records = manifest.get("records") if isinstance(manifest, dict) else None
    if not isinstance(records, list):
        return None
    hashes: dict[str, str] = {}
    for record in records:
        if isinstance(record, dict) and record.get("evidence_id") and record.get("sha256"):
            hashes[record["evidence_id"]] = record["sha256"]
    return hashes


def _candidates(records: list[Any], metric: str) -> dict[str, list[dict[str, Any]]]:
    """Qualified (quality_state=available, required scope/period_type) candidates for one
    metric, grouped by reporting period. A period with more than one candidate is a
    conflicting-observation case, surfaced to the caller rather than silently resolved."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("canonical_metric") != metric:
            continue
        if record.get("quality_state") != "available":
            continue
        if record.get("statement_scope") != _REQUIRED_SCOPE:
            continue
        period_identity = record.get("period_identity")
        if not isinstance(period_identity, dict) or period_identity.get("period_type") != _REQUIRED_PERIOD_TYPE:
            continue
        period = period_identity.get("period")
        if not period:
            continue
        grouped.setdefault(period, []).append(record)
    return grouped


def _qualify_metric_at_period(
    records: list[Any], metric: str, period: str, manifest_hashes: dict[str, str] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Returns (accepted_record_or_None, input_entry). input_entry always carries the full
    per-input identity fields the contract requires, qualified or not."""
    grouped = _candidates(records, metric)
    candidates = grouped.get(period, [])

    def _entry(**overrides: Any) -> dict[str, Any]:
        base = {
            "canonical_field_identity": metric, "reporting_period": period,
            "reporting_frequency": _REQUIRED_PERIOD_TYPE, "statement_scope": _REQUIRED_SCOPE,
            "currency": None, "scale": None, "observation_id": None, "citation_id": None,
            "evidence_id": None, "source_hash": None, "qualification_status": "unqualified",
            "rejection_reason": None,
        }
        base.update(overrides)
        return base

    if not candidates:
        return None, _entry(rejection_reason="no_qualified_consolidated_annual_record_for_period")
    if len(candidates) > 1:
        values = {record.get("value") for record in candidates}
        reason = "conflicting_observations_same_period" if len(values) > 1 else "duplicate_qualified_observations_same_period"
        return None, _entry(rejection_reason=reason)

    record = candidates[0]
    if record.get("derivation_status") != "direct":
        return None, _entry(
            currency=record.get("currency"), scale=record.get("unit_scale"),
            rejection_reason="unsupported_derivation_status_for_this_model",
        )
    evidence = record.get("evidence") if isinstance(record.get("evidence"), dict) else {}
    citation_id = evidence.get("citation_id")
    evidence_id = evidence.get("evidence_id")
    observation_ids = record.get("observation_ids")
    if not citation_id or not evidence_id or not isinstance(observation_ids, list) or not observation_ids:
        return None, _entry(
            currency=record.get("currency"), scale=record.get("unit_scale"),
            rejection_reason="missing_citation_lineage",
        )
    source_hash = (manifest_hashes or {}).get(evidence_id)
    if not source_hash:
        return None, _entry(
            currency=record.get("currency"), scale=record.get("unit_scale"),
            observation_id=observation_ids, citation_id=citation_id, evidence_id=evidence_id,
            rejection_reason="evidence_hash_unresolvable_against_manifest",
        )
    if record.get("value") is None:
        return None, _entry(
            currency=record.get("currency"), scale=record.get("unit_scale"),
            observation_id=observation_ids, citation_id=citation_id, evidence_id=evidence_id,
            source_hash=source_hash, rejection_reason="value_missing",
        )
    return record, _entry(
        currency=record.get("currency"), scale=record.get("unit_scale"),
        observation_id=observation_ids, citation_id=citation_id, evidence_id=evidence_id,
        source_hash=source_hash, qualification_status="qualified", rejection_reason=None,
    )


def _blocked(ticker: str, entity_type: str | None, applicability: str, status: str,
             blocking_reasons: list[str], inputs: list[dict[str, Any]],
             data_warnings: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": FUNDAMENTAL_QUALITY_EVIDENCE_SCHEMA_VERSION,
        "ticker": ticker,
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "status": status,
        "applicability": applicability,
        "reporting_period": None,
        "statement_scope": None,
        "inputs": inputs,
        "metrics": {},
        "data_warnings": data_warnings or [],
        "blocking_reasons": blocking_reasons,
        "limitations": list(_STANDING_LIMITATIONS),
        "provenance": {
            "source": "financial_canonical",
            "evidence_manifest_path": MANIFEST_RELATIVE.as_posix(),
        },
        "is_actionable": False,
    }


def build_fundamental_quality_evidence_for_ticker(
    ticker: str,
    entity_type: str | None,
    financial_canonical: Mapping[str, Any] | None,
    financial_period_coverage: Mapping[str, Any] | None,
    runtime_root: Path,
) -> dict[str, Any]:
    """Build the fundamental_quality_evidence contract for one ticker from already-qualified
    canonical financial records only. Generic across tickers and entity types: identical code
    path regardless of which ticker is passed, no per-ticker branching.

    Reaches status="available" only when operating_cash_flow and net_income both have exactly
    one hash-verified (quality_state=available), consolidated, annual record at a period that
    equals financial_period_coverage.latest_verified_period, with matching currency/scale,
    complete citation/evidence/observation lineage, and a resolvable manifest source hash.
    Fails closed to status="unavailable"/"conflict" otherwise, recording a rejection_reason
    per input. is_actionable is always False.
    """
    if entity_type not in _APPLICABLE_ENTITY_TYPES:
        reason = "entity_type_unknown" if entity_type in (None, "unknown") else f"entity_type_not_applicable:{entity_type}"
        return _blocked(ticker, entity_type, "not_applicable", "not_applicable", [reason], [])

    records = (financial_canonical or {}).get("records") if _is_mapping(financial_canonical) else None
    if not isinstance(records, list) or not records:
        return _blocked(
            ticker, entity_type, "applicable", "unavailable",
            ["financial_canonical_missing_or_empty"],
            [{"canonical_field_identity": m, "reporting_period": None, "reporting_frequency": None,
              "statement_scope": None, "currency": None, "scale": None, "observation_id": None,
              "citation_id": None, "evidence_id": None, "source_hash": None,
              "qualification_status": "unqualified", "rejection_reason": "financial_canonical_missing_or_empty"}
             for m in _REQUIRED_METRICS],
        )

    verified_period = (financial_period_coverage or {}).get("latest_verified_period") if _is_mapping(financial_period_coverage) else None
    if not verified_period:
        return _blocked(
            ticker, entity_type, "applicable", "unavailable",
            ["no_verified_financial_period"],
            [{"canonical_field_identity": m, "reporting_period": None, "reporting_frequency": None,
              "statement_scope": None, "currency": None, "scale": None, "observation_id": None,
              "citation_id": None, "evidence_id": None, "source_hash": None,
              "qualification_status": "unqualified", "rejection_reason": "no_verified_financial_period"}
             for m in _REQUIRED_METRICS],
        )

    manifest_hashes = _load_manifest_hashes(runtime_root)

    resolved: dict[str, dict[str, Any]] = {}
    input_entries: list[dict[str, Any]] = []
    for metric in _REQUIRED_METRICS:
        record, entry = _qualify_metric_at_period(records, metric, verified_period, manifest_hashes)
        entry["ticker"] = ticker
        input_entries.append(entry)
        if record is not None:
            resolved[metric] = record

    missing = [m for m in _REQUIRED_METRICS if m not in resolved]
    if missing:
        conflict = any(e["rejection_reason"] == "conflicting_observations_same_period" for e in input_entries)
        status = "conflict" if conflict else "unavailable"
        return _blocked(
            ticker, entity_type, "applicable", status,
            [f"{e['canonical_field_identity']}:{e['rejection_reason']}" for e in input_entries if e["qualification_status"] != "qualified"],
            input_entries,
        )

    currencies = {resolved[m].get("currency") for m in _REQUIRED_METRICS}
    scales = {resolved[m].get("unit_scale") for m in _REQUIRED_METRICS}
    if len(currencies) != 1 or len(scales) != 1:
        return _blocked(
            ticker, entity_type, "applicable", "conflict",
            ["currency_or_scale_mismatch_across_required_inputs"],
            input_entries,
        )

    operating_cash_flow = resolved["operating_cash_flow"]["value"]
    net_income = resolved["net_income"]["value"]
    if net_income == 0:
        return _blocked(
            ticker, entity_type, "applicable", "unavailable",
            ["net_income_zero_denominator"],
            input_entries,
        )

    metrics = {
        "cash_conversion_ratio": operating_cash_flow / net_income,
        "operating_cash_flow_less_net_income": operating_cash_flow - net_income,
    }
    data_warnings: list[str] = []
    if net_income < 0:
        data_warnings.append("net_income_negative_ratio_sign_reflects_a_loss_period_not_a_data_error")

    return {
        "schema_version": FUNDAMENTAL_QUALITY_EVIDENCE_SCHEMA_VERSION,
        "ticker": ticker,
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "status": "available",
        "applicability": "applicable",
        "reporting_period": verified_period,
        "statement_scope": _REQUIRED_SCOPE,
        "inputs": input_entries,
        "metrics": metrics,
        "data_warnings": data_warnings,
        "blocking_reasons": [],
        "limitations": list(_STANDING_LIMITATIONS),
        "provenance": {
            "source": "financial_canonical",
            "evidence_manifest_path": MANIFEST_RELATIVE.as_posix(),
            "formula": "cash_conversion_ratio = operating_cash_flow / net_income; "
                       "operating_cash_flow_less_net_income = operating_cash_flow - net_income",
        },
        "is_actionable": False,
    }
