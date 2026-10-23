"""Prior-period pairing for admitted official income facts (non-voting research).

Milestone ``QUALIFIED_QUARTERLY_STATEMENT_THROUGHPUT_V1``.  The exact-field stream
(``official_income_research_context``) admits current reviewed/audited income facts but
only searches that same stream for a prior year, so an FY2025 audited fact never meets the
independently qualified FY2024 audited fact it should be compared with.  This module is the
missing read link, not a new fact authority:

* current side: only facts already admitted by ``official_income_research_context``;
* prior side: only rows already qualified by an existing official owner (the governed
  official-evidence identity citations and the P3-E promoted closeout citations), each
  re-checked here for document hash, assurance, scope, currency/unit, literal row identity,
  semantic corrections and knowledge time;
* a comparative column of the *later* report is supporting evidence only.  It can confirm an
  original (``COMPARATIVE_COLUMN_MATCHES_ORIGINAL``) or refuse a pair when it disagrees; it
  never becomes a prior-period fact unless the Owner gate below is explicitly enabled.

Nothing here votes, annualizes, subtracts quarters, builds TTM, converts currency, repairs OCR
or changes valuation eligibility.  Owner gates are disabled unless a caller names them.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CONTRACT_VERSION = "official_income_prior_period_pairing/v1"
COMPARATIVE_CONTRACT = "comparative_column_observation/v1"
COMPARATIVE_PUBLIC_FILE = "comparative_column_observations.jsonl"
COMPARATIVE_GATE = "OWNER_GATE_COMPARATIVE_COLUMN_AS_PRIOR_PERIOD_FACT"
UNREVIEWED_GATE = "OWNER_GATE_D1_UNREVIEWED_QUARTERLY_DIRECTION_PREVIEW"
OWNER_GATES = (COMPARATIVE_GATE, UNREVIEWED_GATE)
METHOD = "same_identity_scope_currency_duration_prior_year_cross_document/v1"
INCOME_METRICS = ("revenue", "net_income", "attributable_net_income")
# Line identities reuse the existing literal row contract (financial_row_identity).
LINE_IDENTITY = {"revenue": ("10", "NET_REVENUE"), "net_income": ("60", "TOTAL_PROFIT_AFTER_TAX"),
                 "attributable_net_income": ("61", "PARENT_PROFIT_AFTER_TAX")}
GOVERNED_METRIC_ALIASES = {"parent_attributable_net_income": "attributable_net_income"}
APPROVED_DOCUMENT_CLASSES = {"audited": {"audited_annual_financial_statements"},
                             "reviewed": {"reviewed_interim_financial_statements"}}


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def _instant(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def literal_row_identity(metric: str, label: str | None) -> str | None:
    """Accounting identity proven by the printed label alone; no line code is invented."""
    from stocklookup_core.evidence.financial_row_identity import resolve_reported_row_identity
    if metric not in LINE_IDENTITY or not label:
        return None
    code, concept = LINE_IDENTITY[metric]
    resolved = resolve_reported_row_identity("income_statement", code, label)
    if resolved["canonical_metric"] != metric or resolved["accounting_identity"] != concept or resolved["blockers"]:
        return None
    return concept


def current_row_identity(row: Mapping[str, Any]) -> str | None:
    code, concept = LINE_IDENTITY.get(str(row.get("canonical_metric")), (None, None))
    return concept if code is not None and str(row.get("line_code")) == code else None


def _annual_bounds(period: str) -> tuple[str, str] | None:
    return (f"{period}-01-01", f"{period}-12-31") if re.fullmatch(r"20[0-3]\d", str(period)) else None


def _prior_year(start: str, end: str) -> tuple[str, str] | None:
    try:
        old_start, old_end = date.fromisoformat(start), date.fromisoformat(end)
        return (old_start.replace(year=old_start.year - 1).isoformat(), old_end.replace(year=old_end.year - 1).isoformat())
    except (ValueError, TypeError):
        return None


def _semantic_corrections(rows: Iterable[Mapping[str, Any]]) -> tuple[set[str], set[tuple]]:
    citations, keys = set(), set()
    for row in rows:
        superseded = row.get("supersedes_fact_identity") or {}
        if superseded.get("citation_id"):
            citations.add(str(superseded["citation_id"]))
        keys.add((str(row.get("ticker") or "").upper(), str(row.get("old_metric") or superseded.get("metric")),
                  str(row.get("reporting_period")), row.get("old_value")))
    return citations, keys


def prior_rows_from_governed_citations(citations: Iterable[Mapping[str, Any]], manifest_records: Iterable[Mapping[str, Any]],
                                       corrections: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Governed official-evidence identity citations joined to their document manifest."""
    manifest = {str(row.get("evidence_id")): row for row in manifest_records if row.get("evidence_id")}
    wrong_citations, wrong_keys = _semantic_corrections(corrections)
    rows = []
    for citation in citations:
        metric = GOVERNED_METRIC_ALIASES.get(str(citation.get("metric")), str(citation.get("metric")))
        if metric not in INCOME_METRICS:
            continue
        document = manifest.get(str(citation.get("evidence_id"))) or {}
        extraction = citation.get("extraction") or {}
        labels = [str(label) for label in extraction.get("raw_labels") or []]
        ticker, period = str(citation.get("ticker") or "").upper(), str(citation.get("reporting_period") or "")
        corrected = (str(citation.get("citation_id")) in wrong_citations
                     or (ticker, str(citation.get("metric")), period, citation.get("value")) in wrong_keys)
        rows.append(_prior_row(
            ticker=ticker, metric=metric, period=period, frequency=citation.get("reporting_frequency"),
            value=citation.get("value"), currency=citation.get("currency"), unit_scale=citation.get("unit_scale"),
            scope=citation.get("statement_scope"), citation_id=citation.get("citation_id"),
            document_sha256=document.get("sha256"), document_class=document.get("document_class"),
            assurance=document.get("audit_status"), document_qualified=document.get("qualification_state") == "qualified",
            label=labels[0] if len(labels) == 1 else None, label_count=len(labels),
            published_at=document.get("published_at"), knowledge_available_at=citation.get("verified_at"),
            source_owner="governed_official_evidence_identity_citation", source_locator=document.get("source_url"),
            source_page=(extraction.get("source_pages") or [None])[0], semantic_correction_present=corrected))
    return rows


def prior_rows_from_promoted_closeout(citations: Iterable[Mapping[str, Any]],
                                      evidence_documents: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """P3-E closeout citations; the printed source fragment comes from the same manifest."""
    fragments = {}
    for document in evidence_documents:
        for metric, source in (document.get("source_page_citations") or {}).items():
            fragments[(str(document.get("ticker")).upper(), metric, str(document.get("reporting_period")),
                       str(document.get("document_sha256")))] = (source.get("source_fragment"), document.get("source_document_class"))
    rows = []
    for citation in citations:
        metric = str(citation.get("metric"))
        if metric not in INCOME_METRICS:
            continue
        ticker, period = str(citation.get("ticker") or "").upper(), str(citation.get("reporting_period") or "")
        label, document_class = fragments.get((ticker, metric, period, str(citation.get("document_sha256"))), (None, None))
        rows.append(_prior_row(
            ticker=ticker, metric=metric, period=period, frequency="annual" if _annual_bounds(period) else None,
            value=citation.get("value"), currency=citation.get("currency"), unit_scale=citation.get("unit_scale"),
            scope=citation.get("statement_scope"), citation_id=citation.get("citation_id"),
            document_sha256=citation.get("document_sha256"), document_class=document_class,
            assurance=citation.get("audit_status"), document_qualified=citation.get("qualification_state") == "QUALIFIED",
            label=label, label_count=1 if label else 0, published_at=citation.get("published_at"),
            knowledge_available_at=citation.get("verified_at"), source_owner="p3e_promoted_fundamental_coverage_closeout",
            source_locator=citation.get("source_locator"), source_page=citation.get("source_page"),
            semantic_correction_present=False))
    return rows


def _prior_row(*, ticker, metric, period, frequency, value, currency, unit_scale, scope, citation_id, document_sha256,
               document_class, assurance, document_qualified, label, label_count, published_at, knowledge_available_at,
               source_owner, source_locator, source_page, semantic_correction_present) -> dict[str, Any]:
    reasons = []
    bounds = _annual_bounds(period) if frequency == "annual" else None
    if bounds is None:
        reasons.append("EXPLICIT_ANNUAL_PERIOD_REQUIRED")
    if not document_qualified or not re.fullmatch(r"[0-9a-f]{64}", str(document_sha256 or "")) or not citation_id:
        reasons.append("QUALIFIED_SOURCE_DOCUMENT_IDENTITY_REQUIRED")
    if assurance not in APPROVED_DOCUMENT_CLASSES or document_class not in APPROVED_DOCUMENT_CLASSES.get(assurance, ()):
        reasons.append("APPROVED_AUDITED_OR_REVIEWED_STATEMENT_DOCUMENT_REQUIRED")
    if scope not in {"consolidated", "standalone"}:
        reasons.append("EXPLICIT_STATEMENT_SCOPE_REQUIRED")
    if (type(value) is not int or type(unit_scale) is not int or unit_scale != 1 or not currency):
        reasons.append("NORMALIZED_SOURCE_UNIT_REQUIRED")
    identity = literal_row_identity(metric, label) if label_count == 1 else None
    if identity is None:
        reasons.append("PRIOR_ROW_LITERAL_IDENTITY_NOT_PROVEN")
    if semantic_correction_present:
        reasons.append("HISTORICAL_SEMANTIC_CORRECTION_SUPERSEDES_ROW")
    if _instant(knowledge_available_at) is None:
        reasons.append("EXPLICIT_KNOWLEDGE_TIME_REQUIRED")
    row = {"contract_version": CONTRACT_VERSION, "ticker": ticker, "canonical_metric": metric, "reporting_period": period,
           "period_type": "annual" if bounds else frequency, "period_start": bounds[0] if bounds else None,
           "period_end": bounds[1] if bounds else None,
           "period_bounds_basis": "ANNUAL_LABEL_CALENDAR_YEAR_FISCAL_CALENDAR_NOT_PROVEN_BY_LABEL" if bounds else None,
           "normalized_value": value, "currency": currency, "unit_scale": unit_scale, "statement_scope": scope,
           "statement_family": "income_statement", "accounting_identity": identity, "printed_label": label,
           "line_code_observed": None, "audit_or_review_status": assurance, "document_class": document_class,
           "document_sha256": document_sha256, "citation_id": citation_id, "source_owner": source_owner,
           "source_locator": source_locator, "source_page": source_page, "publication_date": published_at,
           "knowledge_available_at": knowledge_available_at,
           "availability_basis": "VERIFICATION_TIME_NOT_PUBLICATION_OR_HISTORICAL_PIT_PROOF",
           "admission_state": "QUALIFIED_PRIOR_PERIOD_FACT" if not reasons else "BLOCKED", "reason_codes": sorted(set(reasons))}
    return row


def load_prior_official_income_rows(*, runtime_root: Path | str | None, repo_root: Path | str) -> dict[str, Any]:
    """Read the two existing qualified owners; a missing or unreadable owner is a blocker, never a guess."""
    repo_root = Path(repo_root)
    rows, blockers = [], []
    corrections: list[dict[str, Any]] = []
    correction_path = repo_root / "derived" / "financial-evidence-currency-refresh-v1" / "semantic_metric_relabel_corrections.jsonl"
    if correction_path.is_file():
        corrections = [json.loads(line) for line in correction_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    evidence = Path(runtime_root) / "data" / "official-evidence" if runtime_root else None
    if evidence is None or not (evidence / "financial_identity_citations.jsonl").is_file() or not (evidence / "manifest.json").is_file():
        blockers.append("GOVERNED_OFFICIAL_EVIDENCE_NOT_RETAINED_ON_HOST")
    else:
        try:
            citations = [json.loads(line) for line in (evidence / "financial_identity_citations.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8")).get("records") or []
            rows.extend(prior_rows_from_governed_citations(citations, manifest, corrections))
        except (OSError, ValueError, AttributeError):
            blockers.append("GOVERNED_OFFICIAL_EVIDENCE_UNREADABLE")
    try:
        from stocklookup_core.financial.multi_period_financial_panel import load_promoted_fundamental_coverage_closeout_citations
        manifest_path = repo_root / "config" / "promoted_fundamental_coverage_closeout_evidence.json"
        documents = json.loads(manifest_path.read_text(encoding="utf-8")).get("evidence_documents") or [] if manifest_path.is_file() else []
        rows.extend(prior_rows_from_promoted_closeout(load_promoted_fundamental_coverage_closeout_citations(repo_root), documents))
    except Exception:  # an owner refusal must not become a Daily failure or an admitted value
        blockers.append("P3E_PROMOTED_CLOSEOUT_UNREADABLE")
    rows.sort(key=lambda row: (row["ticker"], row["canonical_metric"], row["reporting_period"], str(row["citation_id"])))
    return {"rows": rows, "load_blockers": sorted(set(blockers))}


def load_prior_period_inputs(*, runtime_root: Path | str | None, repo_root: Path | str,
                             public_root: Path | str) -> dict[str, Any]:
    """Daily-safe bundle: unreadable inputs become blockers, never values or a run failure."""
    loaded = load_prior_official_income_rows(runtime_root=runtime_root, repo_root=repo_root)
    try:
        observations = load_comparative_column_observations(public_root)
    except (OSError, ValueError):
        observations = []
        loaded["load_blockers"] = sorted(set(loaded["load_blockers"]) | {"COMPARATIVE_COLUMN_OBSERVATIONS_UNREADABLE"})
    return {"contract_version": CONTRACT_VERSION, "rows": loaded["rows"], "load_blockers": loaded["load_blockers"],
            "comparative_observations": observations}


def validate_comparative_observation(row: Mapping[str, Any]) -> list[str]:
    """Structural check of one retained comparative-column observation (candidate evidence)."""
    reasons = []
    if row.get("contract_version") != COMPARATIVE_CONTRACT:
        reasons.append("COMPARATIVE_CONTRACT_VERSION_INVALID")
    if (row.get("admission_state") == "QUALIFIED" or row.get("existing_consumer_usable") is not False
            or row.get("official_fact_admitted") is not False):
        reasons.append("COMPARATIVE_OBSERVATION_AUTHORITY_INVALID")
    if row.get("canonical_metric") not in INCOME_METRICS or current_row_identity(row) != row.get("accounting_identity"):
        reasons.append("COMPARATIVE_ROW_IDENTITY_INVALID")
    value = row.get("value")
    if value is not None and (type(value) is not int or row.get("raw_token") is None):
        reasons.append("COMPARATIVE_VALUE_BINDING_INVALID")
    if row.get("observation_id") != _hash({k: row.get(k) for k in (
            "ticker", "canonical_metric", "reporting_period", "source_document_sha256", "source_page", "raw_token")}):
        reasons.append("COMPARATIVE_OBSERVATION_ID_INVALID")
    return reasons


def load_comparative_column_observations(public_root: Path | str) -> list[dict[str, Any]]:
    path = Path(public_root) / COMPARATIVE_PUBLIC_FILE
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        if validate_comparative_observation(row):
            raise ValueError("COMPARATIVE_COLUMN_OBSERVATION_INVALID:" + str(row.get("observation_id")))
    return rows


def _comparison(prior: Mapping[str, Any], current: Mapping[str, Any], *, entity: Any, prior_basis: str,
                restatement_check: str) -> dict[str, Any]:
    from stocklookup_core.financial.financial_analysis_engine_v2 import sign_transition
    old, new = prior["normalized_value"], current["normalized_value"]
    delta = new - old
    return {"metric": current["canonical_metric"], "accounting_identity": current_row_identity(current),
            "statement_scope": current["statement_scope"], "period_type": current["period_type"],
            "currency": current["currency"], "entity_class": entity,
            "prior_period": prior["reporting_period"], "current_period": current["reporting_period"],
            "prior_value": old, "current_value": new, "change": delta,
            "direction": "INCREASED" if delta > 0 else "DECREASED" if delta < 0 else "UNCHANGED",
            "growth_ratio": delta / old if old > 0 else None,
            "semantic_transition": sign_transition(old, new, earnings=current["canonical_metric"] != "revenue"),
            "prior_basis": prior_basis, "restatement_check": restatement_check,
            "prior_citation_id": prior.get("citation_id") or prior.get("observation_id"),
            "prior_document_sha256": prior.get("document_sha256") or prior.get("source_document_sha256"),
            "prior_source_owner": prior.get("source_owner") or COMPARATIVE_CONTRACT,
            "prior_assurance": prior.get("audit_or_review_status") or prior.get("assurance_basis"),
            "current_citation_id": current["citation_id"], "current_document_sha256": current["document_sha256"],
            "current_assurance": current["audit_or_review_status"], "method": METHOD,
            "limitations": ["REPORTED_CHANGE_NOT_BUSINESS_QUALITY", "RECURRENCE_UNKNOWN", "NON_VOTING",
                            "NO_ANNUALIZATION_NO_TTM_NO_FX"]}


def official_income_prior_period_context(record: Mapping[str, Any] | None, *, prior_rows: Sequence[Mapping[str, Any]],
                                         comparative_observations: Sequence[Mapping[str, Any]] = (),
                                         unreviewed_rows: Sequence[Mapping[str, Any]] = (), cutoff: str | None,
                                         ticker: str | None, enabled_owner_gates: Iterable[str] = (),
                                         load_blockers: Sequence[str] = ()) -> dict[str, Any]:
    record = record or {}
    gates = set(enabled_owner_gates)
    if gates - set(OWNER_GATES):
        raise ValueError("UNKNOWN_OWNER_GATE")
    boundary = _instant(cutoff)
    entity = record.get("entity_class")
    income = record.get("official_income_research_context") or {}
    current_facts = [fact for fact in income.get("facts") or []
                     if fact.get("ticker") == ticker and fact.get("canonical_metric") in INCOME_METRICS]
    rejected, comparisons, preview = [], [], []

    def known(row: Mapping[str, Any]) -> bool:
        instant = _instant(row.get("knowledge_available_at"))
        return boundary is not None and instant is not None and instant <= boundary

    eligible_prior = []
    for row in prior_rows:
        if row.get("ticker") != ticker:
            continue
        reasons = list(row.get("reason_codes") or [])
        if entity != "corporate":
            reasons.append("INDUSTRIAL_INCOME_IDENTITY_NOT_ADMITTED_FOR_ENTITY")
        if not known(row):
            reasons.append("PRIOR_FACT_NOT_KNOWN_AT_CUTOFF")
        if row.get("period_end") and boundary is not None and date.fromisoformat(row["period_end"]) > boundary.date():
            reasons.append("PRIOR_PERIOD_END_AFTER_CUTOFF")
        if reasons:
            rejected.append({"side": "PRIOR", "citation_id": row.get("citation_id"), "metric": row.get("canonical_metric"),
                             "reporting_period": row.get("reporting_period"), "reason_codes": sorted(set(reasons))})
        else:
            eligible_prior.append(row)
    observations = [row for row in comparative_observations if row.get("ticker") == ticker and known(row)]
    for current in sorted(current_facts, key=lambda row: (row["canonical_metric"], row["period_end"], row["citation_id"])):
        identity = current_row_identity(current)
        prior_bounds = _prior_year(current.get("period_start"), current.get("period_end"))
        if identity is None or prior_bounds is None:
            rejected.append({"side": "CURRENT", "citation_id": current.get("citation_id"),
                             "reason_codes": ["CURRENT_LINE_IDENTITY_OR_BOUNDS_NOT_EXPLICIT"]})
            continue
        matches = [row for row in eligible_prior
                   if row["accounting_identity"] == identity and row["statement_scope"] == current["statement_scope"]
                   and row["currency"] == current["currency"] and row["unit_scale"] == current["unit_scale"]
                   and row["period_type"] == current["period_type"]
                   and (row["period_start"], row["period_end"]) == prior_bounds
                   and row["audit_or_review_status"] == current["audit_or_review_status"]
                   and row["document_sha256"] != current["document_sha256"]]
        near = [row for row in eligible_prior if row["canonical_metric"] == current["canonical_metric"]
                and row["reporting_period"] == str(int(current["reporting_period"][:4]) - 1) + current["reporting_period"][4:]]
        same_doc = [row for row in observations if row.get("source_document_sha256") == current["document_sha256"]
                    and row.get("canonical_metric") == current["canonical_metric"]
                    and (row.get("period_start"), row.get("period_end")) == prior_bounds]
        if not matches:
            reasons = ["NO_INDEPENDENTLY_QUALIFIED_PRIOR_PERIOD_FACT"]
            for row in near:
                if row["currency"] != current["currency"]:
                    reasons.append("PRIOR_CURRENCY_DIFFERS_NO_FX")
                if row["statement_scope"] != current["statement_scope"]:
                    reasons.append("PRIOR_STATEMENT_SCOPE_DIFFERS")
                if row["audit_or_review_status"] != current["audit_or_review_status"]:
                    reasons.append("PRIOR_ASSURANCE_TIER_DIFFERS")
                if (row["period_start"], row["period_end"]) != prior_bounds:
                    reasons.append("PRIOR_DURATION_OR_FISCAL_BOUNDS_DIFFER")
            rejected.append({"side": "PAIR", "metric": current["canonical_metric"], "current_period": current["reporting_period"],
                             "current_citation_id": current["citation_id"], "reason_codes": sorted(set(reasons))})
        elif len({row["normalized_value"] for row in matches}) != 1:
            rejected.append({"side": "PAIR", "metric": current["canonical_metric"], "current_period": current["reporting_period"],
                             "reason_codes": ["CONFLICTING_QUALIFIED_PRIOR_PERIOD_VALUES"],
                             "prior_citation_ids": sorted(str(row["citation_id"]) for row in matches)})
        else:
            prior = min(matches, key=lambda row: str(row["citation_id"]))
            check = "COMPARATIVE_CROSS_CHECK_NOT_AVAILABLE"
            if same_doc:
                values = {row.get("value") for row in same_doc}
                if None in values and len(values) == 1:
                    check = "COMPARATIVE_CROSS_CHECK_OCR_AMBIGUOUS"
                elif values - {None} == {prior["normalized_value"]}:
                    check = "COMPARATIVE_COLUMN_MATCHES_ORIGINAL"
                else:
                    check = "PRIOR_PERIOD_DIFFERS_IN_LATER_REPORT"
            if check == "PRIOR_PERIOD_DIFFERS_IN_LATER_REPORT":
                # A later report disagreeing with the original is a restatement question, not a winner choice.
                rejected.append({"side": "PAIR", "metric": current["canonical_metric"], "current_period": current["reporting_period"],
                                 "reason_codes": [check], "prior_citation_id": prior["citation_id"],
                                 "comparative_values": sorted(str(row.get("value")) for row in same_doc)})
            else:
                comparisons.append(_comparison(prior, current, entity=entity, restatement_check=check,
                                               prior_basis="INDEPENDENTLY_QUALIFIED_ORIGINAL_REPORT"))
        if not matches and COMPARATIVE_GATE in gates:
            usable = [row for row in same_doc if row.get("value") is not None and not row.get("blockers")
                      and row.get("currency") == current["currency"] and row.get("statement_scope") == current["statement_scope"]]
            if len(usable) == 1:
                observed = {**usable[0], "normalized_value": usable[0]["value"]}
                preview.append({**_comparison(observed, current, entity=entity, restatement_check="NOT_APPLICABLE_SAME_DOCUMENT",
                                              prior_basis="COMPARATIVE_COLUMN_OF_LATER_REPORT"), "owner_gate": COMPARATIVE_GATE})
    unreviewed_preview = []
    if UNREVIEWED_GATE in gates:
        by_key: dict[tuple, list[Mapping[str, Any]]] = {}
        for row in unreviewed_rows:
            if row.get("ticker") == ticker and row.get("evidence_tier") == "UNREVIEWED_QUARTERLY" and known(row):
                by_key.setdefault((row["canonical_metric"], row["document_sha256"]), []).append(row)
        for (metric, _), rows in sorted(by_key.items()):
            roles = {row.get("column_role"): row for row in rows}
            current, prior = roles.get("CURRENT_QUARTER"), roles.get("PRIOR_YEAR_QUARTER")
            if current and prior and len(rows) == 2:
                old, new = prior["value"], current["value"]
                unreviewed_preview.append({"metric": metric, "prior_period": prior["reporting_period"],
                    "current_period": current["reporting_period"], "prior_value": old, "current_value": new,
                    "change": new - old, "direction": "INCREASED" if new > old else "DECREASED" if new < old else "UNCHANGED",
                    "growth_ratio": (new - old) / old if old > 0 else None, "assurance": "unreviewed",
                    "period_family": "STANDALONE_QUARTER", "owner_gate": UNREVIEWED_GATE, "d1_existing_consumer_usable": False})
    earnings = [row for row in comparisons if row["metric"] in {"net_income", "attributable_net_income"}]
    revenue = [row for row in comparisons if row["metric"] == "revenue"]

    def direction(rows):
        values = {row["direction"] for row in rows}
        return values.pop() if len(values) == 1 else ("CONFLICTING" if values else None)

    standalone = sorted({fact["reporting_period"] for fact in current_facts
                         if fact.get("period_type") == "quarter" and fact.get("audit_or_review_status") in {"reviewed", "audited"}})
    return {
        "contract_version": CONTRACT_VERSION, "ticker": ticker, "cutoff": cutoff, "entity_class": entity,
        "comparisons": comparisons, "direction_status": "MEASURED_REPORTED_CHANGE" if comparisons else "UNKNOWN",
        "earnings_direction_research": direction(earnings), "revenue_direction_research": direction(revenue),
        "blocker_reason_codes": sorted(set(load_blockers) | ({"NO_ADMITTED_CURRENT_OFFICIAL_INCOME_FACT"} if not current_facts else set())
                                       | ({"NO_COMPATIBLE_QUALIFIED_PRIOR_PERIOD_PAIR"} if current_facts and not comparisons else set())),
        "rejected": rejected,
        "ttm_inputs": {"status": "UNAVAILABLE" if len(standalone) < 4 else "REQUIRES_SEPARATE_CONTRACT",
                       "qualified_standalone_quarters": standalone, "required_consecutive_standalone_quarters": 4,
                       "synthetic_q4_or_ytd_subtraction": "NOT_PERMITTED"},
        "owner_gated_preview": {
            "enabled_gates": sorted(gates), "available_gates": list(OWNER_GATES),
            "comparative_candidate_count": len(observations),
            "comparative_column_comparisons": preview if COMPARATIVE_GATE in gates else [],
            "unreviewed_quarterly_comparisons": unreviewed_preview if UNREVIEWED_GATE in gates else [],
            "effect": "NONE_PREVIEW_ONLY_NOT_FED_TO_ANY_CONSUMER"},
        "availability_basis": "KNOWLEDGE_AT_RESEARCH_CUTOFF_NOT_PUBLICATION_OR_HISTORICAL_PIT_PROOF",
        "vote_effect": "NONE", "strict_valuation_effect": "NONE", "ttm_effect": "NONE", "is_actionable": False,
    }


def attach_prior_period_pairing(records: Mapping[str, Any], *, prior_rows: Sequence[Mapping[str, Any]],
                                comparative_observations: Sequence[Mapping[str, Any]] = (), cutoff: str | None,
                                load_blockers: Sequence[str] = ()) -> None:
    """Additive key inside each existing income context; the context's own fields stay untouched."""
    for ticker, record in records.items():
        income = record.get("official_income_research_context")
        if not isinstance(income, dict):
            continue
        income["prior_period_pairing"] = official_income_prior_period_context(
            record, prior_rows=prior_rows, comparative_observations=comparative_observations, cutoff=cutoff,
            ticker=ticker, load_blockers=load_blockers)


__all__ = ["COMPARATIVE_GATE", "UNREVIEWED_GATE", "OWNER_GATES", "attach_prior_period_pairing",
           "literal_row_identity", "load_comparative_column_observations", "load_prior_official_income_rows",
           "load_prior_period_inputs",
           "official_income_prior_period_context", "prior_rows_from_governed_citations",
           "prior_rows_from_promoted_closeout", "validate_comparative_observation"]
