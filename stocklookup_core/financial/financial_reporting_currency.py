"""Read-only reporting-basis reconciliation over existing financial owners.

This is a descriptive product adapter, not a qualification or calculation engine.
Official admission is delegated to project_session; Financial V2 measurements are
copied from its compact product. No production consumer imports this by default.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from stocklookup_core.decision.opportunity_axis_freshness import (
    classify_financial_period_freshness, reporting_period_basis, reporting_period_relation,
)
from stocklookup_core.financial import financial_analysis_product_projection as product
from stocklookup_core.financial import financial_v2_current_input_authority as pin

CONTRACT_VERSION = "financial_reporting_currency/v1"
TEMPORAL_USE = "CONSULTATION_KNOWLEDGE_CUTOFF_NOT_PIT_OR_SEALED_DECISION_TIME"
BOUNDARIES = ["NO_METRIC_REPLACEMENT", "NO_ANNUALIZATION_TTM_OR_FX_CONVERSION",
              "NO_VOTE_VALUATION_OR_AUTHORITY_CHANGE", "NO_SOURCE_ACTIVATION",
              "NO_GLOBAL_LATEST_OR_ABSENCE_CLAIM", "NO_CAPITAL_VERDICT"]
REFERENCE_FIELDS = ("source_identity", "document_sha256", "citation_id", "source_page", "line_code",
                    "observed_at", "knowledge_available_at", "publication_date", "ingress_contract")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value: Mapping[str, Any]) -> dict[str, str]:
    digest = hashlib.sha256(canonical({k: v for k, v in value.items()
                                     if k not in {"artifact_identity", "artifact_sha256"}}).encode()).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": CONTRACT_VERSION + ":" + digest}


def _time(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("TIMEZONE_BEARING_KNOWLEDGE_TIME_REQUIRED") from exc


def _eligibility(source: Mapping[str, Any], boundary: datetime) -> dict[str, Any]:
    reasons = []
    for field in ("observed_at", "knowledge_available_at"):
        try:
            if _time(source.get(field)) > boundary:
                reasons.append(field.upper() + "_AFTER_CUTOFF")
        except ValueError:
            reasons.append(field.upper() + "_UNKNOWN_OR_INVALID")
    published = source.get("publication_date")
    publication = "UNKNOWN" if published is None else "KNOWN"
    if published is not None:
        try:
            if len(published) == 10:
                if date.fromisoformat(published) > boundary.date():
                    reasons.append("PUBLICATION_AFTER_CUTOFF")
            elif _time(published) > boundary:
                reasons.append("PUBLICATION_AFTER_CUTOFF")
        except (TypeError, ValueError):
            reasons.append("PUBLICATION_TIME_INVALID")
            publication = "INVALID"
    return {"state": "KNOWN_BY_CONSULTATION_CUTOFF" if not reasons else "EXCLUDED_OR_UNPROVEN_AT_CUTOFF",
            "publication_state": publication, "reason_codes": sorted(reasons),
            "decision_time_eligibility": "NOT_ESTABLISHED_FOR_SEALED_DECISION_OR_PIT"}


def _reference(row: Mapping[str, Any]) -> dict[str, Any]:
    result = {k: deepcopy(row.get(k)) for k in REFERENCE_FIELDS}
    if result["source_identity"] is None:
        result["source_identity"] = row.get("source_locator") or ("official-document:" + str(row["document_sha256"]) if row.get("document_sha256") else None)
    return result


def _basis(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    if (data.get("period_type") == "interim" and str(data.get("reporting_period") or "").endswith("-H1")
            and data.get("period_start") and data.get("period_end")):
        data.setdefault("period_semantic_state", "YTD_CUMULATIVE_INTERIM")
    if data.get("period_type") == "half_year":
        data.setdefault("period_semantic_state", "YTD_CUMULATIVE_INTERIM")
    if data.get("period_type") == "annual":
        data.setdefault("period_semantic_state", "ANNUAL")
    return reporting_period_basis(data)


def comparison_basis(basis: Mapping[str, Any]) -> tuple | None:
    """A usable comparison key requires proved dates and the full measurement basis."""
    fields = ("canonical_metric", "statement_family", "time_basis", "statement_scope", "currency", "unit_scale", "period_end")
    if any(basis.get(k) is None or basis.get(k) == "" for k in fields):
        return None
    if "NATIVE_PERIOD_FAMILY_DURATION_CONFLICT" in basis.get("reason_codes", []):
        return None
    scale = basis.get("unit_scale")
    if (not isinstance(basis.get("currency"), str) or not re.fullmatch(r"[A-Z]{3}", basis["currency"])
            or isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0
            or basis.get("statement_scope") not in ("consolidated", "separate", "parent", "parent_only")
            or basis.get("statement_family") not in ("income_statement", "balance_sheet", "cash_flow")
            or basis.get("time_basis") not in ("INSTANT", "DURATION")
            or basis.get("period_family") == "UNKNOWN"):
        return None
    if basis["time_basis"] == "DURATION" and (not basis.get("period_start") or basis.get("cumulative_basis") == "UNKNOWN"):
        return None
    return tuple(basis.get(k) for k in (*fields, "period_start", "cumulative_basis", "period_family"))


def compatible_measurement(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """Allows descriptive comparison of the same kind of period, never substitution."""
    missing = comparison_basis(left) is None or comparison_basis(right) is None
    dimensions = ("canonical_metric", "statement_family", "time_basis", "statement_scope", "currency", "unit_scale", "cumulative_basis", "period_family")
    mismatches = [k.upper() + "_MISMATCH" for k in dimensions if left.get(k) != right.get(k)]
    if left.get("time_basis") == right.get("time_basis") == "DURATION":
        # Actual duration plus native period family prevent Q2/H1 and 9M/annual swaps.
        if left.get("duration_days") is None or right.get("duration_days") is None:
            missing = True
        elif abs(left["duration_days"] - right["duration_days"]) > 2:
            mismatches.append("DURATION_MISMATCH")
    return {"status": "COMPARABLE_DESCRIPTIVE_ONLY" if not missing and not mismatches else "NOT_COMPARABLE",
            "reason_codes": sorted(mismatches + (["EXPLICIT_MEASUREMENT_BASIS_UNPROVEN"] if missing else [])),
            "replacement": "NOT_PERMITTED"}


def _assurance_bound(row: Mapping[str, Any]) -> bool:
    """Consumer guard against the owner's legacy bare-audited caller allowance.

    This validates the existing retained proof envelope, not PDF classification.
    It cannot certify a filing period or repair upstream evidence recognizers.
    """
    from official_financial_assurance_evidence import CONTRACT_VERSION, validate_assurance_claim

    proof = row.get("assurance_evidence")
    if not isinstance(proof, Mapping) or proof.get("contract_version") != CONTRACT_VERSION:
        return False
    try:
        validate_assurance_claim(row.get("audit_or_review_status"), proof,
                                 document_sha256=row.get("document_sha256"))
    except ValueError:
        return False
    span = proof.get("title_span")
    if not isinstance(span, Mapping):
        return False
    # Reconcile the existing resolver's content identity without reclassifying text.
    proof_id = hashlib.sha256(canonical({"contract": CONTRACT_VERSION,
        "document_sha256": proof.get("document_sha256"), "page_number": proof.get("page_number"),
        "status": proof.get("audit_or_review_status"), "anchors": proof.get("matched_anchors"),
        "title_span": span, "rendered_image_sha256": proof.get("rendered_image_sha256"),
        "materialization_id": proof.get("materialization_id")}).encode()).hexdigest()
    if proof.get("opinion_evidence"):
        proof_id = hashlib.sha256(canonical({"base_evidence_id": proof_id,
            "opinion_evidence": proof["opinion_evidence"]}).encode()).hexdigest()
    scope = "consolidated_interim_statements" if row.get("audit_or_review_status") == "reviewed" else "consolidated_statements"
    return bool(proof.get("evidence_id") == proof_id and proof.get("citation_id") == proof_id
                and proof.get("scope_of_assurance") == scope
                and proof.get("matched_anchors") and span.get("token_ids")
                and all(re.fullmatch(r"[0-9a-f]{64}", str(proof.get(k) or ""))
                        for k in ("evidence_id", "materialization_id", "page_text_sha256", "rendered_image_sha256")))


def _official(tickers: Sequence[str], rows: Sequence[Mapping[str, Any]], session: str, cutoff: str):
    import market_wide_current_fundamental_research as owner
    from financial_evidence_currency_contract import TARGET_PERIODS

    boundary = _time(cutoff)
    inputs, excluded = {}, {t: [] for t in tickers}
    for row in rows:
        ticker = row.get("ticker")
        if ticker not in excluded:
            continue
        source = _reference(row)
        eligibility = _eligibility(source, boundary)
        reasons = list(eligibility["reason_codes"])
        value = row.get("normalized_value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            reasons.append("FINITE_NUMERIC_OFFICIAL_VALUE_REQUIRED")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("document_sha256") or "")) or not isinstance(row.get("citation_id"), str) or not row["citation_id"].strip():
            reasons.append("EXACT_SOURCE_REFERENCE_REQUIRED")
        if row.get("reporting_period") not in TARGET_PERIODS:
            reasons.append("SOURCE_PERIOD_NOT_REGISTERED_BY_EXISTING_INGRESS")
        if not _assurance_bound(row):
            reasons.append("RETAINED_DOCUMENT_ASSURANCE_PROOF_NOT_BOUND")
        if row.get("metadata_qualification") in ("BLOCKED", "UNQUALIFIED") or row.get("qualification_status") == "BLOCKED":
            reasons.append("SOURCE_METADATA_EXPLICITLY_BLOCKED")
        if reasons:
            excluded[ticker].append({"source": source, "eligibility": eligibility, "reason_codes": sorted(set(reasons))})
        else:
            inputs[canonical(row)] = deepcopy(dict(row))
    # Future revisions are excluded BEFORE the standing owner's conflict detector.
    baseline = {"contract_version": owner.CONTRACT_VERSION, "records": {t: {"metrics": []} for t in tickers}}
    baseline.update(owner.content_identity(baseline))
    projected = owner.project_session(baseline=baseline, official_rows=[inputs[k] for k in sorted(inputs)], session=session, cutoff=cutoff)
    qualified = {t: [] for t in tickers}
    for t in tickers:
        for row in projected["records"][t].get("official_field_context", []):
            qualified[t].append({"basis": _basis(row), "normalized_value": row["normalized_value"],
                                 "assurance_evidence": deepcopy(row["assurance_evidence"]),
                                 "audit_or_review_status": row["audit_or_review_status"],
                                 "source": _reference(row), "qualification": {k: row[k] for k in ("factual_status", "factual_reason_codes", "research_status", "research_reason_codes")},
                                 "formal_temporal_status": row["temporal_status"],
                                 "valuation_use": row["valuation_use"],
                                 "eligibility": _eligibility(row, boundary)})
    rejections = {t: [] for t in tickers}
    for row in projected["official_projection"]["rejected_fields"]:
        if row.get("ticker") in rejections:
            rejections[row["ticker"]].append(deepcopy(row))
    # Preserve the known period/source of rejected assertions, without showing their values.
    assertions = {t: [] for t in tickers}
    for row in inputs.values():
        if any(q["source"]["citation_id"] == row.get("citation_id") and q["source"]["document_sha256"] == row.get("document_sha256")
               and q["basis"]["canonical_metric"] == row.get("canonical_metric") and q["basis"]["native_label"] == row.get("reporting_period")
               for q in qualified[row["ticker"]]):
            continue
        assertions[row["ticker"]].append({"basis": _basis(row), "source": _reference(row),
                                          "asserted_qualification": row.get("qualification_state"),
                                          "assurance": row.get("audit_or_review_status")})
    return qualified, excluded, rejections, assertions


def _report_checks(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if report is None:
        return []
    if report.get("contract_version") != "financial_evidence_currency_refresh/v1":
        raise ValueError("SOURCE_REPORT_CONTRACT_MISMATCH")
    payload = {k: v for k, v in report.items() if k not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
    verified = report.get("artifact_sha256") == digest and report.get("artifact_identity") == "financial_evidence_currency_refresh:" + digest
    result = []
    for ticker, issuer in sorted(report.get("issuers", {}).items()):
        for label, period in sorted(issuer.get("periods", {}).items()):
            retained = period.get("immutable_raw_retained") is True and period.get("document_found") is True and bool(re.fullmatch(r"[0-9a-f]{64}", str(period.get("hash") or "")))
            checked = period.get("requested") is True and period.get("http_status") == 200
            kind = ("RETAINED_DOCUMENT" if retained else "CHECKED_NO_POSITIVE_EVIDENCE" if checked and period.get("document_found") is False else "BLOCKED_OR_UNCHECKED") if verified else "UNVERIFIED_CHECK_RECEIPT"
            result.append({"ticker": ticker, "kind": kind, "reporting_period": label,
                           "statement_scope": period.get("scope"),
                           "source_identity": "cohort-report-content:" + digest, "document_sha256": period.get("hash"),
                           "citation_id": period.get("route"), "observed_at": report.get("observed_at"),
                           "knowledge_available_at": report.get("observed_at"), "publication_date": period.get("publication_date"),
                           "blocker": period.get("blocker") if verified else "SOURCE_REPORT_IDENTITY_MISMATCH", "conflicts": deepcopy(period.get("conflicts") or []),
                           "receipt_integrity": "VERIFIED_CONTENT_IDENTITY" if verified else "EMBEDDED_IDENTITY_MISMATCH",
                           "asserted_document_retained": retained,
                           "checked_scope": {"reporting_period": label, "route": period.get("route"), "http_status": period.get("http_status")}})
    return result


def _baseline(record: Mapping[str, Any], observations: Sequence[Mapping[str, Any]], boundary: datetime):
    lineage = (record.get("lineage") or {}).get("source_identities") or {}
    knowledge = lineage.get("period_semantics_knowledge_time")
    recognized = (lineage.get("period_semantics_identity") == pin._EXPECTED_SEMANTICS_IDENTITY
                  and lineage.get("feature_store_artifact_identity") == pin._EXPECTED_FEATURE_STORE_IDENTITY)
    retained_eligibility = _eligibility({"observed_at": knowledge, "knowledge_available_at": knowledge,
                                        "publication_date": None}, boundary)
    # Raw observations are descriptive only and must join an exact compact source reference.
    refs = {(r.get("provider"), r.get("source_sha256"), r.get("fact_id"))
            for f in (record.get("feature_fitness") or {}).values()
            for r in (f.get("source_feature_context") or {}).get("source_fact_refs", [])
            if all(isinstance(r.get(k), str) and r[k] for k in ("provider", "source_sha256", "fact_id"))}
    matched = []
    for row in observations:
        source = row.get("source_lineage") or {}
        if (source.get("provider"), source.get("source_sha256"), source.get("fact_id")) not in refs:
            continue
        ref = {"source_identity": record.get("source_context_identity"),
               "document_sha256": source.get("source_sha256"), "citation_id": source.get("fact_id"),
               "observed_at": row.get("retrieval_or_observation_timestamp"),
               "knowledge_available_at": knowledge, "publication_date": row.get("published_timestamp")}
        eligible = _eligibility(ref, boundary)
        observation_basis = _basis(row)
        if observation_basis.get("period_end") and observation_basis["period_end"] > boundary.date().isoformat():
            eligible["reason_codes"].append("EXPLICIT_REPORTING_PERIOD_END_AFTER_CUTOFF")
            eligible["state"] = "EXCLUDED_OR_UNPROVEN_AT_CUTOFF"
        observation = {"basis": observation_basis, "source": ref, "eligibility": eligible,
                       "qualification": "PROVIDER_REPORTED_NOT_OFFICIAL", "source_conflicts": deepcopy(row.get("source_conflicts") or [])}
        if not eligible["reason_codes"]:
            observation["reported_value"] = row.get("reported_value")
        else:
            observation["value_state"] = "WITHHELD_EXCLUDED_OR_UNPROVEN_AT_CUTOFF"
        matched.append(observation)
    measurements = []
    for key, feature in sorted((record.get("feature_fitness") or {}).items()):
        context = deepcopy(feature.get("source_feature_context") or {})
        bases = [_basis({**context, "reporting_period": label, "canonical_metric": key}) for label in context.get("period_identity") or []]
        measurements.append({"feature_id": key, "fitness": feature.get("fitness"),
                             "reason_codes": deepcopy(feature.get("reason_codes") or []),
                             "measurement": context, "periods": bases,
                             "analytical_lag_validity": [classify_financial_period_freshness(source_period=b["native_label"], decision_session=boundary.date().isoformat(), maximum_completed_quarter_lag=4) for b in bases]})
    excluded_measurements = []
    if retained_eligibility["reason_codes"]:
        excluded_measurements = [{"feature_id": m["feature_id"], "source_fact_refs": m["measurement"].get("source_fact_refs"),
                                  "value_state": "WITHHELD_RETAINED_KNOWLEDGE_UNPROVEN_AT_CUTOFF"} for m in measurements]
        measurements = []
    return {"status": record.get("status"), "source_context_identity": record.get("source_context_identity"),
            "lineage_ref": record.get("lineage_ref"), "source_identities": deepcopy(lineage),
            "measurements": measurements, "excluded_measurement_references": excluded_measurements,
            "retained_knowledge_eligibility": retained_eligibility, "matched_observations": _sorted_unique(matched),
            "compact_context": deepcopy(record) if not retained_eligibility["reason_codes"] else None,
            "source_update_state": "FROZEN_PROVIDER_PIN" if recognized else "PROVIDER_UPDATE_STATE_UNPROVEN",
            "pin_version": pin.AUTHORITY_VERSION if recognized else None,
            "last_retained_knowledge_time": knowledge, "last_source_publication": None,
            "publication_state": "UNKNOWN", "reason_codes": ["OBSERVATION_IS_NOT_PUBLICATION", "COMPACT_HEADLINE_IS_NATIVE_LABEL_NOT_CALENDAR_LATEST"]}


def _sorted_unique(rows):
    return [json.loads(k) for k in sorted({canonical(r) for r in rows})]


def _comparison_anchors(bases, candidate):
    # An old historical row must never make a filing look newer than the latest
    # available basis. Keep statement timing and measurement matching separate.
    exact = [b for b in bases if b.get("canonical_metric") == candidate.get("canonical_metric")
             and b.get("statement_family") == candidate.get("statement_family")]
    selected = exact or bases
    dated = [b for b in selected if b.get("period_end")]
    if dated:
        end = max(b["period_end"] for b in dated)
        return _sorted_unique([b for b in dated if b["period_end"] == end])
    labels = [b for b in selected if re.fullmatch(r"\d{4}(?:-(?:Q[1-4]|H1|9M|FY))?", str(b.get("native_label") or ""))]
    if not labels:
        return _sorted_unique(selected)
    year = max(b["native_label"][:4] for b in labels)
    same_year = [b for b in labels if b["native_label"][:4] == year]
    return _sorted_unique([b for b in same_year if not any(reporting_period_relation(b, other) == "NATIVE_LABEL_PROGRESS_CALENDAR_UNPROVEN" for other in same_year)])


def _collapse_checks(checks):
    groups = {}
    for check in checks:
        key = canonical({k: check.get(k) for k in ("kind", "basis", "checked_scope", "blocker", "receipt_integrity")})
        source = check["source"]
        key += canonical({k: source.get(k) for k in ("source_identity", "document_sha256", "publication_date")})
        if not source.get("document_sha256"):
            key += canonical(source.get("citation_id"))
        if key not in groups:
            groups[key] = deepcopy(check)
            groups[key]["observation_receipts"] = []
        groups[key]["observation_receipts"].append({k: source.get(k) for k in ("observed_at", "knowledge_available_at", "citation_id")})
        if (_time(source["knowledge_available_at"]), canonical(source)) < (_time(groups[key]["source"]["knowledge_available_at"]), canonical(groups[key]["source"])):
            groups[key]["source"] = deepcopy(source)
    return [{**groups[k], "observation_receipts": _sorted_unique(groups[k]["observation_receipts"])} for k in sorted(groups)]


def build(*, financial_product: Mapping[str, Any], official_rows: Sequence[Mapping[str, Any]],
          tickers: Sequence[str], decision_session: str, knowledge_cutoff: str,
          cohort_report: Mapping[str, Any] | None = None,
          provider_observations: Sequence[Mapping[str, Any]] = (),
          source_checks: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Bounded side-by-side consultation. Inputs remain unchanged and are not overwritten."""
    import re

    boundary = _time(knowledge_cutoff)
    if date.fromisoformat(decision_session).isoformat() != decision_session or boundary.date().isoformat() != decision_session:
        raise ValueError("SESSION_CUTOFF_DATE_MISMATCH")
    names = sorted(tickers)
    if not names or len(names) > 32 or len(set(names)) != len(names) or any(not isinstance(t, str) or not re.fullmatch(r"[A-Z0-9]{1,16}", t) for t in names):
        raise ValueError("INVALID_BOUNDED_TICKER_SELECTION")
    canonical([financial_product, official_rows, cohort_report, provider_observations, source_checks])
    product.validate_product_context(financial_product)
    if financial_product.get("artifact_identity") != product._identity(financial_product)["artifact_identity"]:
        raise ValueError("FINANCIAL_PRODUCT_IDENTITY_MISMATCH")
    qualified, excluded, rejected, assertions = _official(names, official_rows, decision_session, knowledge_cutoff)
    checks = _report_checks(cohort_report) + [deepcopy(dict(c)) for c in source_checks]
    records = {}
    for ticker in names:
        compact = product.context_for_ticker(financial_product, ticker) if ticker in financial_product["records"] else product.absent_context(ticker, source_context_identity=financial_product.get("source_context_identity"))
        baseline = _baseline(compact, [r for r in provider_observations if r.get("ticker") == ticker], boundary)
        known_checks, excluded_checks = [], []
        for check in checks:
            if check.get("ticker") != ticker:
                continue
            if check.get("kind") not in {"RETAINED_DOCUMENT", "SOURCE_NOTICE", "CHECKED_NO_POSITIVE_EVIDENCE", "BLOCKED_OR_UNCHECKED", "UNVERIFIED_CHECK_RECEIPT"} or not check.get("source_identity") or not check.get("checked_scope"):
                raise ValueError("SOURCE_CHECK_RECEIPT_REQUIRED")
            if check.get("kind") == "RETAINED_DOCUMENT" and not re.fullmatch(r"[0-9a-f]{64}", str(check.get("document_sha256") or "")):
                raise ValueError("RETAINED_DOCUMENT_HASH_REQUIRED")
            eligible = _eligibility(check, boundary)
            receipt = {"kind": check["kind"], "basis": _basis(check), "source": _reference(check),
                       "checked_scope": deepcopy(check["checked_scope"]), "blocker": check.get("blocker"),
                       "conflicts": deepcopy(check.get("conflicts") or []), "eligibility": eligible,
                       "receipt_integrity": check.get("receipt_integrity", "EXPLICIT_INPUT_RECEIPT_NOT_SOURCE_AUTHORITY"),
                       "asserted_document_retained": check.get("asserted_document_retained")}
            (known_checks if not eligible["reason_codes"] else excluded_checks).append(receipt)
        known_checks = _collapse_checks(known_checks)
        provider_bases = [o["basis"] for o in baseline["matched_observations"] if not o["eligibility"]["reason_codes"]]
        if not provider_bases:
            provider_bases = [b for m in baseline["measurements"] for b in m["periods"]]
        # Keep every period/family; a single lexical maximum is never a ticker currency verdict.
        period_evidence = []
        candidates = [("QUALIFIED_EXACT_FACT", q) for q in qualified[ticker]] + [(c["kind"], c) for c in known_checks]
        for kind, candidate in candidates:
            basis = candidate["basis"]
            period_evidence.append({"kind": kind, "basis": basis, "source": candidate["source"],
                                    "relations_to_provider": _sorted_unique([{"baseline": b, "relation": reporting_period_relation(b, basis),
                                                                               "measurement_comparison": compatible_measurement(b, basis)} for b in _comparison_anchors(provider_bases, basis)]),
                                    "claim_limit": "SOURCE_SCOPE_AND_NATIVE_LABEL_ONLY_WHEN_CALENDAR_UNPROVEN"})
        later = {e["kind"] for e in period_evidence if e["kind"] not in {"UNVERIFIED_CHECK_RECEIPT", "CHECKED_NO_POSITIVE_EVIDENCE", "BLOCKED_OR_UNCHECKED"} and any(r["relation"] in {"NEWER_EXPLICIT_END", "NATIVE_LABEL_PROGRESS_CALENDAR_UNPROVEN"} for r in e["relations_to_provider"])}
        conflicts = any("CONFLICT" in canonical(r) for r in rejected[ticker]) or any(c["conflicts"] for c in known_checks)
        reasons = ["FORMAL_CURRENT_IS_POLICY_LABEL_NOT_LATEST_REPORT", "NO_WHOLE_TICKER_REJECTION", "PUBLICATION_UNKNOWN_DOES_NOT_PROVE_PIT"]
        if "QUALIFIED_EXACT_FACT" in later:
            reasons.append("KNOWN_NATIVE_PERIOD_PROGRESS_QUALIFIED_FIELDS_ONLY")
        if "RETAINED_DOCUMENT" in later:
            reasons.append("KNOWN_RETAINED_PERIOD_PROGRESS_NOT_FIELD_QUALIFICATION")
        if "SOURCE_NOTICE" in later:
            reasons.append("SOURCE_NOTICE_NOT_AUTHENTICATED_FILING")
        if conflicts:
            reasons.append("KNOWN_SOURCE_ASSERTION_CONFLICT")
        if any(c["kind"] == "UNVERIFIED_CHECK_RECEIPT" for c in known_checks):
            reasons.append("SOURCE_REPORT_IDENTITY_MISMATCH")
        reasons.append("NO_GLOBAL_LATEST_REPORT_PROOF")
        entity = compact.get("issuer_type") or "UNKNOWN"
        records[ticker] = {"ticker": ticker, "report_period_coverage": {"provider_bases": _sorted_unique(provider_bases),
                           "official_bases": _sorted_unique([q["basis"] for q in qualified[ticker]]),
                           "entity_type": entity, "analysis_family": compact.get("analysis_family"),
                           "method_applicability": {"ordinary_corporate_debt_ebitda": "NOT_APPLICABLE" if entity in {"bank", "securities"} else "FOLLOW_EXISTING_ENTITY_METHOD_GATES",
                                                    "bank": "FOLLOW_BANK_OWNER" if entity == "bank" else "NOT_APPLICABLE",
                                                    "securities": "FOLLOW_SECURITIES_OWNER" if entity == "securities" else "NOT_APPLICABLE"}},
                           "source_update": {"provider": baseline["source_update_state"],
                                             "official_route": "RETAINED_SUCCESSFUL_CHECK_AT_RECEIPT_TIME" if any(c["kind"] not in {"BLOCKED_OR_UNCHECKED", "UNVERIFIED_CHECK_RECEIPT", "SOURCE_NOTICE"} for c in known_checks) else "BLOCKED_OR_UNCHECKED",
                                             "checks": _sorted_unique(known_checks), "live_route_status": "NOT_CHECKED_BY_OFFLINE_CONSUMER"},
                           "newer_period_evidence": {"period_evidence": _sorted_unique(period_evidence), "known_progress_kinds": sorted(later),
                                                     "conflicts": conflicts, "unqualified_assertions": _sorted_unique(assertions[ticker]),
                                                     "qualification_rejections": _sorted_unique(rejected[ticker]), "global_latest_status": "UNPROVEN"},
                           "knowledge_cutoff_eligibility": {"excluded_facts": _sorted_unique(excluded[ticker]), "excluded_checks": _sorted_unique(excluded_checks),
                                                            "knowledge_cutoff": knowledge_cutoff, "temporal_use": TEMPORAL_USE},
                           "investor_interpretation": {"historical_research_usable": bool(baseline["measurements"] or qualified[ticker]),
                                                       "update_status": "KNOWN_PERIOD_CONTEXT_WITH_LIMITS" if later else "LATEST_UPDATE_UNKNOWN",
                                                       "material_freshness_warning": bool(later or conflicts), "reason_codes": sorted(reasons),
                                                       "blocked_fields": _sorted_unique(rejected[ticker]), "ticker_rejected": False},
                           "frozen_provider_baseline": baseline, "qualified_official_fields": _sorted_unique(qualified[ticker])}
        sources = [q["source"] for q in qualified[ticker]]
        records[ticker]["source_update"]["official_fact_retrieval_times"] = sorted({s["observed_at"] for s in sources if s.get("observed_at")})
        records[ticker]["source_update"]["official_fact_qualification_times"] = sorted({s["knowledge_available_at"] for s in sources if s.get("knowledge_available_at")})
        records[ticker]["source_update"]["official_publication_times"] = sorted({s["publication_date"] for s in sources if s.get("publication_date")})
        records[ticker]["source_update"]["official_publication_state"] = "UNKNOWN_FOR_SOME_OR_ALL_FACTS" if any(not s.get("publication_date") for s in sources) or not sources else "EXPLICIT_SOURCE_PUBLICATION_RETAINED"
    groups = {}
    for ticker, record in records.items():
        for q in record["qualified_official_fields"]:
            key = comparison_basis(q["basis"])
            if key is not None:
                key += (record["report_period_coverage"]["entity_type"], record["report_period_coverage"]["analysis_family"])
                group = groups.setdefault(canonical(key), {"basis": q["basis"], "members": []})
                group["entity_type"] = record["report_period_coverage"]["entity_type"]
                group["members"].append({"ticker": ticker, "value": q["normalized_value"], "source": q["source"]})
    result = {"contract_version": CONTRACT_VERSION, "decision_session": decision_session, "knowledge_cutoff": knowledge_cutoff,
              "temporal_use": TEMPORAL_USE, "selection_basis": "EXPLICIT_SELECTED_SECURITIES_NOT_PEER_OR_UNIVERSE_COHORT",
              "source_financial_product_identity": financial_product["artifact_identity"], "records": records,
              "coverage": {"selected_ticker_denominator": len(names), "provider_present_count": sum(r["frozen_provider_baseline"]["status"] == "AVAILABLE" for r in records.values()),
                           "provider_known_by_cutoff_count": sum(not r["frozen_provider_baseline"]["retained_knowledge_eligibility"]["reason_codes"] for r in records.values()),
                           "qualified_fact_count": sum(len(r["qualified_official_fields"]) for r in records.values()),
                           "qualified_ticker_count": sum(bool(r["qualified_official_fields"]) for r in records.values()),
                           "verified_retained_document_count": len({(t, c["source"]["document_sha256"]) for t, r in records.items() for c in r["source_update"]["checks"] if c["kind"] == "RETAINED_DOCUMENT"}),
                           "unverified_document_claim_count": len({(t, c["source"]["document_sha256"]) for t, r in records.items() for c in r["source_update"]["checks"] if c["kind"] == "UNVERIFIED_CHECK_RECEIPT" and c["asserted_document_retained"]}),
                           "checked_negative_scope_count": sum(c["kind"] == "CHECKED_NO_POSITIVE_EVIDENCE" for r in records.values() for c in r["source_update"]["checks"]),
                           "notice_scope_count": sum(c["kind"] == "SOURCE_NOTICE" for r in records.values() for c in r["source_update"]["checks"]),
                           "progress_kind_ticker_counts": dict(sorted(Counter(k for r in records.values() for k in r["newer_period_evidence"]["known_progress_kinds"]).items())),
                           "zero_silent_ticker_drops": True},
              "selected_comparison": {"basis_groups": [{**groups[k], "members": _sorted_unique(groups[k]["members"])} for k in sorted(groups)],
                                      "cross_basis_comparison": "NOT_PERMITTED", "ranking": "NOT_PRODUCED"},
              "research_boundaries": list(BOUNDARIES), "authority_effect": "NONE", "non_voting": True,
              "is_actionable": False, "production": "OFFLINE_OPT_IN_ONLY"}
    result.update(identity(result))
    return result


def packet_context(projection: Mapping[str, Any], *, ticker: str, decision_session: str | None = None):
    """Verify identity and immutable research boundaries before a packet accepts the view."""
    if projection.get("contract_version") != CONTRACT_VERSION or any(projection.get(k) != v for k, v in identity(projection).items()):
        raise ValueError("FINANCIAL_CURRENCY_IDENTITY_MISMATCH")
    if projection.get("authority_effect") != "NONE" or projection.get("non_voting") is not True or projection.get("is_actionable") is not False or projection.get("production") != "OFFLINE_OPT_IN_ONLY" or projection.get("research_boundaries") != BOUNDARIES or projection.get("temporal_use") != TEMPORAL_USE:
        raise ValueError("FINANCIAL_CURRENCY_BOUNDARY_MISMATCH")
    if decision_session is not None and decision_session != projection.get("decision_session"):
        raise ValueError("FINANCIAL_CURRENCY_SESSION_MISMATCH")
    record = projection.get("records", {}).get(ticker)
    if not isinstance(record, Mapping) or record.get("ticker") != ticker:
        raise ValueError("FINANCIAL_CURRENCY_SUBJECT_MISMATCH")
    boundary = _time(projection["knowledge_cutoff"])
    if projection.get("decision_session") != boundary.date().isoformat():
        raise ValueError("FINANCIAL_CURRENCY_CUTOFF_SESSION_MISMATCH")
    coverage = projection.get("coverage") or {}
    if coverage.get("selected_ticker_denominator") != len(projection["records"]) or coverage.get("zero_silent_ticker_drops") is not True:
        raise ValueError("FINANCIAL_CURRENCY_DENOMINATOR_MISMATCH")
    if record["investor_interpretation"].get("ticker_rejected") is not False or record["newer_period_evidence"].get("global_latest_status") != "UNPROVEN":
        raise ValueError("FINANCIAL_CURRENCY_INTERPRETATION_PROMOTED")
    from stocklookup_core.decision.human_ai_decision_evidence_packet import FORBIDDEN

    def no_capital_fields(value):
        if isinstance(value, Mapping):
            if any(k in value for k in (*FORBIDDEN, "freshness_score", "capital_verdict")):
                raise ValueError("FINANCIAL_CURRENCY_FORBIDDEN_VERDICT")
            for child in value.values():
                no_capital_fields(child)
        elif isinstance(value, list):
            for child in value:
                no_capital_fields(child)
    no_capital_fields(record)
    baseline = record["frozen_provider_baseline"]
    eligible = _eligibility({"observed_at": baseline["last_retained_knowledge_time"],
                             "knowledge_available_at": baseline["last_retained_knowledge_time"], "publication_date": None}, boundary)
    if baseline["retained_knowledge_eligibility"] != eligible or (eligible["reason_codes"] and (baseline["measurements"] or baseline["compact_context"] is not None)):
        raise ValueError("FINANCIAL_CURRENCY_PROVIDER_CUTOFF_INVALID")
    for check in record["source_update"]["checks"]:
        eligibility = _eligibility(check["source"], boundary)
        if eligibility["reason_codes"] or check["eligibility"] != eligibility:
            raise ValueError("FINANCIAL_CURRENCY_CHECK_CUTOFF_INVALID")
        if check["receipt_integrity"] == "EMBEDDED_IDENTITY_MISMATCH" and check["kind"] != "UNVERIFIED_CHECK_RECEIPT":
            raise ValueError("FINANCIAL_CURRENCY_UNVERIFIED_RECEIPT_PROMOTED")
        for receipt in check.get("observation_receipts", []):
            if any(_time(receipt.get(k)) > boundary for k in ("observed_at", "knowledge_available_at")):
                raise ValueError("FINANCIAL_CURRENCY_CHECK_RECEIPT_AFTER_CUTOFF")
    for observation in baseline["matched_observations"]:
        eligibility = _eligibility(observation["source"], boundary)
        if observation["basis"].get("period_end") and observation["basis"]["period_end"] > boundary.date().isoformat():
            eligibility["reason_codes"].append("EXPLICIT_REPORTING_PERIOD_END_AFTER_CUTOFF")
            eligibility["state"] = "EXCLUDED_OR_UNPROVEN_AT_CUTOFF"
        if observation["eligibility"] != eligibility or (eligibility["reason_codes"] and "reported_value" in observation):
            raise ValueError("FINANCIAL_CURRENCY_PROVIDER_OBSERVATION_CUTOFF_INVALID")
    from financial_evidence_currency_contract import TARGET_INTERIM_PERIODS, TARGET_PERIODS

    for q in record["qualified_official_fields"]:
        if not _assurance_bound({**q["source"], "assurance_evidence": q.get("assurance_evidence"),
                                 "audit_or_review_status": q.get("audit_or_review_status")}):
            raise ValueError("FINANCIAL_CURRENCY_ASSURANCE_PROOF_NOT_BOUND")
        eligibility = _eligibility(q["source"], boundary)
        if eligibility["reason_codes"] or q["eligibility"] != eligibility or isinstance(q["normalized_value"], bool) or not isinstance(q["normalized_value"], (int, float)) or not math.isfinite(q["normalized_value"]):
            raise ValueError("FINANCIAL_CURRENCY_FACT_CUTOFF_INVALID")
        if q["qualification"].get("factual_status") != "qualified":
            raise ValueError("FINANCIAL_CURRENCY_FACT_NOT_QUALIFIED")
        label = q["basis"].get("native_label")
        if label not in TARGET_PERIODS or not q["basis"].get("period_end") or q["basis"]["period_end"] > projection["decision_session"]:
            raise ValueError("FINANCIAL_CURRENCY_FACT_PERIOD_NOT_ADMITTED")
        formal = "CURRENT_OFFICIAL_FACT" if label in TARGET_INTERIM_PERIODS and label.startswith(projection["decision_session"][:4]) else "HISTORICAL_OFFICIAL_FACT"
        if q["formal_temporal_status"] != formal or q["valuation_use"] not in {"NOT_PERMITTED_EARNINGS_COMPONENT_CONTEXT", "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT", "NOT_PERMITTED_FOREIGN_CURRENCY_CONTEXT", "EXISTING_METRIC_PERIOD_CONTRACT_ONLY"}:
            raise ValueError("FINANCIAL_CURRENCY_FORMAL_POLICY_CHANGED")
    return {"projection_identity": projection["artifact_identity"], "knowledge_cutoff": projection["knowledge_cutoff"],
            "temporal_use": TEMPORAL_USE, "record": deepcopy(record), "research_boundaries": list(BOUNDARIES)}


def render_markdown(projection: Mapping[str, Any]) -> str:
    """Investor presentation. Numeric comparisons only appear within exact basis groups."""
    lines = ["# Financial reporting basis", "", f"Research session: {projection['decision_session']}; knowledge cutoff: {projection['knowledge_cutoff']}.",
             "Consultation evidence only. Publication, decision-time and global latest-report proof remain separate.", ""]
    for ticker, record in projection["records"].items():
        packet_context(projection, ticker=ticker)
        baseline = record["frozen_provider_baseline"]
        labels = sorted({str(b["native_label"]) for b in record["report_period_coverage"]["provider_bases"]})
        lines.extend([f"## {ticker}", "", f"Provider: {baseline['source_update_state']}; native labels: {', '.join(labels) or 'unknown'}. Fiscal calendar requires explicit proof.",
                      f"Provider identity: `{baseline['source_context_identity']}`; retained knowledge: {baseline['last_retained_knowledge_time']}; publication: unknown.",
                      f"Entity: {record['report_period_coverage']['entity_type']}; method applicability: {canonical(record['report_period_coverage']['method_applicability'])}.",
                      f"Update interpretation: {record['investor_interpretation']['update_status']}. Historical research remains usable by field; no ticker rejection.", "",
                      "Qualified fields show newer native-period context; they do not replace provider inputs. Calendar ordering remains unproven where provider dates are missing, and the global latest report remains unproven." if "QUALIFIED_EXACT_FACT" in record["newer_period_evidence"]["known_progress_kinds"] else "No newer qualified period is established here. Missing observations do not prove a filing does not exist.",
                      f"Official retrieval receipts: {', '.join(record['source_update']['official_fact_retrieval_times']) or 'unknown'}. Qualification receipts: {', '.join(record['source_update']['official_fact_qualification_times']) or 'unknown'}. Publication proof: {record['source_update']['official_publication_state']}.", "",
                      "Provider measurements (unchanged engine values; each metric retains its own fitness and period):", "",
                      "| Engine metric | Native periods / semantics | Original value | Currency / scale as retained | Fitness |", "|---|---|---:|---|---|"])
        for m in baseline["measurements"]:
            value = m["measurement"].get("value")
            if value is not None:
                lines.append(f"| {m['feature_id']} | {canonical(m['measurement'].get('period_identity'))}; {canonical(m['measurement'].get('period_semantics'))} | {value} | {canonical(m['measurement'].get('currency'))} / {canonical(m['measurement'].get('scale'))} | {m['fitness']} |")
        missing = [{"feature_id": m["feature_id"], "fitness": m["fitness"], "reason_codes": m["reason_codes"]} for m in baseline["measurements"] if m["measurement"].get("value") is None]
        lines.extend(["", "Provider blocked/unknown fields: " + canonical(missing), "",
                      "Official exact fields (policy CURRENT does not mean newest report):", "",
                      "| Official exact field | Reporting basis | Value | Formal policy label | Citation / source |", "|---|---|---:|---|---|"])
        for q in record["qualified_official_fields"]:
            b, s = q["basis"], q["source"]
            lines.append(f"| {b['canonical_metric']} | {b['native_label']}; {b['time_basis']}; {b['cumulative_basis']}; {b['period_start']}..{b['period_end']}; {b['statement_scope']} | {q['normalized_value']} {b['currency']} (scale {b['unit_scale']}) | {q['formal_temporal_status']} | `{s['citation_id']}` / `{s['document_sha256']}`; publication {s['publication_date'] or 'unknown'} |")
        if not record["qualified_official_fields"]:
            lines.append("| unknown | No admitted exact fields | — | unchanged | Qualification gap retained |")
        lines.extend(["", "Retained filing and checked-source context:"])
        for check in record["source_update"]["checks"]:
            claimed = " The report claims a retained document; its content identity is unverified." if check["asserted_document_retained"] and check["kind"] == "UNVERIFIED_CHECK_RECEIPT" else ""
            lines.append(f"- {check['basis']['native_label']}: {check['kind']}; blocker {check['blocker'] or 'none recorded'}; citation `{check['source']['citation_id']}`; receipt {check['source']['observed_at']}. This is bounded source-scope evidence.{claimed}")
        lines.extend(["", "Research limits: " + "; ".join(record["investor_interpretation"]["reason_codes"]),
                      "Qualification gaps: " + canonical(record["newer_period_evidence"]["qualification_rejections"]),
                      "Excluded or unknown cutoff receipts: " + canonical(record["knowledge_cutoff_eligibility"]), ""])
    lines.extend(["## Selected comparison", "", "Only identical metric/date/duration/scope/currency/unit/entity bases share a group; no cross-basis ranking.", "",
                  "| Metric / exact reporting basis | Securities and unchanged values |", "|---|---|"])
    for group in projection["selected_comparison"]["basis_groups"]:
        b = group["basis"]
        lines.append(f"| {b['canonical_metric']}; {b['period_start']}..{b['period_end']}; {b['time_basis']}; {b['cumulative_basis']}; {b['statement_scope']}; {b['currency']} (scale {b['unit_scale']}); {group['entity_type']} | " + "; ".join(f"{m['ticker']}: {m['value']}" for m in group["members"]) + " |")
    lines.extend(["", "Coverage (explicit selected denominator): " + canonical(projection["coverage"]), "",
                  "No metric replacement, annualization, FX conversion, vote/valuation change or capital verdict."])
    return "\n".join(lines) + "\n"
