"""Explicit, offline business disclosures; no acquisition, store, or financial authority.

Consumes the existing document-manifest vocabulary and exact supplied source bytes.
Research fixtures are always labeled and never promoted by an approved host alone.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from stocklookup_core.evidence.official_issuer_disclosure_registry import project_disclosure_record

VERSION = "business_update_observations/v1"
CLASSES = {
    "official_operating_update": "OFFICIAL_OPERATING_UPDATE",
    "issuer_operating_update": "OFFICIAL_OPERATING_UPDATE",
    "preliminary_earnings_disclosure": "PRELIMINARY_EARNINGS_DISCLOSURE",
    "audited_annual_financial_statements": "OFFICIAL_FINANCIAL_STATEMENT",
    "reviewed_interim_financial_statements": "OFFICIAL_FINANCIAL_STATEMENT",
    "unreviewed_financial_statements": "OFFICIAL_FINANCIAL_STATEMENT",
    "quarterly_financial_statements": "OFFICIAL_FINANCIAL_STATEMENT",
    "management_guidance": "MANAGEMENT_GUIDANCE",
    "third_party_report": "THIRD_PARTY_REPORT",
}


def _identity(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _instant(value: Any) -> datetime | None:
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return instant if instant.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def session_cutoff(session: str) -> str:
    """The existing Integrated Decision cutoff, not an exchange-close inference."""
    return date.fromisoformat(session).isoformat() + "T15:00:00+07:00"


def candidate_manifest(candidate: Mapping[str, Any], *, source_id: str | None = None) -> dict[str, Any]:
    """Translate research-candidate metadata without inventing source/clock authority.

    Grok's report is a candidate, not a store manifest. A printed local clock with
    no source timezone stays unqualified; PDF ModDate never becomes publication.
    The caller may identify the existing source owner explicitly, not activate it.
    """
    if candidate.get("record_type") != "official_issuer_disclosure/v1-candidate":
        raise ValueError("DISCLOSURE_CANDIDATE_SCHEMA_UNSUPPORTED")
    required = ("ticker", "issuer_name", "evidence_id", "document_type", "document_url", "sha256", "observation_at")
    if any(not candidate.get(key) for key in required):
        raise ValueError("DISCLOSURE_CANDIDATE_IDENTITY_INCOMPLETE")
    sha = candidate["sha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("DISCLOSURE_CANDIDATE_HASH_INVALID")
    return dict(ticker=candidate["ticker"], issuer_name=candidate["issuer_name"],
                document_id=candidate["evidence_id"], document_type=candidate["document_type"],
                source_id=source_id or candidate.get("source_id"), source_url=candidate["document_url"],
                content_sha256=sha, observed_at=candidate["observation_at"],
                known_at=candidate["observation_at"], published_at=candidate.get("published_at"),
                declared_publication=candidate.get("declared_publication"),
                declared_publication_timezone=candidate.get("declared_publication_timezone"),
                assurance=candidate.get("assurance", "UNKNOWN"),
                candidate_restriction=candidate.get("qualification_restriction"),
                supersedes_document_id=candidate.get("supersedes_document_id"))


def _fact(raw: Mapping[str, Any], text: str, document_class: str) -> dict[str, Any]:
    fact = copy.deepcopy(dict(raw))
    blockers = []
    required = ("native_label", "concept", "value", "unit", "native_value", "native_unit",
                "basis", "sector", "period_label", "span")
    if any(fact.get(key) is None or fact.get(key) == "" for key in required):
        blockers.append("FACT_IDENTITY_INCOMPLETE")
    span = fact.get("span") or {}
    start, end = span.get("start"), span.get("end")
    excerpt = (text[start:end] if type(start) is int and type(end) is int
               and 0 <= start < end <= len(text) else "")
    if not excerpt or excerpt != span.get("text"):
        blockers.append("SOURCE_SPAN_MISMATCH")
    if any(str(fact.get(key) or "") not in excerpt for key in
           ("native_label", "native_value", "native_unit", "period_label")):
        blockers.append("NATIVE_FACT_NOT_IN_SPAN")
    try:
        value = Decimal(str(fact["value"]))
        # Native numeric tokens may use Vietnamese decimal commas; no scale inference.
        native = Decimal(str(fact["native_value"]).replace(",", "."))
        if not value.is_finite() or native != value:
            blockers.append("NUMERIC_TOKEN_MISMATCH")
    except (KeyError, InvalidOperation, ValueError):
        blockers.append("VALUE_NOT_FINITE_DECIMAL")
    if not fact.get("period_proof") or fact["period_proof"] not in text:
        blockers.append("PERIOD_NOT_SOURCE_BOUND")
    try:
        begin_raw, end_raw = fact.get("period_start"), fact.get("period_end")
        begin = date.fromisoformat(begin_raw) if begin_raw else None
        finish = date.fromisoformat(end_raw) if end_raw else None
        if bool(begin) != bool(finish) or begin and begin > finish:
            blockers.append("PERIOD_NOT_SOURCE_BOUND")
        # Explicit ISO endpoints must occur in the supplied period proof; no Q3/9M inference.
        if begin and any(fact[key] not in str(fact.get("period_proof")) for key in ("period_start", "period_end")):
            blockers.append("PERIOD_ENDPOINTS_NOT_PROVEN")
    except (KeyError, TypeError, ValueError):
        blockers.append("PERIOD_UNKNOWN")
    unit = fact.get("unit")
    native_units = {"triệu tấn": "million tonnes", "tấn": "tonnes", "%": "percent", "tỷ đồng": "billion VND"}
    if unit != native_units.get(fact.get("native_unit"), fact.get("native_unit")):
        blockers.append("UNIT_CONVERSION_NOT_AUTHORIZED")
    if fact.get("value_relation", "EXACT") not in {"EXACT", "GREATER_THAN", "APPROXIMATE"}:
        blockers.append("VALUE_RELATION_UNKNOWN")
    kind = fact.get("metric_kind")
    if kind not in {"PRODUCTION", "SALES", "SHIPMENTS", "CAPACITY", "ORDERS", "EARNINGS", "GUIDANCE"}:
        blockers.append("METRIC_KIND_UNKNOWN")
    if document_class == "OFFICIAL_OPERATING_UPDATE" and kind == "EARNINGS":
        blockers.append("OPERATING_UPDATE_IS_NOT_EARNINGS")
    if kind in {"PRODUCTION", "SALES", "SHIPMENTS", "CAPACITY"} and unit not in {"tonnes", "million tonnes", "units", "percent"}:
        blockers.append("OPERATING_UNIT_NOT_COMPATIBLE")
    if document_class == "PRELIMINARY_EARNINGS_DISCLOSURE" and (kind != "EARNINGS" or not fact.get("accounting_scope")):
        blockers.append("PRELIMINARY_ACCOUNTING_IDENTITY_UNKNOWN")
    if kind == "EARNINGS" and unit not in {"VND", "million VND", "billion VND", "USD", "million USD"}:
        blockers.append("EARNINGS_UNIT_NOT_COMPATIBLE")
    if document_class == "MANAGEMENT_GUIDANCE" and kind != "GUIDANCE":
        blockers.append("GUIDANCE_IS_NOT_ACTUAL")
    if fact.get("sector_applicability") is not True:
        blockers.append("SECTOR_APPLICABILITY_UNKNOWN_OR_FALSE")
    comparison = fact.get("comparison")
    if comparison:
        proof = comparison.get("source_span")
        if (comparison.get("basis") not in {"YoY", "QoQ", "UNKNOWN"} or comparison.get("method") != "EXPLICIT"
                or comparison.get("unit") != "percent" or not proof or proof not in excerpt
                or str(comparison.get("native_value") or "") not in proof):
            blockers.append("COMPARISON_NOT_SOURCE_BOUND")
        try:
            if Decimal(str(comparison["value"])) != Decimal(comparison["native_value"].replace(",", ".")):
                blockers.append("COMPARISON_NUMERIC_MISMATCH")
        except (KeyError, TypeError, AttributeError, InvalidOperation):
            blockers.append("COMPARISON_NUMERIC_MISMATCH")
        comparison["qualification"] = "UNKNOWN_BASIS" if comparison.get("basis") == "UNKNOWN" else "SOURCE_STATED_COMPARISON"
    fact["blockers"] = sorted(set(blockers))
    fact["fact_identity"] = "business_fact:" + _identity(raw)
    fact["qualification"] = "SOURCE_BOUND_RESEARCH" if not blockers else "UNKNOWN"
    fact["limitations"] = sorted(set(fact.get("limitations") or []) | ({"PERIOD_ENDPOINTS_UNKNOWN"} if not fact.get("period_start") else set()))
    if comparison and comparison.get("basis") == "UNKNOWN":
        fact["limitations"].append("COMPARATIVE_PERIOD_NOT_STATED")
    return fact


def observe(*, manifest: Mapping[str, Any], source_bytes: bytes | None,
            observations: Sequence[Mapping[str, Any]], cutoff: str,
            route_admission: Mapping[str, Any] | None = None, research_fixture: bool = False) -> dict[str, Any]:
    """No implicit latest loader. Manifest timestamps are independent; no fallback time.

    Fixture use permits source-bound demonstrations on unapproved types, but grants
    zero official qualification. Real documents still require the existing route.
    """
    manifest = copy.deepcopy(dict(manifest))
    cls = CLASSES.get(manifest.get("document_type"), "UNKNOWN")
    blockers = []
    if not all(manifest.get(key) for key in ("ticker", "issuer_name", "source_id", "document_id", "source_url")):
        blockers.append("ISSUER_SOURCE_IDENTITY_MISSING")
    # The existing registry owner supplies its decision; dependency direction stays
    # evidence -> evidence, never a new package -> root registry dependency.
    route = copy.deepcopy(dict(route_admission or {"decision": "refused", "reason": "REGISTRY_DECISION_NOT_SUPPLIED"}))
    route_bound = all(route.get(key) == manifest.get(field) for key, field in
                      (("source_id", "source_id"), ("url", "source_url"), ("document_type", "document_type")))
    if route.get("decision") != "admitted" or not route_bound:
        blockers.append("SOURCE_ROUTE_UNAPPROVED")
    if cls == "UNKNOWN":
        blockers.append("DOCUMENT_CLASS_UNKNOWN")
    limit = _instant(cutoff)
    if limit is None:
        raise ValueError("TIMEZONE_AWARE_CUTOFF_REQUIRED")
    for key in ("published_at", "observed_at", "known_at"):
        instant = _instant(manifest.get(key))
        if instant is None:
            blockers.append(key.upper() + "_UNKNOWN")
        elif instant > limit:
            blockers.append(key.upper() + "_AFTER_CUTOFF")
    times = [_instant(manifest.get(k)) for k in ("published_at", "observed_at", "known_at")]
    if all(times):
        if times[2] < times[1]:
            blockers.append("KNOWN_AT_PRECEDES_OBSERVATION")
        if times[2] < times[0]:
            blockers.append("KNOWN_AT_PRECEDES_PUBLICATION")
        if times[1] < times[0]:
            blockers.append("OBSERVATION_PRECEDES_PUBLICATION")
    digest = hashlib.sha256(source_bytes).hexdigest() if source_bytes is not None else None
    if digest is None:
        blockers.append("NO_SOURCE_BYTES")
    elif digest != manifest.get("content_sha256"):
        blockers.append("SOURCE_HASH_MISMATCH")
    try:
        text = source_bytes.decode("utf-8") if source_bytes is not None else ""
    except UnicodeDecodeError:
        text = ""
        if cls != "OFFICIAL_FINANCIAL_STATEMENT":
            blockers.append("SOURCE_TEXT_UNAVAILABLE")
    if cls == "PRELIMINARY_EARNINGS_DISCLOSURE" and manifest.get("assurance") != "PRELIMINARY_UNASSURED":
        blockers.append("PRELIMINARY_ASSURANCE_MISMATCH")
    if cls == "OFFICIAL_FINANCIAL_STATEMENT":
        blockers.append("ROUTE_TO_EXISTING_FINANCIAL_OWNER")
    if cls == "THIRD_PARTY_REPORT":
        blockers.append("PRIMARY_EVIDENCE_ABSENT")
    facts = [_fact(raw, text, cls) for raw in observations]
    if not facts and cls != "OFFICIAL_FINANCIAL_STATEMENT":
        blockers.append("NO_OBSERVATIONS")
    disqualifying = set(blockers) - ({"SOURCE_ROUTE_UNAPPROVED"} if research_fixture else set())
    for fact in facts:
        if disqualifying:
            fact["qualification"] = "UNKNOWN"
        fact["coverage_kind"] = "OFFLINE_FIXTURE" if research_fixture else "REAL_RETAINED_INPUT"
    usable = [fact for fact in facts if fact["qualification"] == "SOURCE_BOUND_RESEARCH"]
    disclosure = project_disclosure_record(manifest_record=manifest, source_id=str(manifest.get("source_id") or ""))
    result = dict(contract_version=VERSION, event_type="EARNINGS_BUSINESS_UPDATE",
                  ticker=manifest.get("ticker"), issuer_name=manifest.get("issuer_name"),
                  document_class=cls, disclosure=disclosure, manifest=manifest,
                  source_sha256=digest, cutoff=cutoff, observations=facts, blockers=sorted(set(blockers)),
                  research_usable=bool(usable), coverage_kind="OFFLINE_FIXTURE" if research_fixture else "REAL_RETAINED_INPUT",
                  official_qualified=False, accounting_fact_authority=False,
                  route_decision=route, authority_effect="NONE", is_actionable=False,
                  financial_owner_input=(disclosure if not research_fixture and cls == "OFFICIAL_FINANCIAL_STATEMENT" and not
                                        (set(blockers) - {"ROUTE_TO_EXISTING_FINANCIAL_OWNER"}) else None))
    result["observation_identity"] = VERSION + ":" + _identity(result)
    return result


def research_context(envelopes: Sequence[Mapping[str, Any]], *, ticker: str, cutoff: str) -> dict[str, Any]:
    """Revalidate signed envelope/time, deduplicate, supersede only proven same-issuer documents.

    No new global event registry/status machine; this is a non-voting context projection.
    """
    limit = _instant(cutoff)
    if limit is None:
        raise ValueError("TIMEZONE_AWARE_CUTOFF_REQUIRED")
    unique = {}
    for raw in envelopes:
        item = copy.deepcopy(dict(raw))
        identity = item.pop("observation_identity", None)
        if item.get("contract_version") != VERSION or identity != VERSION + ":" + _identity(item):
            raise ValueError("BUSINESS_ENVELOPE_IDENTITY_MISMATCH")
        if item.get("ticker") != ticker:
            continue
        # An envelope built later can never repair earlier knowledge.
        if any(_instant(item["manifest"].get(k)) is None or _instant(item["manifest"].get(k)) > limit
               for k in ("observed_at", "known_at")):
            continue
        publication = _instant(item["manifest"].get("published_at"))
        if publication is not None and publication > limit:
            continue
        item["observation_identity"] = identity
        unique[identity] = item
    items = sorted(unique.values(), key=lambda item: item["observation_identity"])
    suppressed = set()
    for item in items:
        parent = item["manifest"].get("supersedes_document_id")
        if parent and item["research_usable"]:
            prior = [p for p in items if p["manifest"]["document_id"] == parent
                     and p["manifest"].get("source_id") == item["manifest"].get("source_id")
                     and p["issuer_name"] == item["issuer_name"]
                     and _instant(p["manifest"]["known_at"]) < _instant(item["manifest"]["known_at"])]
            # Ambiguous versions of the parent cannot be silently superseded.
            if prior and len({p["source_sha256"] for p in prior}) == 1:
                suppressed.update(p["observation_identity"] for p in prior)
    versions = {}
    metric_values = {}
    for item in items:
        versions.setdefault((item["manifest"].get("source_id"), item["manifest"]["document_id"]), set()).add(item["source_sha256"])
        if item["observation_identity"] in suppressed:
            continue
        for fact in item["observations"]:
            if fact["qualification"] != "SOURCE_BOUND_RESEARCH":
                continue
            key = tuple(str(fact.get(k)) for k in ("concept", "metric_kind", "period_label", "period_start", "period_end", "unit", "basis", "accounting_scope"))
            metric_values.setdefault(key, set()).add((str(fact["value"]), fact.get("value_relation", "EXACT")))
    conflicts = ["DOCUMENT_ID_HAS_DIFFERENT_HASHES"] if any(len(v) > 1 for v in versions.values()) else []
    if any(len(v) > 1 for v in metric_values.values()):
        conflicts.append("CONTRADICTORY_SOURCE_FACTS")
    facts = []
    seen_facts = set()
    for item in items:
        if item["observation_identity"] in suppressed:
            continue
        for fact in item["observations"]:
            if fact["qualification"] == "SOURCE_BOUND_RESEARCH":
                capture_key = (item["manifest"].get("source_id"), item["manifest"]["document_id"],
                               item["source_sha256"], fact["fact_identity"])
                if capture_key in seen_facts:
                    continue
                seen_facts.add(capture_key)
                facts.append({**fact, "document_identity": item["observation_identity"],
                              "document_class": item["document_class"], "source_url": item["manifest"]["source_url"],
                              "published_at": item["manifest"]["published_at"], "known_at": item["manifest"]["known_at"],
                              "coverage_kind": item["coverage_kind"]})
    # Whole-context conflict is conservative; never pick a preferred announcement.
    return dict(contract_version=VERSION, ticker=ticker, cutoff=cutoff, event_type="EARNINGS_BUSINESS_UPDATE",
                FACT=facts, CONTEXT=[f["comparison"] for f in facts if f.get("comparison")],
                UNCERTAINTY=sorted(set(conflicts + [b for i in items for b in i["blockers"]])),
                THESIS_IMPLICATION="Operating/earnings observations are research questions about demand, mix and conversion; no causal conclusion.",
                COUNTER_THESIS="Volume can rise while prices, mix, margins or cash conversion deteriorate. Guidance is not actual performance.",
                DECISION_USE="NON_VOTING_RESEARCH_CONTEXT_ONLY", research_usable=bool(facts) and not conflicts,
                conflicts=conflicts, documents=items, superseded_identities=sorted(suppressed),
                authority_effect="NONE", is_actionable=False, financial_fact_authority=False,
                posture_effect="NONE", valuation_effect="NONE")
