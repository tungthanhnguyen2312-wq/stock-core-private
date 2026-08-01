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

_CAPITAL_REQUIRED_METRICS = (
    "cash_and_equivalents", "short_term_borrowings", "long_term_borrowings",
    "total_debt", "shareholders_equity",
)
_CAPITAL_OPTIONAL_METRIC = "minority_interest_equity"
_DERIVED_COMPONENTS = {
    "total_debt": ("short_term_borrowings", "long_term_borrowings"),
    "shareholders_equity": ("total_equity", "minority_interest_equity"),
}

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


def _qualify_capital_metric_at_period(
    records: list[Any], metric: str, period: str, manifest_hashes: dict[str, str] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Qualify one historical capital-structure identity, including only the two
    established reconciled derivations whose components carry complete evidence lineage."""
    candidates = _candidates(records, metric).get(period, [])
    entry = {
        "canonical_field_identity": metric, "reporting_period": period,
        "reporting_frequency": _REQUIRED_PERIOD_TYPE, "statement_scope": _REQUIRED_SCOPE,
        "currency": None, "scale": None, "value": None, "observation_id": None,
        "citation_id": None, "evidence_id": None, "source_hash": None,
        "qualification_status": "unqualified", "rejection_reason": None,
    }
    if not candidates:
        entry["rejection_reason"] = "no_qualified_consolidated_annual_record_for_period"
        return None, entry
    if len(candidates) != 1:
        entry["rejection_reason"] = "conflicting_observations_same_period"
        return None, entry
    record = candidates[0]
    entry.update({"currency": record.get("currency"), "scale": record.get("unit_scale"), "value": record.get("value")})
    if record.get("value") is None:
        entry["rejection_reason"] = "value_missing"
        return None, entry
    if record.get("derivation_status") == "direct":
        evidence = record.get("evidence") if isinstance(record.get("evidence"), Mapping) else {}
        evidence_id, citation_id, observation_ids = evidence.get("evidence_id"), evidence.get("citation_id"), record.get("observation_ids")
        if not evidence_id or not citation_id or not isinstance(observation_ids, list) or not observation_ids:
            entry["rejection_reason"] = "missing_citation_lineage"
            return None, entry
        source_hash = (manifest_hashes or {}).get(evidence_id)
        if not source_hash:
            entry.update({"evidence_id": evidence_id, "citation_id": citation_id, "observation_id": observation_ids})
            entry["rejection_reason"] = "evidence_hash_unresolvable_against_manifest"
            return None, entry
        entry.update({"observation_id": observation_ids, "citation_id": citation_id, "evidence_id": evidence_id, "source_hash": source_hash, "qualification_status": "qualified"})
        return record, entry
    expected = _DERIVED_COMPONENTS.get(metric)
    components = ((record.get("evidence") or {}).get("components") if isinstance(record.get("evidence"), Mapping) else None)
    if record.get("derivation_status") != "derived" or not expected or not isinstance(components, list):
        entry["rejection_reason"] = "unsupported_derivation_status_for_capital_structure"
        return None, entry
    by_metric = {component.get("canonical_metric"): component for component in components if isinstance(component, Mapping)}
    if set(by_metric) != set(expected):
        entry["rejection_reason"] = "derived_component_identity_mismatch"
        return None, entry
    component_entries = []
    for identity in expected:
        component = by_metric[identity]
        compatible = (component.get("period_identity", {}).get("period") == period and
                      component.get("period_identity", {}).get("period_type") == _REQUIRED_PERIOD_TYPE and
                      component.get("statement_scope") == _REQUIRED_SCOPE and
                      component.get("currency") == record.get("currency") and
                      component.get("unit_scale") == record.get("unit_scale"))
        evidence_id, citation_id, observation_ids = component.get("evidence_id"), component.get("citation_id"), component.get("observation_ids")
        source_hash = (manifest_hashes or {}).get(evidence_id) if evidence_id else None
        if not compatible or component.get("value") is None or not citation_id or not isinstance(observation_ids, list) or not observation_ids or not source_hash:
            entry["rejection_reason"] = "derived_component_lineage_or_compatibility_unqualified"
            return None, entry
        component_entries.append({"canonical_field_identity": identity, "value": component["value"], "observation_id": observation_ids, "citation_id": citation_id, "evidence_id": evidence_id, "source_hash": source_hash})
    entry.update({"observation_id": record.get("observation_ids"), "qualification_status": "qualified", "derivation": "compatible_canonical_components", "component_provenance": component_entries})
    return record, entry


def build_historical_capital_structure_analysis(
    ticker: str, entity_type: str | None, financial_canonical: Mapping[str, Any] | None,
    financial_period_coverage: Mapping[str, Any] | None, financial_freshness: Mapping[str, Any] | None,
    runtime_root: Path,
) -> dict[str, Any]:
    """Evidence-qualified, single-period capital structure only. It never consumes shares
    or market data and is deliberately non-actionable."""
    warnings = ["price_basis_unknown_or_unverified", "volume_basis_unknown_or_unverified", "current_shares_unqualified"]
    base = {"schema_version": "1.0.0", "analysis": "historical_capital_structure", "ticker": ticker,
            "historical_only": True, "market_dependent": False, "is_actionable": False,
            "applicability": "applicable" if entity_type in _APPLICABLE_ENTITY_TYPES else "not_applicable",
            "status": "unavailable", "reporting_period": None, "period_end": None,
            "publication_timestamp": None, "statement_scope": _REQUIRED_SCOPE, "currency": None,
            "scale": None, "inputs": [], "metrics": {}, "data_warnings": warnings,
            "blocking_reasons": [], "provenance": {"source": "financial_canonical", "evidence_manifest_path": MANIFEST_RELATIVE.as_posix()}}
    if entity_type not in _APPLICABLE_ENTITY_TYPES:
        base["blocking_reasons"] = ["entity_type_not_applicable_for_nonfinancial_capital_structure"]
        return base
    period = (financial_period_coverage or {}).get("latest_verified_period") if isinstance(financial_period_coverage, Mapping) else None
    freshness = financial_freshness if isinstance(financial_freshness, Mapping) else {}
    if not period:
        base["blocking_reasons"] = ["no_verified_financial_period"]
        return base
    base.update({"reporting_period": period, "period_end": freshness.get("financial_period_end"),
                 "publication_timestamp": freshness.get("source_publication_timestamp")})
    if freshness.get("publication_timestamp_qualified") is not True:
        base["blocking_reasons"].append("financial_publication_timestamp_unqualified")
    records = (financial_canonical or {}).get("records") if isinstance(financial_canonical, Mapping) else None
    if not isinstance(records, list):
        base["blocking_reasons"].append("financial_canonical_missing_or_empty")
        return base
    hashes = _load_manifest_hashes(runtime_root)
    resolved: dict[str, dict[str, Any]] = {}
    for metric in _CAPITAL_REQUIRED_METRICS + (_CAPITAL_OPTIONAL_METRIC,):
        record, entry = _qualify_capital_metric_at_period(records, metric, period, hashes)
        entry["ticker"] = ticker
        base["inputs"].append(entry)
        if record is not None:
            resolved[metric] = record
    qualified = [record for record in resolved.values()]
    if qualified:
        currencies, scales = {r.get("currency") for r in qualified}, {r.get("unit_scale") for r in qualified}
        if len(currencies) == 1 and len(scales) == 1:
            base.update({"currency": next(iter(currencies)), "scale": next(iter(scales))})
        else:
            base["blocking_reasons"].append("currency_or_scale_mismatch_across_capital_inputs")
    def metric(value: Any, status: str, numerator: str, denominator: str | None = None, reason: str | None = None) -> dict[str, Any]:
        return {"value": value, "qualification_status": status, "numerator_identity": numerator,
                "denominator_identity": denominator, "blocking_reason": reason}
    debt, cash, equity = (resolved.get("total_debt"), resolved.get("cash_and_equivalents"), resolved.get("shareholders_equity"))
    debt_value = debt.get("value") if debt else None
    cash_value = cash.get("value") if cash else None
    equity_value = equity.get("value") if equity else None
    def compatible(*records: dict[str, Any] | None) -> bool:
        present = [record for record in records if record is not None]
        return len(present) == len(records) and len({record.get("currency") for record in present}) == 1 and len({record.get("unit_scale") for record in present}) == 1
    base["metrics"]["gross_debt"] = metric(debt_value, "qualified" if debt else "unavailable", "total_debt", reason=None if debt else "total_debt_unqualified")
    base["metrics"]["cash"] = metric(cash_value, "qualified" if cash else "unavailable", "cash_and_equivalents", reason=None if cash else "cash_and_equivalents_unqualified")
    debt_cash_compatible = compatible(debt, cash)
    net_debt = debt_value - cash_value if debt_cash_compatible else None
    base["metrics"]["net_debt"] = metric(net_debt, "qualified" if net_debt is not None else "unavailable", "total_debt_less_cash_and_equivalents", reason=None if net_debt is not None else "total_debt_or_cash_currency_or_scale_unqualified")
    denominator_valid = equity_value is not None and equity_value > 0
    ratios = (
        ("debt_to_equity", debt_value, "total_debt", (debt, equity)),
        ("net_debt_to_equity", net_debt, "total_debt_less_cash_and_equivalents", (debt, cash, equity)),
        ("minority_interest_to_equity", (resolved.get(_CAPITAL_OPTIONAL_METRIC) or {}).get("value"), _CAPITAL_OPTIONAL_METRIC, (resolved.get(_CAPITAL_OPTIONAL_METRIC), equity)),
    )
    for name, numerator, identity, inputs in ratios:
        status = "qualified" if numerator is not None and denominator_valid and compatible(*inputs) else "unavailable"
        reason = None if status == "qualified" else ("shareholders_equity_nonpositive_or_unqualified" if not denominator_valid else f"{identity}_currency_or_scale_unqualified")
        base["metrics"][name] = metric(numerator / equity_value if status == "qualified" else None, status, identity, "shareholders_equity", reason)
    debt_denominator_valid = debt_value is not None and debt_value > 0 and debt_cash_compatible
    base["metrics"]["cash_to_debt"] = metric(cash_value / debt_value if cash_value is not None and debt_denominator_valid else None, "qualified" if cash_value is not None and debt_denominator_valid else "unavailable", "cash_and_equivalents", "total_debt", None if cash_value is not None and debt_denominator_valid else "total_debt_currency_scale_nonpositive_or_unqualified")
    unavailable = [name for name, value in base["metrics"].items() if value["qualification_status"] != "qualified"]
    base["status"] = "available" if not unavailable and not base["blocking_reasons"] else "partial"
    base["blocking_reasons"] += sorted({value["blocking_reason"] for value in base["metrics"].values() if value["blocking_reason"]})
    return base


def build_historical_fundamental_brief(
    ticker: str, earnings_quality: Mapping[str, Any] | None,
    capital_structure: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compose existing qualified historical contracts without re-resolving any source
    identity or allowing the result to affect current-market readiness."""
    capital = capital_structure if isinstance(capital_structure, Mapping) else {}
    earnings = earnings_quality if isinstance(earnings_quality, Mapping) else {}
    warnings = list(capital.get("data_warnings") or [])
    for warning in ("price_basis_unknown_or_unverified", "volume_basis_unknown_or_unverified", "current_shares_unqualified"):
        if warning not in warnings:
            warnings.append(warning)
    facts: list[dict[str, Any]] = []
    missing: list[str] = [
        "current qualified price basis is required for any market-dependent conclusion",
        "current qualified volume basis is required for market-liquidity conclusions",
        "current shares outstanding with an effective-date bridge is required for market value and per-share current-market conclusions",
        "FY2023 comparable verified evidence is required for comparative-period conclusions",
    ]
    capital_metrics = capital.get("metrics") if isinstance(capital.get("metrics"), Mapping) else {}
    for identity, item in capital_metrics.items():
        if isinstance(item, Mapping) and item.get("qualification_status") == "qualified":
            facts.append({"identity": identity, "value": item.get("value"), "source_contract": "historical_capital_structure",
                          "numerator_identity": item.get("numerator_identity"), "denominator_identity": item.get("denominator_identity")})
        elif isinstance(item, Mapping):
            warnings.append(f"{identity}:{item.get('blocking_reason') or 'unqualified'}")
    earnings_metrics = earnings.get("metrics") if earnings.get("status") == "available" and isinstance(earnings.get("metrics"), Mapping) else {}
    for identity, value in earnings_metrics.items():
        facts.append({"identity": identity, "value": value, "source_contract": "fundamental_quality_evidence"})
    if not earnings_metrics:
        missing.append("qualified FY2024 earnings-quality metrics are unavailable")
    if not capital_metrics:
        missing.append("qualified FY2024 capital-structure metrics are unavailable")
    supported_inferences: list[dict[str, Any]] = []
    net_debt = capital_metrics.get("net_debt") if isinstance(capital_metrics.get("net_debt"), Mapping) else None
    if net_debt and net_debt.get("qualification_status") == "qualified":
        direction = "positive" if net_debt.get("value") > 0 else "negative" if net_debt.get("value") < 0 else "zero"
        supported_inferences.append({"statement": f"Net debt was {direction} for the reported period.",
                                     "supporting_metrics": ["historical_capital_structure.net_debt"]})
    cash_to_debt = capital_metrics.get("cash_to_debt") if isinstance(capital_metrics.get("cash_to_debt"), Mapping) else None
    if cash_to_debt and cash_to_debt.get("qualification_status") == "qualified":
        relationship = "exceeded" if cash_to_debt.get("value") > 1 else "did not exceed" if cash_to_debt.get("value") < 1 else "equalled"
        supported_inferences.append({"statement": f"Cash {relationship} gross debt for the reported period.",
                                     "supporting_metrics": ["historical_capital_structure.cash", "historical_capital_structure.gross_debt", "historical_capital_structure.cash_to_debt"]})
    return {
        "schema_version": "1.0.0", "ticker": ticker, "status": "available" if facts else "partial",
        "historical_only": True, "market_dependent": False, "is_actionable": False,
        "reporting_period": capital.get("reporting_period"), "publication_timestamp": capital.get("publication_timestamp"),
        "statement_scope": capital.get("statement_scope"), "currency": capital.get("currency"), "scale": capital.get("scale"),
        "facts": facts, "data_warnings": sorted(set(warnings)), "supported_inferences": supported_inferences,
        "hypotheses": [], "missing_evidence": missing,
        "invalidation_conditions": [
            "A change to the FY2024 reporting period, consolidated scope, currency, scale, canonical identity, citation, source hash, or restatement state invalidates this brief.",
            "Any market-dependent conclusion remains invalid until price and volume basis and current shares are qualified.",
        ],
        "provenance_references": {"earnings_quality": "fundamental_quality_evidence", "capital_structure": "historical_capital_structure"},
    }


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
