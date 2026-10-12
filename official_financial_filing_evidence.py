"""Fail-closed financial fact admission and append-only overlay preparation.

Pure document-metadata envelopes are explicitly re-exported from their lower
owner for compatibility. Source, literal value/identity, assurance, period and
knowledge/use proofs remain admission prerequisites; parsing and acquisition
remain outside this module. No provider observation is promoted by agreement.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


from stocklookup_core.evidence.financial_metadata_envelope import (
    VERSION, CONTRACT_VERSION, REQUIRED_METADATA, METADATA_QUALIFIED, METADATA_BLOCKED,
    canonical_json, stable_id, EvidenceSpan, _span, qualify_document_metadata,
)


LEGACY_ROW_ADMISSION_PATH = "config/official_financial_legacy_row_admission_v1.json"
LEGACY_ROW_PROOF_SUBSTITUTED = frozenset({"DOCUMENT_METADATA_PROOF_MISSING", "RETAINED_SOURCE_PROOF_UNAVAILABLE",
    "LITERAL_METRIC_ROW_PROOF_MISSING", "LITERAL_VALUE_PROOF_MISSING"})


@lru_cache(maxsize=1)
def _legacy_row_admission() -> Mapping[str, Any]:
    pin = json.loads((Path(__file__).resolve().parent / LEGACY_ROW_ADMISSION_PATH).read_text(encoding="utf-8"))
    return {"pin": pin, "rows": {entry["row_sha256"]: entry for entry in pin["rows"]}}


def legacy_row_admission_entry(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Exact-row membership in the closed, hash-sealed v2 legacy set; never a shape test.

    Only rows that predate the document-metadata schema and are byte-for-byte the rows
    published under the governed ingress v2 contract qualify. Any edited, re-derived or
    new row has a different hash and must carry modern retained-source proof instead.
    """
    if isinstance(row.get("document_metadata"), Mapping):
        return None
    loaded = _legacy_row_admission()
    contracts = loaded["pin"]["governing_contracts"]
    if any(row.get(name) != value for name, value in contracts.items()):
        return None
    digest = hashlib.sha256(canonical_json({k: v for k, v in row.items() if k != "admission"}).encode("utf-8")).hexdigest()
    entry = loaded["rows"].get(digest)
    if entry is None or entry["document_sha256"] != row.get("document_sha256") or entry["ticker"] != row.get("ticker"):
        return None
    return entry


def admit_official_financial_fact(row: Mapping[str, Any], **context) -> dict[str, Any]:
    """Malformed proof shapes are blocked deterministically before any consumer can promote them."""
    try:
        return _admit_official_financial_fact(row, **context)
    except (TypeError, ValueError, AttributeError, KeyError, OverflowError):
        result = {"state":"BLOCKED", "reason_codes":["MALFORMED_SOURCE_PROOF"],
            "intended_use":context.get("intended_use","CURRENT_RESEARCH_FACTUAL_AUTHORITY"),
            "document_sha256":row.get("document_sha256") if isinstance(row,Mapping) else None}
        result["admission_id"] = stable_id(result)
        return result


def _admit_official_financial_fact(row: Mapping[str, Any], *, source_record: Mapping[str, Any] | None = None,
        retained_bytes: bytes | None = None, registry: Mapping[str, Any] | None = None,
        document_pages: Mapping[int, str] | None = None,
        cutoff: str | None = None, intended_use: str = "CURRENT_RESEARCH_FACTUAL_AUTHORITY") -> dict[str, Any]:
    """Pure common admission. Retained bytes and registry arrive independently of row claims.

    An overlay seal, SHA string or caller boolean cannot replace the retained source.
    This projection never repairs or publishes evidence and never expands period authority.
    """
    from datetime import datetime
    from official_source_registry import admit, ADMITTED
    from official_financial_assurance_evidence import assurance_proof_is_bound
    from official_financial_period_identity import (period_bounds, recognize_statement_period,
        recognize_scope, recognize_currency, recognize_unit_scale, recognize_audit_or_review)
    from official_financial_value_evidence import parse_accounting_integer
    from financial_evidence_currency_contract import TARGET_PERIODS

    reasons, missing = [], []
    sha = str(row.get("document_sha256") or "")
    metadata = row.get("document_metadata")
    if not isinstance(metadata, Mapping):
        missing.append("DOCUMENT_METADATA_PROOF_MISSING")
    else:
        document = dict(metadata.get("document") or {})
        candidate = {"issuer_identity": metadata.get("issuer_identity"), "entity_type": metadata.get("entity_type"),
            "document": {**document, "sha256": document.get("document_sha256")},
            "metadata": {**(metadata.get("metadata_claims") or {}), **(metadata.get("optional_metadata_claims") or {})}}
        replay = qualify_document_metadata(candidate)
        if (replay["qualification_status"] != METADATA_QUALIFIED or metadata.get("qualification_status") != METADATA_QUALIFIED
                or replay["evidence_envelope_id"] != metadata.get("evidence_envelope_id")):
            reasons.append("DOCUMENT_METADATA_NOT_QUALIFIED")
        if document.get("document_sha256") != sha or metadata.get("issuer_identity") != row.get("ticker"):
            reasons.append("DOCUMENT_ISSUER_IDENTITY_MISMATCH")
        claims = metadata.get("metadata_claims") or {}
        if document_pages is None:
            missing.append("RETAINED_DOCUMENT_TEXT_PROOF_UNAVAILABLE")
        else:
            for name, claim in claims.items():
                span = (claim or {}).get("evidence_span") or {}
                page = document_pages.get(span.get("source_page"), "")
                literal = " ".join(str(span.get("text") or "").split()).lower()
                if not literal or literal not in " ".join(page.split()).lower():
                    reasons.append("METADATA_LITERAL_NOT_IN_RETAINED_DOCUMENT")
            period_page = document_pages.get(((claims.get("reporting_period") or {}).get("evidence_span") or {}).get("source_page"), "")
            if recognize_statement_period(period_page)["period"] != row.get("reporting_period"):
                reasons.append("RETAINED_STATEMENT_PERIOD_MISMATCH")
            for name, recognizer in (("statement_scope", recognize_scope), ("currency", recognize_currency), ("unit_scale", recognize_unit_scale)):
                claim = claims.get(name) or {}
                page = document_pages.get((claim.get("evidence_span") or {}).get("source_page"), "")
                if recognizer(page).get(name) != claim.get("value"):
                    reasons.append(f"RETAINED_{name.upper()}_NOT_EXPLICIT")
            proof_page = document_pages.get((row.get("assurance_evidence") or {}).get("page_number"), "")
            opinion_page = document_pages.get(((row.get("assurance_evidence") or {}).get("opinion_evidence") or {}).get("page_number"), "")
            if recognize_audit_or_review(proof_page + "\n" + opinion_page)["audit_or_review_status"] != row.get("audit_or_review_status"):
                reasons.append("RETAINED_ASSURANCE_TEXT_NOT_EXPLICIT")
            proof = row.get("assurance_evidence") or {}
            native = proof.get("native_text_evidence")
            if isinstance(native, Mapping):
                from official_financial_assurance_evidence import resolve_native_document_assurance
                numbers = native.get("page_numbers") or []
                if (not numbers or len(numbers)>8 or any(number not in document_pages for number in numbers)
                        or resolve_native_document_assurance(sha, {number:document_pages[number] for number in numbers}).get("evidence_id") != proof.get("evidence_id")):
                    reasons.append("NATIVE_ASSURANCE_SOURCE_REPLAY_MISMATCH")
            import re
            if not re.search(r"\b" + re.escape(str(row.get("ticker") or "")) + r"\b",
                    "\n".join(text for number,text in document_pages.items() if number <= 8), re.IGNORECASE):
                missing.append("RETAINED_ISSUER_LITERAL_PROOF_UNAVAILABLE")
        for name in ("reporting_period", "statement_scope", "currency"):
            if (claims.get(name) or {}).get("value") != row.get(name):
                reasons.append(f"DOCUMENT_{name.upper()}_MISMATCH")
        period_claim = claims.get("reporting_period") or {}
        if recognize_statement_period((period_claim.get("evidence_span") or {}).get("text"))["period"] != row.get("reporting_period"):
            reasons.append("STATEMENT_PERIOD_NOT_EXPLICIT")
        if (claims.get("unit_scale") or {}).get("value") != row.get("source_unit_scale", row.get("unit_scale")):
            reasons.append("DOCUMENT_UNIT_SCALE_MISMATCH")
    if source_record is None or retained_bytes is None or registry is None:
        missing.append("RETAINED_SOURCE_PROOF_UNAVAILABLE")
    else:
        source = source_record
        from urllib.parse import urlsplit
        from financial_evidence_currency_contract import ISSUER_IR_INDEX_SEEDS, DIRECT_TARGET_LOCATORS, ENTITY_FAMILY
        if source.get("source_id") == "issuer_ir":
            locators = [ISSUER_IR_INDEX_SEEDS.get(str(row.get("ticker")), "")] + [
                item["url"] for item in DIRECT_TARGET_LOCATORS if item["ticker"] == row.get("ticker")]
            hosts = {str(urlsplit(url).hostname or "").removeprefix("www.") for url in locators if url}
            actual_host = str(urlsplit(str(source.get("canonical_url") or "")).hostname or "").removeprefix("www.")
            final_host = str(urlsplit(str(source.get("final_url") or source.get("canonical_url") or "")).hostname or "").removeprefix("www.")
            if not hosts:
                missing.append("ISSUER_DOMAIN_BINDING_PROOF_UNAVAILABLE")
            elif actual_host not in hosts or final_host not in hosts:
                reasons.append("ISSUER_SOURCE_DOMAIN_MISMATCH")
        else:
            missing.append("EXCHANGE_ISSUER_BINDING_PROOF_UNAVAILABLE")
        if isinstance(metadata, Mapping) and metadata.get("entity_type") != ENTITY_FAMILY.get(str(row.get("ticker"))):
            reasons.append("ISSUER_STATEMENT_FAMILY_MISMATCH")
        if hashlib.sha256(retained_bytes).hexdigest() != sha or source.get("sha256") != sha:
            reasons.append("RETAINED_DOCUMENT_HASH_MISMATCH")
        if source.get("acquisition_status") != "retained" or source.get("ticker") != row.get("ticker"):
            reasons.append("RETAINED_SOURCE_IDENTITY_MISMATCH")
        if source.get("reporting_period") != row.get("reporting_period"):
            reasons.append("RETAINED_SOURCE_PERIOD_MISMATCH")
        status = row.get("audit_or_review_status")
        expected_class = "audited_annual_financial_statements" if status == "audited" else "reviewed_interim_financial_statements"
        if source.get("document_class") != expected_class:
            reasons.append("DOCUMENT_CLASS_NOT_FINANCIAL_STATEMENT")
        url = source.get("final_url") or source.get("canonical_url") or ""
        if row.get("source_locator") is not None and row.get("source_locator") not in {source.get("canonical_url"),source.get("final_url")}:
            reasons.append("FACT_SOURCE_LOCATOR_MISMATCH")
        try:
            source_time = datetime.fromisoformat(str(source.get("observed_at")).replace("Z", "+00:00"))
            if source_time.tzinfo is None:
                raise ValueError()
            source_admitted = admit(str(source.get("source_id") or ""), str(url), expected_class, registry=registry, now=source_time)["decision"] == ADMITTED
        except (ValueError, TypeError):
            source_admitted = False
        if not source_admitted:
            reasons.append("OFFICIAL_SOURCE_NOT_ADMITTED")
        if isinstance(metadata, Mapping):
            doc = metadata.get("document") or {}
            if (doc.get("source_locator") not in {source.get("canonical_url"), source.get("final_url")}
                    or doc.get("source_id") != source.get("source_id") or doc.get("document_id") != source.get("document_id")):
                reasons.append("SOURCE_DOCUMENT_LOCATOR_MISMATCH")
    if row.get("assurance_evidence") is None:
        missing.append("DOCUMENT_ASSURANCE_PROOF_MISSING")
    elif not assurance_proof_is_bound(row.get("audit_or_review_status"), row.get("assurance_evidence"), document_sha256=sha):
        reasons.append("DOCUMENT_ASSURANCE_PROOF_NOT_BOUND")
    if row.get("qualification_state") != "QUALIFIED" or row.get("blockers") or row.get("conflicts"):
        reasons.append("FACT_QUALIFICATION_BLOCKED")
    if row.get("metadata_qualification") in {"BLOCKED", "UNQUALIFIED", METADATA_BLOCKED} or row.get("qualification_status") in {"BLOCKED", "OFFICIAL_FACT_CANDIDATE_BLOCKED"}:
        reasons.append("FACT_QUALIFICATION_BLOCKED")
    period = str(row.get("reporting_period") or "")
    if period not in TARGET_PERIODS:
        reasons.append("SOURCE_PERIOD_NOT_ADMITTED")
    else:
        start, end = period_bounds(period)
        if (row.get("period_start"), row.get("period_end")) != (start, end):
            reasons.append("PERIOD_BOUNDS_MISMATCH")
        if row.get("period_type") != ("annual" if period.isdigit() else "interim"):
            reasons.append("PERIOD_TYPE_MISMATCH")
        if (period.isdigit() and row.get("audit_or_review_status") != "audited"):
            reasons.append("ANNUAL_ASSURANCE_NOT_AUDITED")
    if not row.get("canonical_metric") or not row.get("citation_id") or row.get("statement_scope") != "consolidated":
        reasons.append("FACT_SEMANTIC_IDENTITY_INCOMPLETE")
    from financial_statement_template_recognizer import GENERIC_METRIC_RULES, _normalize_text
    from stocklookup_core.evidence.financial_row_identity import row_label_supports_metric
    metric = str(row.get("canonical_metric") or "")
    from stocklookup_core.evidence.financial_row_identity import LINE_CODE_IDENTITY_CONFLICTS
    if (metric,str(row.get('line_code') or '')) in LINE_CODE_IDENTITY_CONFLICTS:
        reasons.append("METRIC_LINE_CODE_IDENTITY_CONFLICT")
    label = row.get("raw_row_label")
    span = row.get("source_span")
    if not label or not isinstance(span, Mapping):
        missing.append("LITERAL_METRIC_ROW_PROOF_MISSING")
    else:
        spec = GENERIC_METRIC_RULES.get("cash_and_equivalents" if metric == "cash_and_cash_equivalents" else metric)
        if spec:
            if (not any(anchor in _normalize_text(str(label)) for anchor in spec["label_anchors"])
                    or row.get("statement_family") != str(spec["statement_type"])):
                reasons.append("METRIC_STATEMENT_IDENTITY_MISMATCH")
        elif metric not in {"investment_property_disposal_result", "provision_charge_or_reversal_adjustment"}:
            missing.append("METRIC_SOURCE_TEMPLATE_PROOF_UNAVAILABLE")
        if not row_label_supports_metric(metric, str(label)):
            reasons.append("METRIC_LITERAL_LABEL_NOT_SUPPORTED")
        if span.get("document_sha256") != sha or span.get("citation_id") != row.get("citation_id"):
            reasons.append("VALUE_CITATION_NOT_DOCUMENT_BOUND")
        span_text = " ".join(str(span.get("text") or "").split())
        if " ".join(str(label).split()) not in span_text:
            reasons.append("METRIC_LITERAL_NOT_IN_CITED_SPAN")
        if document_pages is not None:
            page = document_pages.get(span.get("source_page"), "")
            if not span_text or span_text not in " ".join(page.split()):
                reasons.append("VALUE_SPAN_NOT_IN_RETAINED_DOCUMENT")
    try:
        value = row.get("normalized_value", row.get("parsed_numeric_value"))
        if "value" in row and "normalized_value" in row and row['value'] != value:
            reasons.append("FACT_VALUE_ALIAS_CONFLICT")
        if row.get("unit_scale") != 1 or isinstance(row.get("unit_scale"), bool):
            reasons.append("NORMALIZED_BASE_UNIT_REQUIRED")
        scale = row.get("source_unit_scale", row.get("unit_scale"))
        raw = row.get("raw_value_text", row.get("raw_numeric_text"))
        if raw is None:
            missing.append("LITERAL_VALUE_PROOF_MISSING")
        if isinstance(value, bool) or not isinstance(scale, int) or isinstance(scale, bool) or scale <= 0:
            raise ValueError()
        if raw is not None and parse_accounting_integer(raw) * scale != value:
            raise ValueError()
        if raw is not None and isinstance(span, Mapping) and str(raw) not in str(span.get("text") or ""):
            raise ValueError()
        if raw is not None and document_pages is not None and str(raw) not in " ".join(document_pages.values()):
            raise ValueError()
    except (ValueError, TypeError):
        reasons.append("LITERAL_VALUE_NORMALIZATION_NOT_BOUND")
    def time(value):
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp
    try:
        observed, known = time(row.get("observed_at")), time(row.get("knowledge_available_at"))
        if known < observed or known.date().isoformat() < str(row.get("period_end")):
            reasons.append("KNOWLEDGE_TIME_INVALID")
        if source_record and observed < time(source_record.get("observed_at")):
            reasons.append("KNOWLEDGE_PRECEDES_RETAINED_SOURCE")
        if cutoff and known > time(cutoff):
            reasons.append("AFTER_KNOWLEDGE_CUTOFF")
        publication = row.get("publication_date")
        if publication:
            if len(str(publication)) == 10:
                if str(publication) > known.date().isoformat():
                    reasons.append("PUBLICATION_AFTER_KNOWLEDGE_TIME")
            elif time(publication) > known:
                reasons.append("PUBLICATION_AFTER_KNOWLEDGE_TIME")
    except (ValueError, TypeError):
        reasons.append("QUALIFIED_TIMESTAMP_MISSING_OR_INVALID")
    if intended_use in {"CANONICAL_CITATION", "VALUATION_INPUT_WHERE_METRIC_PERMITS"} and (
            row.get("currency") != "VND" or row.get("context_kind") in {"AUDITED_ANNUAL_FIELD", "EARNINGS_QUALITY_COMPONENT"}):
        reasons.append("INTENDED_USE_NOT_ADMITTED")
    if intended_use not in {"CURRENT_RESEARCH_FACTUAL_AUTHORITY", "CANONICAL_CITATION", "VALUATION_INPUT_WHERE_METRIC_PERMITS"}:
        reasons.append("INTENDED_USE_OUTSIDE_CONTRACT")
    legacy = legacy_row_admission_entry(row)
    if legacy is not None:
        # Version-specific: the pinned v2 row substitutes only for the newer document-metadata
        # and literal-span schema. Assurance binding, period, scope, units, time and use still apply.
        missing = [reason for reason in missing if reason not in LEGACY_ROW_PROOF_SUBSTITUTED]
    reasons = sorted(set(reasons + missing))
    state = "BLOCKED" if reasons and any(reason not in missing for reason in reasons) else "UNKNOWN" if missing else "ADMITTED"
    if reasons == ["INTENDED_USE_OUTSIDE_CONTRACT"]:
        state = "INAPPLICABLE"
    result = {"state": state, "reason_codes": reasons, "intended_use": intended_use,
        "document_sha256": sha, "metadata_evidence_id": metadata.get("evidence_envelope_id") if isinstance(metadata, Mapping) else None}
    if legacy is not None:
        pin = _legacy_row_admission()["pin"]
        result.update(admission_basis=pin["admission_basis"], legacy_row_sha256=legacy["row_sha256"],
                      evidence_classification=dict(pin["evidence_classification"]))
    elif state == "ADMITTED":
        result["admission_basis"] = "RETAINED_SOURCE_REPLAY"
    result["admission_id"] = stable_id({**result, "row": {k: v for k, v in row.items() if k != "admission"}, "cutoff": cutoff})
    return result


OFFICIAL_FACT_KEY_FIELDS = ("ticker", "canonical_metric", "reporting_period", "statement_scope")
OFFICIAL_FACT_VALUE_FIELDS = ("normalized_value", "currency", "unit_scale")


def official_fact_key(row: Mapping[str, Any]) -> tuple:
    return tuple(row.get(name) for name in OFFICIAL_FACT_KEY_FIELDS)


def plan_official_overlay_publication(rows, *, retained_text: str, admission) -> dict[str, Any]:
    """Validate the entire ingress and plan an append-only, order-independent publication.

    Every candidate, including an exact replay of a retained key, must pass the common
    admission. A retained key with the same value identity keeps its first qualification;
    a different value is a conflict. Distinct candidates for one new key are refused rather
    than resolved by input order. Historical claims are preserved, never requalified.
    """
    candidates = list(rows)
    plan = {"text": None, "appended": [], "replayed_keys": [], "prior_count": 0}
    prior = [json.loads(line) for line in retained_text.splitlines() if line.strip()]
    plan["prior_count"] = len(prior)
    if not candidates:
        return plan
    blocked = []
    for row in candidates:
        decision = admission(row)
        if decision["state"] != "ADMITTED":
            blocked.append({"key": [str(part) for part in official_fact_key(row)], "state": decision["state"],
                "reason_codes": list(decision.get("reason_codes") or [])})
    if blocked:
        blocked.sort(key=canonical_json)
        raise ValueError("OFFICIAL_PUBLICATION_CANDIDATE_NOT_ADMITTED:" + canonical_json(blocked))
    retained = {}
    for row in prior:
        retained.setdefault(official_fact_key(row), row)
    proposed: dict[tuple, dict[str, str]] = {}
    for row in candidates:
        proposed.setdefault(official_fact_key(row), {})[canonical_json(row)] = row
    appended, replayed = [], []
    for key in sorted(proposed, key=lambda item: canonical_json(list(item))):
        variants = proposed[key]
        values = {canonical_json([row.get(name) for name in OFFICIAL_FACT_VALUE_FIELDS]) for row in variants.values()}
        if key in retained:
            first = canonical_json([retained[key].get(name) for name in OFFICIAL_FACT_VALUE_FIELDS])
            if values != {first}:
                raise ValueError("APPEND_ONLY_OFFICIAL_FACT_CONFLICT")
            replayed.append(list(key))
            continue
        if len(values) != 1:
            raise ValueError("OFFICIAL_PUBLICATION_EXACT_KEY_CONFLICT")
        if len(variants) != 1:
            raise ValueError("OFFICIAL_PUBLICATION_DUPLICATE_KEY_AMBIGUOUS_CITATION")
        appended.append(next(iter(variants.values())))
    plan["appended"], plan["replayed_keys"] = appended, replayed
    if appended:
        plan["text"] = retained_text + ("\n" if retained_text and not retained_text.endswith("\n") else "") + "".join(
            canonical_json(row) + "\n" for row in appended)
    return plan


def prepare_official_overlay_publication(rows, *, retained_text: str, admission) -> str | None:
    """Append-only publication bytes, or None when no new admitted key exists."""
    return plan_official_overlay_publication(rows, retained_text=retained_text, admission=admission)["text"]


def append_precedence_for_keys(retained_text: str, precedence_rows, keys) -> str:
    """Append companion precedence rows only for newly published fact keys, once each."""
    wanted = {tuple(key) for key in keys}
    existing = {line.strip() for line in retained_text.splitlines() if line.strip()}
    lines = []
    for row in precedence_rows:
        key = row.get("key") or {}
        identity = (key.get("ticker"), key.get("metric"), key.get("period"), key.get("scope"))
        line = json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if identity in wanted and line not in existing and line not in lines:
            lines.append(line)
    return retained_text + ("\n" if retained_text and lines and not retained_text.endswith("\n") else "") + "".join(
        line + "\n" for line in sorted(lines))
