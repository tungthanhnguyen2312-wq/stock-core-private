"""Opt-in, offline company economics observations; no thesis or capital decision.

Consumes the standing qualified official overlay, not raw statement rows. Directional
structural flags are reserved/UNKNOWN until an existing source contract qualifies
multi-year economics. Current financial or investor-lens states do not provide it.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

import market_wide_current_fundamental_research as fundamental
from stocklookup_core.portfolio.portfolio_opportunity_cost_research import _strategic

CONTRACT_VERSION = "long_term_company_economics_evidence/v1"
STATUSES = ("KNOWN", "PARTIALLY_KNOWN", "UNKNOWN", "NOT_APPLICABLE")
DIMENSIONS = (
    "business_durability", "revenue_profit_economics", "balance_sheet_resilience",
    "cash_generation_reinvestment", "earnings_quality", "cyclicality",
    "management_capital_allocation", "valuation_fitness", "structural_thesis_invalidation",
)
FLAGS = (
    "STRUCTURAL_THESIS_SUPPORTED", "STRUCTURAL_THESIS_CHALLENGED",
    "INSUFFICIENT_STRUCTURAL_EVIDENCE", "CYCLICAL_RECOVERY_POSSIBLE",
    "EARNINGS_QUALITY_UNCERTAIN", "VALUATION_UNQUALIFIED",
)
METRIC_DIMENSIONS = {
    "revenue": "revenue_profit_economics", "net_income": "revenue_profit_economics",
    "attributable_net_income": "revenue_profit_economics",
    "total_assets": "balance_sheet_resilience", "shareholders_equity": "balance_sheet_resilience",
    "cash_and_equivalents": "balance_sheet_resilience",
    "short_term_interest_bearing_debt": "balance_sheet_resilience",
    "long_term_interest_bearing_debt": "balance_sheet_resilience",
    "operating_cash_flow": "cash_generation_reinvestment",
    "provision_charge_or_reversal_adjustment": "earnings_quality",
    "investment_property_disposal_result": "earnings_quality",
}
BOUNDARIES = (
    "Exact financial observations do not establish 5–20 year business durability or a structural thesis.",
    "Missing evidence is UNKNOWN, never evidence of economic weakness or clean earnings.",
    "H1 stays H1: no annualization, TTM, period joining or USD/VND conversion.",
    "Reported provisions are descriptive components; recurrence and accounting treatment are unproven.",
    "No automatic provision or impairment add-back, normalized economics or normalized EPS.",
    "Tactical adversity and sector leadership do not establish or invalidate company quality.",
    "Relative valuation fitness is method-scoped research; strict shares and valuation remain unqualified here.",
    "Existing thesis lenses and Portfolio Opportunity Cost retain their own states and decisions.",
)
NORMALIZATION_BLOCKERS = (
    "RECURRENCE_TREATMENT_UNPROVEN", "RECONCILED_ACCOUNTING_PRESENTATION_UNPROVEN",
    "ADJUSTMENT_SIGN_AND_DIRECTION_UNPROVEN", "APPROPRIATE_DENOMINATOR_UNQUALIFIED",
)
EVIDENCE_GAPS = {
    "business_durability": ["SOURCE_BOUND_MULTI_YEAR_BUSINESS_DURABILITY_NOT_AVAILABLE"],
    "revenue_profit_economics": ["COMPARABLE_MULTI_YEAR_ECONOMICS_AND_RECURRENCE_UNPROVEN"],
    "balance_sheet_resilience": ["CURRENT_CASH_DEBT_AND_BALANCE_SHEET_RESILIENCE_UNPROVEN"],
    "cash_generation_reinvestment": ["CURRENT_OPERATING_FLOW_REINVESTMENT_AND_ACCOUNTING_BRIDGE_UNPROVEN"],
    "earnings_quality": list(NORMALIZATION_BLOCKERS),
    "cyclicality": ["ISSUER_SPECIFIC_CYCLE_AND_RECOVERY_EVIDENCE_NOT_AVAILABLE"],
    "management_capital_allocation": ["SOURCE_BOUND_MANAGEMENT_AND_REINVESTMENT_RECORD_NOT_AVAILABLE"],
    "valuation_fitness": ["QUALIFIED_RELATIVE_METHOD_NOT_SUPPLIED", "STRICT_SHARE_CONTINUITY_NOT_SUPPLIED"],
    "structural_thesis_invalidation": ["SOURCE_OWNED_STRUCTURAL_INVALIDATION_CONDITIONS_NOT_SUPPLIED"],
}

# Independent consumer contract for a source-bound evidence_item/v1 reference.
# These closed schema checks do not construct items, reduce axes/lenses, verify
# T0 snapshots, or grant any directional authority. No offline engine is imported.
_CONTEXT_FIELDS = frozenset({
    "contract_version", "subject", "source", "axis", "sub_axis", "role", "lens_binding",
    "state", "unknown_class", "reason_codes", "blocker_codes", "knowledge_stage",
    "seal_reference", "horizon", "correlation_group", "canonical_evidence_key",
    "common_cause_key", "freshness", "basis", "authority_ceiling", "fitness", "relations",
    "confirmation_pointers", "invalidation_pointers", "coverage", "factual_values",
    "facts_present", "materiality", "non_voting", "is_actionable", "artifact_identity", "artifact_sha256",
})
_CONTEXT_ENUMS = {
    "contract_version": {"evidence_item/v1"},
    "state": {"SUPPORTS", "OPPOSES", "NEUTRAL", "MIXED", "UNKNOWN", "NOT_APPLICABLE"},
    "role": {"PRIMARY", "SECONDARY", "CONTEXT"},
    "axis": {"TECHNICAL", "VOLUME", "PARTICIPANT_FLOW", "FUNDAMENTAL", "VALUATION",
             "CORPORATE_FORWARD", "MACRO_SECTOR", "LIQUIDITY_PORTFOLIO", "EVIDENCE_QUALITY"},
    "knowledge_stage": {"T0_SEALED", "POST_T0_ENRICHED"},
}
_UNKNOWN_CLASSES = {"MISSING", "IMMATURE", "UNQUALIFIED", "STALE", "POLICY_NOT_AUTHORIZED",
                    "PRIMARY_EVIDENCE_MISSING", "CONTEXT_ONLY", "HIGHER_TIMEFRAME_UNKNOWN",
                    "UNRESOLVED", "AUTHORITY_LIMITED"}
_FORBIDDEN_KEYS = {"score", "weight", "confidence", "probability", "rank", "rating", "conviction", "target",
                   "priorityscore", "overall", "overallscore", "overallrating", "certainty", "likelihood",
                   "recommendation", "buysell", "signalstrength", "stars", "grade", "alphaestimate", "forecastreturn"}
_FORBIDDEN_TOKENS = {"score", "scores", "weight", "weights", "weighted", "confidence", "probability",
                     "probabilities", "rank", "ranking", "rating", "conviction", "target", "certainty", "likelihood"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _seal(value: Mapping[str, Any], kind: str) -> dict[str, Any]:
    body = {key: item for key, item in value.items() if key not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(_canonical(body).encode("utf8")).hexdigest()
    return {**body, "artifact_sha256": digest, "artifact_identity": kind + ":" + digest}


def _verify_identity(value: Mapping[str, Any], kind: str) -> None:
    expected = _seal(value, kind)
    if any(value.get(key) != expected[key] for key in ("artifact_identity", "artifact_sha256")):
        raise ValueError("ECONOMICS_CONTENT_IDENTITY_INVALID:" + kind)


def _scan_forbidden(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            words = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(key)).lower()
            if ("".join(re.findall(r"[a-z]+", words)) in _FORBIDDEN_KEYS
                    or set(re.findall(r"[a-z]+", words)) & _FORBIDDEN_TOKENS):
                raise ValueError("ECONOMICS_FORBIDDEN_JUDGMENT_FIELD:" + path + "/" + str(key))
            _scan_forbidden(child, path + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, path + "/" + str(index))
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("ECONOMICS_NON_FINITE_FACT:" + path)


def _verify_context_item(item: Mapping[str, Any]) -> None:
    """Validate an existing serialized reference; do not evaluate its thesis."""
    _scan_forbidden(item)
    _verify_identity(item, "evidence_item/v1")
    def require(condition: bool, code: str) -> None:
        if not condition:
            raise ValueError("ECONOMICS_CONTEXT_" + code)
    require(set(item) == _CONTEXT_FIELDS and set(item["source"]) == {"identity", "contract_version", "pointer"}, "SCHEMA_UNSUPPORTED")
    require(set(item["fitness"]) == {"fact_eligible", "direction_eligible"}
            and all(type(v) is bool for v in item["fitness"].values()), "FITNESS_BOOLEAN_REQUIRED")
    require(all(isinstance(item[key], str) and item[key] for key in (
        "correlation_group", "canonical_evidence_key", "common_cause_key", "horizon")), "CORRELATION_BINDING_REQUIRED")
    for key, vocabulary in _CONTEXT_ENUMS.items():
        require(item[key] in vocabulary, "UNMAPPED_VOCABULARY:" + key)
    require(set(item["lens_binding"]) == {"LONG_TERM_INVESTOR", "SHORT_TERM_INVESTOR"}
            and all(role in _CONTEXT_ENUMS["role"] for role in item["lens_binding"].values()), "LENS_BINDING_INVALID")
    require(item["unknown_class"] in _UNKNOWN_CLASSES if item["state"] == "UNKNOWN"
            else item["unknown_class"] is None, "UNKNOWN_CLASS_INVALID")
    require(all(item["source"].values()), "SOURCE_POINTER_REQUIRED")
    require(item["non_voting"] is True and item["is_actionable"] is False, "ACTION_BOUNDARY")
    if item["fitness"]["direction_eligible"]:
        require(item["axis"] not in {"VOLUME", "PARTICIPANT_FLOW", "CORPORATE_FORWARD", "LIQUIDITY_PORTFOLIO", "EVIDENCE_QUALITY"}, "FACTS_ONLY_AXIS")
        require(item["sub_axis"] not in {"patterns", "volatility", "morphology", "technical_native_volume_copy"}, "CONTEXT_PRIMITIVE")
        if "RAW_AS_TRADED" in _canonical(item["basis"]):
            require(isinstance(item["basis"], dict) and (item["basis"].get("corporate_action_comparability") or {}).get("comparability") == "PIT_NORMALIZED", "RAW_DIRECTION_AUTHORITY_INSUFFICIENT")
        require(item["state"] in {"SUPPORTS", "OPPOSES", "NEUTRAL", "MIXED"}
                and item["freshness"] in {"CURRENT_SESSION", "FRESH_COMPLETED_PERIOD", "CURRENT_REPORTING_PERIOD"}
                and item["fitness"]["fact_eligible"], "DIRECTION_FITNESS_INVALID")
        require(item["role"] != "CONTEXT" or any(role != "CONTEXT" for role in item["lens_binding"].values()), "CONTEXT_CANNOT_VOTE")
    if item["knowledge_stage"] == "T0_SEALED":
        require(bool(item["seal_reference"]) and "RETROSPECTIVE" not in _canonical(item["basis"]), "T0_SEAL_OR_BASIS_INVALID")
    for fact in item["factual_values"]:
        require(set(fact) == {"name", "value", "semantic", "unit", "fitness", "source_pointer"}, "FACT_METADATA_REQUIRED")
        require(bool(fact["semantic"] and fact["unit"] and fact["source_pointer"]), "FACT_PROVENANCE_REQUIRED")
        _scan_forbidden({fact["name"]: fact["value"], fact["semantic"]: None, fact["unit"]: None})


def _time(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result
    except (ValueError, TypeError) as exc:
        raise ValueError("EXPLICIT_TIMEZONE_BEARING_KNOWLEDGE_TIME_REQUIRED") from exc


def _temporal_reasons(row: Mapping[str, Any], boundary: datetime) -> list[str]:
    reasons = []
    for key in ("knowledge_available_at", "observed_at"):
        try:
            if _time(row.get(key)) > boundary:
                reasons.append(key.upper() + "_AFTER_CUTOFF")
        except ValueError:
            reasons.append(key.upper() + "_INVALID")
    # Date-only publication is preserved; it never substitutes for knowledge time.
    publication = row.get("publication_date")
    if publication:
        try:
            if len(str(publication)) == 10:
                from datetime import date
                if date.fromisoformat(publication) > boundary.date():
                    reasons.append("PUBLICATION_AFTER_CUTOFF")
            elif _time(publication) > boundary:
                reasons.append("PUBLICATION_AFTER_CUTOFF")
        except ValueError:
            reasons.append("PUBLICATION_TIME_INVALID")
    return reasons


def _reference(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(row.get(key)) for key in (
        "source_identity", "document_sha256", "citation_id", "source_page", "line_code",
        "observed_at", "knowledge_available_at", "publication_date", "ingress_contract",
    )}


def build(*, ticker: str, knowledge_cutoff: str,
          official_rows: Sequence[Mapping[str, Any]],
          context_items: Sequence[Mapping[str, Any]] = (),
          valuation_context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build from retained exact rows and optional timed existing research references.

    context_items: envelopes with item=evidence_item/v1, observed_at and
    knowledge_available_at from the retained receipt. They remain context only.
    valuation_context: the same timed envelope, with payload equal to the standing
    Portfolio Opportunity Cost strategic input. No allocation or case is built.
    """
    boundary = _time(knowledge_cutoff)
    if not isinstance(ticker, str) or not ticker or ticker != ticker.strip().upper():
        raise ValueError("EXACT_TICKER_REQUIRED")
    session = boundary.date().isoformat()
    source_rows = [deepcopy(dict(r)) for r in official_rows if r.get("ticker") == ticker]
    admitted, excluded = [], []
    for row in source_rows:
        reasons = _temporal_reasons(row, boundary)
        amount = row.get("normalized_value")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            reasons.append("FINITE_NUMERIC_OFFICIAL_VALUE_REQUIRED")
        if not row.get("document_sha256") or not row.get("citation_id"):
            reasons.append("EXACT_SOURCE_REFERENCE_REQUIRED")
        if reasons:
            excluded.append({"source": _reference(row), "reasons": sorted(set(reasons))})
        else:
            admitted.append(row)
    # Filter by cutoff BEFORE conflict detection: a future revision cannot poison
    # a fact known at an earlier cutoff. Reuse every standing financial gate.
    unique = {_seal(r, "row")["artifact_sha256"]: r for r in admitted}
    baseline = {"contract_version": fundamental.CONTRACT_VERSION,
                "records": {ticker: {"metrics": []}}}
    baseline.update(fundamental.content_identity(baseline))
    projection = fundamental.project_session(
        baseline=baseline, official_rows=[unique[k] for k in sorted(unique)],
        session=session, cutoff=knowledge_cutoff)
    for rejected in projection["official_projection"]["rejected_fields"]:
        row = next(r for r in admitted if r.get("citation_id") == rejected["citation_id"])
        excluded.append({"source": _reference(row), "reasons": rejected["reasons"]})
    fields = projection["records"][ticker]["official_field_context"]
    dimensions = {key: {"observation_status": "UNKNOWN", "current_observation_status": "UNKNOWN",
                        "interpretation_status": "UNKNOWN",
                        "observations": [], "research_context": [],
                        "interpretation_blockers": list(EVIDENCE_GAPS[key])}
                  for key in DIMENSIONS}
    for field in fields:
        dimension = METRIC_DIMENSIONS.get(field["canonical_metric"])
        if dimension is None:
            excluded.append({"source": _reference(field), "reasons": ["METRIC_NOT_MAPPED_IN_V1"]})
            continue
        observation = {key: deepcopy(field.get(key)) for key in (
            "canonical_metric", "normalized_value", "currency", "reporting_period", "period_type",
            "period_start", "period_end", "statement_scope", "statement_family", "temporal_nature",
            "audit_or_review_status", "factual_status", "research_status", "research_reason_codes",
            "temporal_status", "valuation_use", "annualization", "ttm_derivation",
            "foreign_currency_conversion", "context_kind", "component_semantic_type", "component_direction",
        )}
        observation["source"] = _reference(field)
        observation["assurance_reference"] = {
            key: deepcopy((field.get("assurance_evidence") or {}).get(key))
            for key in ("evidence_id", "document_sha256", "contract_version", "page_number")}
        observation["observation_status"] = "KNOWN"
        if dimension == "earnings_quality":
            observation.update(recurrence_assessment="UNKNOWN", normalization_status="NOT_CALCULATED")
        dimensions[dimension]["observations"].append(observation)
    for dimension in dimensions.values():
        dimension["observations"].sort(key=lambda r: (r["reporting_period"], r["currency"], r["canonical_metric"], r["source"]["citation_id"]))
        if dimension["observations"]:
            dimension["observation_status"] = "PARTIALLY_KNOWN"
        if any(o["temporal_status"] == "CURRENT_OFFICIAL_FACT" for o in dimension["observations"]):
            dimension["current_observation_status"] = "PARTIALLY_KNOWN"
    # A bounded current income observation is known only within one period/scope/
    # currency group. This is not a claim about long-run profitability.
    income = dimensions["revenue_profit_economics"]
    groups: dict[tuple, set] = {}
    for observation in income["observations"]:
        if observation["temporal_status"] == "CURRENT_OFFICIAL_FACT":
            key = tuple(observation[k] for k in ("reporting_period", "statement_scope", "currency"))
            groups.setdefault(key, set()).add(observation["canonical_metric"])
    if any({"revenue", "net_income"} <= metrics for metrics in groups.values()):
        income["observation_status"] = "KNOWN"
        income["current_observation_status"] = "KNOWN"

    contexts = []
    for envelope in context_items:
        item = envelope["item"]
        _verify_context_item(item)
        if item["subject"] != {"ticker": ticker, "session": session}:
            raise ValueError("RESEARCH_CONTEXT_SUBJECT_MISMATCH")
        reasons = _temporal_reasons(envelope, boundary)
        if reasons:
            excluded.append({"source_identity": item["artifact_identity"], "reasons": reasons})
            continue
        contexts.append({"item_identity": item["artifact_identity"], "source": deepcopy(item["source"]),
                         "axis": item["axis"], "state": item["state"], "fitness": deepcopy(item["fitness"]),
                         "source_owned_facts": deepcopy(item["factual_values"]),
                         "knowledge_available_at": envelope["knowledge_available_at"],
                         "observed_at": envelope["observed_at"],
                         "authority": "RESEARCH_CONTEXT_ONLY_NOT_QUALIFIED_COMPANY_ECONOMICS"})
    valuation = None
    if valuation_context:
        reasons = _temporal_reasons(valuation_context, boundary)
        if reasons:
            excluded.append({"source_identity": valuation_context.get("payload", {}).get("source_identity"), "reasons": reasons})
        else:
            valuation = _strategic(valuation_context["payload"], session=session, ticker=ticker, event_ids=[])
            valuation["knowledge_available_at"] = valuation_context["knowledge_available_at"]
            valuation["observed_at"] = valuation_context["observed_at"]
            dimensions["valuation_fitness"]["research_context"] = [deepcopy(valuation)]
            if valuation["valuation_qualified"]:
                dimensions["valuation_fitness"].update(observation_status="KNOWN", current_observation_status="KNOWN", interpretation_status="PARTIALLY_KNOWN",
                    interpretation_blockers=["SCOPED_RELATIVE_RESEARCH_NOT_STRICT_VALUATION"])
    flags = {name: {"status": "UNKNOWN", "reason": "QUALIFIED_MULTI_YEAR_STRUCTURAL_SOURCE_NOT_AVAILABLE"}
             for name in FLAGS}
    flags["INSUFFICIENT_STRUCTURAL_EVIDENCE"] = {"status": "KNOWN", "reason": "PARTIAL_FACTS_DO_NOT_ESTABLISH_STRUCTURAL_THESIS"}
    flags["EARNINGS_QUALITY_UNCERTAIN"] = {"status": "KNOWN", "reason": "RECURRENCE_AND_RECONCILED_PRESENTATION_UNPROVEN"}
    flags["VALUATION_UNQUALIFIED"] = {"status": "KNOWN", "reason": "STRICT_SHARES_AND_VALUATION_NOT_QUALIFIED_BY_THIS_OBJECT"}
    result = {
        "contract_version": CONTRACT_VERSION, "ticker": ticker, "knowledge_cutoff": knowledge_cutoff,
        "dimensions": dimensions, "flags": flags,
        "normalization": {"status": "NORMALIZED_ECONOMICS_NOT_QUALIFIED",
                          "blockers": list(NORMALIZATION_BLOCKERS) + (["EXACT_COMPONENT_PERIOD_SCOPE_NOT_AVAILABLE"]
                            if not dimensions["earnings_quality"]["observations"] else [])},
        "research_context": sorted({_seal(r, "context")["artifact_sha256"]: r for r in contexts}.values(), key=lambda r: r["item_identity"]),
        "excluded_evidence": sorted({_seal(r, "excluded")["artifact_sha256"]: r for r in excluded}.values(), key=lambda r: _seal(r, "excluded")["artifact_sha256"]),
        "research_boundaries": list(BOUNDARIES), "strict_share_qualification": "NOT_PROVIDED",
        "strict_valuation_qualification": "NOT_PROVIDED", "non_voting": True,
        "is_actionable": False, "authority_effect": "NONE", "production": "OFFLINE_OPT_IN_ONLY",
    }
    _scan_forbidden(result)
    return _seal(result, CONTRACT_VERSION)


def render_research_boundaries(evidence: Mapping[str, Any]) -> str:
    """Small human-readable view with exact retained source/knowledge references."""
    _verify_identity(evidence, CONTRACT_VERSION)
    lines = [f"{evidence['ticker']} company economics; knowledge cutoff {evidence['knowledge_cutoff']}"]
    for name, dimension in evidence["dimensions"].items():
        lines.append(f"{name}: observed {dimension['observation_status']}; current observed "
                     f"{dimension['current_observation_status']}; interpreted {dimension['interpretation_status']}")
        lines.append("  Gaps: " + ", ".join(dimension["interpretation_blockers"]))
        for observation in dimension["observations"]:
            source = observation["source"]
            lines.append(f"  {observation['canonical_metric']} {observation['normalized_value']} {observation['currency']} "
                         f"{observation['reporting_period']} ({observation['temporal_status']}); "
                         f"document {source['document_sha256']}; citation {source['citation_id']}; "
                         f"page {source['source_page']}/line {source['line_code']}; "
                         f"known {source['knowledge_available_at']}; retrieved {source['observed_at']}")
    lines.extend(f"{name}: {flag['status']} ({flag['reason']})" for name, flag in evidence["flags"].items())
    lines.append(evidence["normalization"]["status"] + ": " + ", ".join(evidence["normalization"]["blockers"]))
    for context in evidence["research_context"]:
        lines.append(f"Research reference {context['source']['identity']} {context['source']['pointer']}; "
                     f"item {context['item_identity']}; known {context['knowledge_available_at']}; "
                     f"{context['authority']}")
    for context in evidence["dimensions"]["valuation_fitness"]["research_context"]:
        lines.append(f"Relative research {context['source']['source_identity']}; "
                     f"methods {context['qualified_methods']}; known {context['knowledge_available_at']}; "
                     f"{context['valuation_authority']}")
    lines.extend(evidence["research_boundaries"])
    return "\n".join(lines)


def packet_context(evidence: Mapping[str, Any], *, ticker: str) -> dict[str, Any]:
    """Verify the serialized v1 boundary, then retain its complete research view.

    A digest checks content integrity, not source authenticity or PIT eligibility.
    The caller must supply the existing qualified producer's object. This consumer
    neither qualifies raw facts nor evaluates structural economics.
    """
    def require(condition: bool, code: str) -> None:
        if not condition:
            raise ValueError("ECONOMICS_PACKET_" + code)

    require(isinstance(evidence, Mapping), "OBJECT_REQUIRED")
    _verify_identity(evidence, CONTRACT_VERSION)
    _scan_forbidden(dict(evidence))
    require(set(evidence) == {
        "contract_version", "ticker", "knowledge_cutoff", "dimensions", "flags",
        "normalization", "research_context", "excluded_evidence", "research_boundaries",
        "strict_share_qualification", "strict_valuation_qualification", "non_voting",
        "is_actionable", "authority_effect", "production", "artifact_identity", "artifact_sha256",
    }, "SCHEMA_UNSUPPORTED")
    require(evidence["contract_version"] == CONTRACT_VERSION and evidence["ticker"] == ticker, "SUBJECT_OR_CONTRACT_MISMATCH")
    require(isinstance(ticker, str) and bool(ticker) and ticker == ticker.strip().upper(), "EXACT_SUBJECT_REQUIRED")
    boundary = _time(evidence["knowledge_cutoff"])
    require(evidence["non_voting"] is True and evidence["is_actionable"] is False
            and evidence["authority_effect"] == "NONE" and evidence["production"] == "OFFLINE_OPT_IN_ONLY"
            and evidence["strict_share_qualification"] == evidence["strict_valuation_qualification"] == "NOT_PROVIDED", "AUTHORITY_BOUNDARY")
    require(evidence["research_boundaries"] == list(BOUNDARIES), "RESEARCH_BOUNDARY")
    dimensions = evidence["dimensions"]
    require(isinstance(dimensions, dict) and set(dimensions) == set(DIMENSIONS), "DIMENSIONS_INVALID")
    for name, dimension in dimensions.items():
        require(isinstance(dimension, dict) and set(dimension) == {
            "observation_status", "current_observation_status", "interpretation_status",
            "observations", "research_context", "interpretation_blockers"}, "DIMENSION_SCHEMA")
        require(all(isinstance(dimension[k], list) for k in ("observations", "research_context", "interpretation_blockers")), "DIMENSION_ARRAYS")
        observations = dimension["observations"]
        require(all(isinstance(o, dict) for o in observations), "OBSERVATION_OBJECT_REQUIRED")
        current = [o for o in observations if o.get("temporal_status") == "CURRENT_OFFICIAL_FACT"]
        expected = "PARTIALLY_KNOWN" if observations else "UNKNOWN"
        expected_current = "PARTIALLY_KNOWN" if current else "UNKNOWN"
        if name == "revenue_profit_economics":
            groups = {}
            for observation in current:
                key = tuple(observation.get(k) for k in ("reporting_period", "statement_scope", "currency"))
                groups.setdefault(key, set()).add(observation.get("canonical_metric"))
            if any({"revenue", "net_income"} <= metrics for metrics in groups.values()):
                expected = expected_current = "KNOWN"
        interpretation, blockers = "UNKNOWN", list(EVIDENCE_GAPS[name])
        require(not dimension["research_context"] or name == "valuation_fitness", "UNSUPPORTED_DIMENSION_CONTEXT")
        if dimension["research_context"]:
            require(len(dimension["research_context"]) == 1, "VALUATION_CONTEXT_COUNT")
            context = dimension["research_context"][0]
            require(isinstance(context, dict) and set(context) == {
                "event_ids", "catalyst_context", "valuation_authority", "status", "relative_research_state",
                "reported_relative_label", "qualified_methods", "valuation_qualified", "earnings_state",
                "source", "comparable", "gaps", "knowledge_available_at", "observed_at"}, "VALUATION_CONTEXT_SCHEMA")
            require(not _temporal_reasons(context, boundary), "CONTEXT_AFTER_CUTOFF")
            # Preserve the existing producer's scoped method result, never strict qualification.
            require(isinstance(context, dict) and context.get("valuation_authority") == "SCOPED_RELATIVE_RESEARCH_NOT_STRICT_VALUATION"
                    and isinstance(context.get("valuation_qualified"), bool), "VALUATION_BOUNDARY")
            require((context.get("source") or {}).get("session") == boundary.date().isoformat(), "VALUATION_SESSION")
            if context["valuation_qualified"]:
                require(bool(context.get("qualified_methods")) and context.get("comparable") is True, "VALUATION_METHODS")
                methods = context["qualified_methods"]
                require(all(isinstance(m, dict) and set(m) == {"method", "basis", "percentile", "peer_count"} for m in methods), "VALUATION_METHOD_SCHEMA")
                raw = {**context["source"], "relative_research_state": context["reported_relative_label"],
                       "peer_methods": {m["method"]: {**m, "status": "READY_RESEARCH_ONLY"} for m in methods}}
                checked = _strategic(raw, session=boundary.date().isoformat(), ticker=ticker, event_ids=[])
                require(checked["valuation_qualified"] and checked["qualified_methods"] == methods
                        and checked["relative_research_state"] == context["relative_research_state"], "VALUATION_METHOD_FITNESS")
                expected = expected_current = "KNOWN"
                interpretation, blockers = "PARTIALLY_KNOWN", ["SCOPED_RELATIVE_RESEARCH_NOT_STRICT_VALUATION"]
        require(dimension["observation_status"] == expected and dimension["current_observation_status"] == expected_current
                and dimension["interpretation_status"] == interpretation and dimension["interpretation_blockers"] == blockers, "STATUS_OR_INTERPRETATION_BOUNDARY")
        for observation in observations:
            fields = {"canonical_metric", "normalized_value", "currency", "reporting_period", "period_type",
                      "period_start", "period_end", "statement_scope", "statement_family", "temporal_nature",
                      "audit_or_review_status", "factual_status", "research_status", "research_reason_codes",
                      "temporal_status", "valuation_use", "annualization", "ttm_derivation",
                      "foreign_currency_conversion", "context_kind", "component_semantic_type", "component_direction",
                      "source", "assurance_reference", "observation_status"}
            if name == "earnings_quality":
                fields.update({"recurrence_assessment", "normalization_status"})
            require(set(observation) == fields, "OBSERVATION_SCHEMA")
            require(METRIC_DIMENSIONS.get(observation.get("canonical_metric")) == name, "METRIC_DIMENSION")
            amount = observation.get("normalized_value")
            require(type(amount) in (int, float) and math.isfinite(amount), "FINITE_OBSERVATION_REQUIRED")
            require(observation.get("observation_status") == "KNOWN" and observation.get("factual_status") == "qualified", "OBSERVATION_FITNESS")
            require(observation.get("annualization") == observation.get("ttm_derivation") == "NOT_PERMITTED"
                    and observation.get("foreign_currency_conversion") == "NOT_PERMITTED", "TRANSFORMATION_BOUNDARY")
            require(observation.get("temporal_status") in {"CURRENT_OFFICIAL_FACT", "HISTORICAL_OFFICIAL_FACT"}, "TEMPORAL_STATUS")
            source = observation.get("source")
            require(isinstance(source, dict) and not _temporal_reasons(source, boundary), "SOURCE_TIME_INVALID")
            require(set(source) == {"source_identity", "document_sha256", "citation_id", "source_page", "line_code",
                                   "observed_at", "knowledge_available_at", "publication_date", "ingress_contract"}, "SOURCE_SCHEMA")
            require(all(source.get(k) not in (None, "") for k in ("source_identity", "document_sha256", "citation_id", "source_page", "line_code")), "SOURCE_REFERENCE_REQUIRED")
            require(isinstance(observation.get("assurance_reference"), dict)
                    and set(observation["assurance_reference"]) == {"evidence_id", "document_sha256", "contract_version", "page_number"}
                    and observation["assurance_reference"].get("evidence_id")
                    and observation["assurance_reference"]["document_sha256"] == source["document_sha256"], "ASSURANCE_REFERENCE_REQUIRED")
            require(all(observation.get(k) for k in ("currency", "reporting_period", "period_type", "statement_scope", "statement_family")), "OBSERVATION_BASIS_REQUIRED")
            if name == "earnings_quality":
                require(observation.get("recurrence_assessment") == "UNKNOWN"
                        and observation.get("normalization_status") == "NOT_CALCULATED", "COMPONENT_INTERPRETATION_BOUNDARY")
    expected_flags = {name: {"status": "UNKNOWN", "reason": "QUALIFIED_MULTI_YEAR_STRUCTURAL_SOURCE_NOT_AVAILABLE"} for name in FLAGS}
    expected_flags.update(
        INSUFFICIENT_STRUCTURAL_EVIDENCE={"status": "KNOWN", "reason": "PARTIAL_FACTS_DO_NOT_ESTABLISH_STRUCTURAL_THESIS"},
        EARNINGS_QUALITY_UNCERTAIN={"status": "KNOWN", "reason": "RECURRENCE_AND_RECONCILED_PRESENTATION_UNPROVEN"},
        VALUATION_UNQUALIFIED={"status": "KNOWN", "reason": "STRICT_SHARES_AND_VALUATION_NOT_QUALIFIED_BY_THIS_OBJECT"})
    require(evidence["flags"] == expected_flags, "STRUCTURAL_FLAGS")
    normalization_blockers = list(NORMALIZATION_BLOCKERS)
    if not dimensions["earnings_quality"]["observations"]:
        normalization_blockers.append("EXACT_COMPONENT_PERIOD_SCOPE_NOT_AVAILABLE")
    require(evidence["normalization"] == {"status": "NORMALIZED_ECONOMICS_NOT_QUALIFIED", "blockers": normalization_blockers}, "NORMALIZATION_BOUNDARY")
    require(isinstance(evidence["research_context"], list) and isinstance(evidence["excluded_evidence"], list), "CONTEXT_ARRAYS")
    for context in evidence["research_context"]:
        require(isinstance(context, dict) and set(context) == {
            "item_identity", "source", "axis", "state", "fitness", "source_owned_facts",
            "knowledge_available_at", "observed_at", "authority"}, "CONTEXT_SCHEMA")
        require(not _temporal_reasons(context, boundary)
                and context.get("authority") == "RESEARCH_CONTEXT_ONLY_NOT_QUALIFIED_COMPANY_ECONOMICS", "CONTEXT_BOUNDARY")
    return {"matrix": deepcopy(dict(evidence)), "source_matrix_identity": evidence["artifact_identity"],
            "temporal_use": "CONSULTATION_KNOWLEDGE_CUTOFF_NOT_SEALED_DECISION_TIME",
            "identity_use": "CONTENT_INTEGRITY_NOT_SOURCE_AUTHENTICATION_OR_PIT"}


def compare_selected(matrices: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Display exact reported bases side by side, without arithmetic or judgment."""
    if not matrices:
        raise ValueError("ECONOMICS_COMPARISON_SELECTION_REQUIRED")
    views = sorted([packet_context(matrix, ticker=matrix["ticker"])["matrix"] for matrix in matrices], key=lambda v: v["ticker"])
    tickers = [v["ticker"] for v in views]
    if len(set(tickers)) != len(tickers):
        raise ValueError("ECONOMICS_COMPARISON_DUPLICATE_TICKER")
    if len({_time(v["knowledge_cutoff"]) for v in views}) != 1:
        raise ValueError("ECONOMICS_COMPARISON_CUTOFF_MISMATCH")
    basis_keys = ("canonical_metric", "period_start", "period_end", "period_type", "statement_scope",
                  "currency", "statement_family", "temporal_nature", "context_kind",
                  "component_semantic_type", "component_direction")
    groups, unpaired = {}, []
    from datetime import date
    for view in sorted(views, key=lambda v: v["ticker"]):
        for name, dimension in view["dimensions"].items():
            for observation in dimension["observations"]:
                row = {"ticker": view["ticker"], "dimension": name, "observation": deepcopy(observation)}
                start, end = observation.get("period_start"), observation.get("period_end")
                try:
                    # Stock observations also need explicit coverage; labels never supply dates.
                    dates_valid = bool(start and end and date.fromisoformat(start) <= date.fromisoformat(end))
                except (ValueError, TypeError):
                    dates_valid = False
                if not dates_valid:
                    unpaired.append({**row, "basis_status": "EXPLICIT_COVERED_DATES_NOT_AVAILABLE"})
                    continue
                basis = {k: observation.get(k) for k in basis_keys}
                groups.setdefault(_canonical(basis), {"basis": basis, "observations": []})["observations"].append(row)
    grouped = []
    for key in sorted(groups):
        group = groups[key]
        group["basis_status"] = ("EXACT_REPORTED_BASIS_MATCH_NOT_ECONOMIC_EQUIVALENCE"
                                 if len({r["ticker"] for r in group["observations"]}) > 1 else "SINGLE_SELECTED_ISSUER_ONLY")
        grouped.append(group)
    return {"selection_basis": "EXPLICIT_STUDY_GROUP_NOT_UNIVERSE_OR_PEER_COHORT",
            "tickers": sorted(tickers), "knowledge_cutoff": views[0]["knowledge_cutoff"],
            "groups": grouped, "unpaired_observations": unpaired,
            "issuer_states": {v["ticker"]: {"source_matrix_identity": v["artifact_identity"],
                "dimensions": {n: {k: deepcopy(d[k]) for k in ("observation_status", "current_observation_status", "interpretation_status", "interpretation_blockers")} for n, d in v["dimensions"].items()},
                "flags": v["flags"], "normalization": v["normalization"]} for v in sorted(views, key=lambda v: v["ticker"])},
            "research_boundaries": list(BOUNDARIES), "non_voting": True, "is_actionable": False,
            "authority_effect": "NONE", "production": "OFFLINE_OPT_IN_ONLY"}
