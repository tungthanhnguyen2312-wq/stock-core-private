"""Non-voting projection of source-qualified economic identities; no store or evaluator.

Financial amounts come only through the existing official research gate. Explicit corporate
observations require a qualified source owner's typed semantic receipt. Research candidates
are visible only via the separate offline preview entrypoint, never through default delivery.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Any, Mapping, Sequence

VERSION = "shareholder_economics_context/v1"
STATES = {
    "CONTRACTUAL_OBLIGATION": {"CONTRACTUAL"},
    "PROVISION": {"BOOKED", "MANAGEMENT_ESTIMATE"},
    "PROVISION_CASH_FLOW_ADJUSTMENT": {"REPORTED"},
    "PROFIT": {"REPORTED", "MANAGEMENT_ESTIMATE"},
    "OPERATING_CASH_FLOW": {"REPORTED"},
    "MATURED_UNPAID_DEBT": {"REPORTED"},
    "ISSUANCE": {"APPROVED_PROPOSAL", "REGISTERED_OFFER", "EXECUTED"},
    "SUBSCRIPTION_RIGHTS": {"ENTITLEMENT"},
    "ISSUED_SHARES": {"DATED_OBSERVATION"},
    "TOTAL_SHARES": {"DATED_OBSERVATION"},
    "OUTSTANDING_SHARES": {"DATED_OBSERVATION"},
    "TREASURY_SHARES": {"DATED_OBSERVATION"},
    "VOTING_SHARES": {"DATED_OBSERVATION"},
    "LISTED_SHARES": {"DATED_OBSERVATION"},
    "TRADABLE_SHARES": {"DATED_OBSERVATION"},
    "EPS_WEIGHTED_AVERAGE_SHARES": {"REPORTED"},
    "DILUTED_EPS_SHARES": {"REPORTED"},
    "SHARE_REPURCHASE": {"APPROVED_PROPOSAL", "REGISTERED_OFFER", "EXECUTED"},
    "SHARE_CANCELLATION": {"APPROVED_PROPOSAL", "REGISTERED_OFFER", "EXECUTED"},
    "CHARTER_CAPITAL": {"DATED_OBSERVATION"},
    "FINANCING_PROCEEDS": {"PLANNED", "RECEIVED"},
    "DEBT_REPAYMENT": {"EARMARKED", "REPAID"},
}
SHARE_KINDS = frozenset(k for k in STATES if "SHARES" in k)
SOURCE_OWNERS = frozenset({"corporate_action_events", "official_corporate_action_ledger",
                           "retained_common_share_note", "official_financial_field"})
ACCOUNTING_METRICS = {"PROVISION": "repurchase_commitment_provision",
    "PROVISION_CASH_FLOW_ADJUSTMENT": "provision_charge_or_reversal_adjustment",
    "OPERATING_CASH_FLOW": "operating_cash_flow", "MATURED_UNPAID_DEBT": "matured_unpaid_principal",
    "PROFIT": "net_income"}
ACCOUNTING_FAMILIES = {"PROVISION": "balance_sheet", "MATURED_UNPAID_DEBT": "balance_sheet",
    "PROFIT": "income_statement", "OPERATING_CASH_FLOW": "cash_flow",
    "PROVISION_CASH_FLOW_ADJUSTMENT": "cash_flow"}
FINANCIAL_KINDS = {"operating_cash_flow": "OPERATING_CASH_FLOW",
                   "provision_charge_or_reversal_adjustment": "PROVISION_CASH_FLOW_ADJUSTMENT"}
FORBIDDEN = ["VALUATION_DENOMINATOR", "PRICE_ADJUSTMENT_FACTOR", "EPS_REPLACEMENT", "PIT",
             "POSTURE_OR_RISK_VETO", "TRADING_SIGNAL", "SIZING", "SOURCE_PROMOTION"]
CLAIM_FIELDS = ("ticker", "kind", "state", "subject", "value", "unit", "scope", "consideration",
    "effective_date", "period_start", "period_end", "ex_date", "record_date", "subscription_payment_deadline",
    "source_owner", "qualification_state", "field_qualification", "qualified_semantics", "coverage_kind",
    "document_sha256", "source_identity", "citation_id", "source_locator", "source_page",
    "published_at", "observed_at", "knowledge_available_at", "execution_evidence_qualified",
    "settlement_evidence_qualified", "candidate_execution_document", "candidate_settlement_document",
    "candidate_only", "value_basis", "limitations")
OPTIONAL_SEMANTICS = ("event_id", "share_class", "denominator_basis", "value_basis", "restated",
    "effective_date_type", "ex_date", "record_date", "first_trading_date", "issuance_end_date")
CLAIM_FIELDS += OPTIONAL_SEMANTICS


def _claim(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(row[k]) for k in CLAIM_FIELDS if k in row}


def _identity(value: Mapping[str, Any]) -> str:
    body = {k: v for k, v in value.items() if k != "context_identity"}
    return VERSION + ":" + hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _instant(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.utcoffset() is not None else None
    except ValueError:
        return None


def _day(value: Any) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def _receipt_reasons(row: Mapping[str, Any], ticker: str, boundary: datetime, *, preview: bool) -> list[str]:
    """Require the semantic identity itself to be qualified, not just its document host."""
    reasons = []
    kind, state = row.get("kind"), row.get("state")
    if any(not isinstance(row.get(k), str) for k in ("kind", "state", "unit", "subject", "scope", "source_owner")):
        return ["ECONOMIC_IDENTITY_OR_STATE_UNSUPPORTED"]
    if kind not in STATES or state not in STATES.get(kind, ()):
        reasons.append("ECONOMIC_IDENTITY_OR_STATE_UNSUPPORTED")
    if row.get("ticker") != ticker:
        reasons.append("ISSUER_IDENTITY_MISMATCH")
    if any(row.get(k) is not None and (not isinstance(row[k], str) or not row[k].strip())
           for k in OPTIONAL_SEMANTICS if k != "restated") or (
           row.get("restated") is not None and not isinstance(row["restated"], bool)):
        reasons.append("MALFORMED_OPTIONAL_SHARE_SEMANTICS")
        return reasons
    if (row.get("source_owner") not in SOURCE_OWNERS or row.get("qualification_state") != "QUALIFIED"
            or row.get("field_qualification") != "QUALIFIED") and not preview:
        reasons.append("EXISTING_SOURCE_AND_FIELD_QUALIFICATION_REQUIRED")
    if row.get("coverage_kind") != "REAL_RETAINED_INPUT" and not preview:
        reasons.append("CANDIDATE_OR_FIXTURE_NOT_LIVE_EVIDENCE")
    # A caller's annotation cannot reinterpret a qualified quantity as a different claim.
    semantic = {k: row.get(k) for k in ("kind", "state", "unit", "subject", "value", "scope",
                                       "effective_date", "period_start", "period_end", "consideration")}
    if row.get("qualified_semantics") != semantic and not preview:
        supplied = row.get("qualified_semantics")
        if not isinstance(supplied, Mapping) or any(supplied.get(k) != v for k, v in semantic.items()):
            reasons.append("SOURCE_QUALIFIED_SEMANTIC_RECEIPT_REQUIRED")
    if not preview and any(row.get(k) is not None and (
            not isinstance(row.get("qualified_semantics"), Mapping)
            or row["qualified_semantics"].get(k) != row[k]) for k in OPTIONAL_SEMANTICS):
        reasons.append("SOURCE_QUALIFIED_SEMANTIC_RECEIPT_REQUIRED")
    sha = row.get("document_sha256")
    if (not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)
            or not all(isinstance(row.get(k), str) and row[k].strip()
                       for k in ("source_identity", "citation_id", "source_locator", "subject", "scope"))):
        reasons.append("SOURCE_PROVENANCE_INCOMPLETE")
    times = [_instant(row.get(k)) for k in ("published_at", "observed_at", "knowledge_available_at")]
    required_times = times[1:] if preview and times[0] is None else times
    if any(t is None or t > boundary for t in required_times):
        reasons.append("SOURCE_NOT_KNOWN_AT_CUTOFF")
    elif not times[1] <= times[2] or times[0] is not None and not times[0] <= times[1]:
        reasons.append("SOURCE_CLOCK_ORDER_INVALID")
    value = row.get("value")
    unquantified_contract = kind == "CONTRACTUAL_OBLIGATION" and value is None and row.get("unit") == "NOT_QUANTIFIED"
    if not unquantified_contract and (not _number(value) or not row.get("unit")):
        reasons.append("FINITE_EXPLICIT_VALUE_AND_UNIT_REQUIRED")
    if kind in SHARE_KINDS or kind in {"ISSUANCE", "SUBSCRIPTION_RIGHTS", "SHARE_REPURCHASE", "SHARE_CANCELLATION"}:
        if row.get("unit") != "shares" or not _number(value) or value < 0 or int(value) != value:
            reasons.append("EXPLICIT_SHARE_UNIT_AND_INTEGER_REQUIRED")
    elif not unquantified_contract and row.get("unit") not in {"VND", "million VND", "billion VND", "USD", "million USD"}:
        reasons.append("EXPLICIT_MONETARY_UNIT_REQUIRED")
    if kind in ACCOUNTING_METRICS and state in {"BOOKED", "REPORTED"} and not preview:
        from stocklookup_core.financial.fundamental_signal_consumption_contract import official_research_row_reasons
        fact = row.get("financial_source_record")
        fact = fact if isinstance(fact, Mapping) else {}
        if (row.get("source_owner") != "official_financial_field"
                or fact.get("canonical_metric") != ACCOUNTING_METRICS[kind]
                or fact.get("normalized_value") != value or fact.get("currency") != row.get("unit")
                or fact.get("citation_id") != row.get("citation_id")
                or fact.get("document_sha256") != row.get("document_sha256")
                or fact.get("statement_scope") != row.get("scope")
                or fact.get("period_start") != row.get("period_start")
                or fact.get("period_end") != row.get("period_end")):
            reasons.append("ACCOUNTING_IDENTITY_REQUIRES_EXISTING_FINANCIAL_OWNER")
        reasons += official_research_row_reasons(fact, boundary=boundary, entity=row.get("entity_class"),
            ticker=ticker, statement_family=ACCOUNTING_FAMILIES[kind])
    if state == "EXECUTED" and row.get("execution_evidence_qualified") is not True \
            and not (preview and row.get("candidate_execution_document")):
        reasons.append("ISSUANCE_EXECUTION_NOT_QUALIFIED")
    if state in {"RECEIVED", "REPAID"} and row.get("settlement_evidence_qualified") is not True \
            and not (preview and row.get("candidate_settlement_document")):
        reasons.append("CASH_SETTLEMENT_NOT_QUALIFIED")
    instant = _day(row.get("effective_date"))
    start, end = _day(row.get("period_start")), _day(row.get("period_end"))
    for key in ("effective_date", "period_start", "period_end", "ex_date", "record_date", "subscription_payment_deadline",
                "first_trading_date", "issuance_end_date"):
        if row.get(key) is not None and _day(row[key]) is None:
            reasons.append("MALFORMED_SOURCE_DATE")
    if instant is None and (start is None or end is None or start > end):
        reasons.append("EXPLICIT_EFFECTIVE_DATE_OR_PERIOD_REQUIRED")
    if state == "DATED_OBSERVATION" and instant is None:
        reasons.append("SHARE_OBSERVATION_REQUIRES_EXPLICIT_DATE")
    if kind in {"EPS_WEIGHTED_AVERAGE_SHARES", "DILUTED_EPS_SHARES"} and (start is None or end is None or start > end):
        reasons.append("EPS_WEIGHTED_AVERAGE_REQUIRES_DURATION")
    actual = state in {"BOOKED", "REPORTED", "EXECUTED", "DATED_OBSERVATION", "RECEIVED", "REPAID"}
    if actual and any(d and d > boundary.date() for d in (instant, end)):
        reasons.append("ACTUAL_EFFECT_AFTER_CUTOFF")
    if row.get("conflicts"):
        reasons.append("CONFLICTING_SOURCE_EVIDENCE")
    return reasons


def _explanations(claims: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    messages = {}
    for c in claims:
        kind, state = c["kind"], c["state"]
        if kind == "CONTRACTUAL_OBLIGATION":
            messages["CONTRACT_NOT_SETTLEMENT"] = "A contractual obligation is distinct from its estimate, booked provision and cash settlement."
        if kind == "PROVISION":
            if state == "BOOKED":
                messages["BOOKED_PROVISION"] = "The provision is recognized for its stated period; it is not a new financing inflow."
            else:
                messages["ESTIMATE_NOT_REPORTED_ACTUAL"] = "Management's future obligation estimate is not a reported actual loss or an additional unbooked balance. Overlap with booked provisions is unresolved."
        if kind == "PROVISION_CASH_FLOW_ADJUSTMENT":
            messages["AGGREGATE_PROVISION_CAPTION"] = "The reported cash-flow provision adjustment is an aggregate caption, not a repurchase-only provision or normalized earnings."
        if kind == "PROFIT" and state == "MANAGEMENT_ESTIMATE":
            messages["PROFIT_PLAN_NOT_ACTUAL"] = "Planned profit or loss is not reported actual earnings."
        if kind == "ISSUANCE":
            if state != "EXECUTED":
                messages["PENDING_ISSUANCE_NOT_OUTSTANDING"] = "Approved or registered offering shares are prospective. Existing holders may face ownership dilution after execution; current outstanding shares are unchanged by this explanation."
            elif c.get("consideration") == "NONCASH_CONVERSION":
                messages["NONCASH_CONVERSION_NOT_CASH_RAISE"] = "The executed conversion issues shares without proving new financing cash received at conversion."
            elif c.get("consideration") == "BONUS_FROM_EQUITY":
                messages["BONUS_NOT_NEW_EARNINGS_OR_CASH"] = "Executed bonus shares differ from an unissued placement; they do not create operating earnings or financing cash."
            else:
                messages["ISSUANCE_NOT_CASH_RECEIPT"] = "Executed issuance does not independently prove financing cash received."
        if kind == "SUBSCRIPTION_RIGHTS":
            messages["RIGHTS_NOT_ISSUED_SHARES"] = "Subscription rights and their eligible share base are distinct from paid subscriptions and resulting outstanding shares."
        if kind in SHARE_KINDS:
            messages["SHARE_IDENTITIES_SEPARATE"] = "Issued, treasury, voting/outstanding, listed and tradable shares have separate identities and dates. A bounded observation does not prove later continuity."
        if kind in {"EPS_WEIGHTED_AVERAGE_SHARES", "DILUTED_EPS_SHARES"}:
            messages["EPS_BASIS_SEPARATE"] = "EPS weighted-average shares must not be replaced by period-end or current outstanding shares."
        if kind in {"SHARE_REPURCHASE", "SHARE_CANCELLATION"}:
            messages["REPURCHASE_STAGE_SEPARATE"] = "Approval is not a completed buyback or cancellation; absence of a completion report is not evidence of zero execution."
        if kind == "CHARTER_CAPITAL":
            messages["CAPITAL_NOT_OUTSTANDING"] = "Charter capital is a monetary legal/accounting observation, not an outstanding-share denominator; no division by par value is performed."
        if kind == "FINANCING_PROCEEDS" and state == "PLANNED":
            messages["PLANNED_FUNDS_NOT_RECEIVED"] = "Planned proceeds are contingent financing, not available cash."
        if kind == "DEBT_REPAYMENT" and state == "EARMARKED":
            messages["EARMARKED_NOT_REPAID"] = "Funds earmarked for bond or debt repayment do not prove that debt was repaid."
        if kind == "MATURED_UNPAID_DEBT" or kind == "OPERATING_CASH_FLOW" and c["value"] < 0:
            messages["FINANCING_STRESS_INDEPENDENT_OF_TECHNICAL"] = "A technical breakout or uptrend does not settle financial obligations or repay overdue debt; conditional recovery research remains separate."
    if any(c["kind"] in {"PROVISION", "CONTRACTUAL_OBLIGATION", "MATURED_UNPAID_DEBT", "ISSUANCE"} for c in claims):
        messages["LOW_PB_NOT_EQUITY_VALUE_PROOF"] = "A low research P/B does not establish attractive current equity value while obligations or shareholder claims remain unresolved. No revised BVPS or P/B is computed."
    return [{"code": code, "text": text} for code, text in sorted(messages.items())]


def _share_research(claims: Sequence[Mapping[str, Any]], *, preview: bool) -> dict[str, Any]:
    """Arithmetic over admitted observations, never a share resolver or authority gate.

    A measured endpoint change does not prove what happened between the endpoints.
    The existing share_transition_bridge remains the sole transition/coverage resolver.
    """
    points = [copy.deepcopy(c) for c in claims if c["kind"] in SHARE_KINDS or c["kind"] == "CHARTER_CAPITAL"]
    events = [copy.deepcopy(c) for c in claims if c["kind"] in {"ISSUANCE", "SHARE_REPURCHASE", "SHARE_CANCELLATION", "SUBSCRIPTION_RIGHTS"}]
    changes, stage_variances = [], []
    groups: dict[tuple, list] = {}
    for c in points:
        # Weighted duration/restatement and unknown class/basis cannot be chained.
        if c["state"] != "DATED_OBSERVATION" or c["kind"] == "CHARTER_CAPITAL" \
                or not all(c.get(k) for k in ("effective_date", "share_class", "denominator_basis")):
            continue
        key = tuple(c.get(k) for k in ("kind", "subject", "scope", "unit", "share_class", "denominator_basis", "value_basis", "restated"))
        groups.setdefault(key, []).append(c)
    for key, rows in sorted(groups.items(), key=lambda kv: str(kv[0])):
        by_day: dict[str, list] = {}
        for c in rows:
            by_day.setdefault(c["effective_date"], []).append(c)
        days = sorted(by_day)
        for prior_day, current_day in zip(days, days[1:]):
            prior, current = by_day[prior_day], by_day[current_day]
            if len({p["value"] for p in prior}) != 1 or len({p["value"] for p in current}) != 1:
                continue
            before, after = prior[0]["value"], current[0]["value"]
            changes.append(dict(kind=key[0], scope=key[2], share_class=key[4], denominator_basis=key[5],
                prior_date=prior_day, current_date=current_day, prior_value=before, current_value=after,
                change=after-before, change_ratio=(after-before)/before if before else None,
                evidence_citations=sorted({p["citation_id"] for p in prior+current}),
                classification="CANDIDATE_ARITHMETIC" if preview else "ARITHMETIC_INFERENCE_FROM_QUALIFIED_POINTS",
                continuity_status="UNKNOWN_BETWEEN_OBSERVATIONS", ownership_dilution="UNKNOWN",
                interpretation="Endpoint count change is not a continuous share history or proof of cash raised, wealth dilution, or unchanged ownership."))
    event_groups: dict[tuple, list] = {}
    for c in events:
        if c.get("event_id") and c.get("share_class") and c.get("denominator_basis"):
            event_groups.setdefault(tuple(c.get(k) for k in ("event_id", "kind", "scope", "unit", "share_class", "denominator_basis")), []).append(c)
    for key, rows in sorted(event_groups.items()):
        planned = [r for r in rows if r["state"] in {"APPROVED_PROPOSAL", "REGISTERED_OFFER"}]
        executed = [r for r in rows if r["state"] == "EXECUTED"]
        if len({p["value"] for p in planned}) == 1 and len({p["value"] for p in executed}) == 1:
            stage_variances.append(dict(event_id=key[0], planned=planned[0]["value"], executed=executed[0]["value"],
                executed_minus_planned=executed[0]["value"]-planned[0]["value"],
                evidence_citations=sorted({r["citation_id"] for r in planned+executed}),
                classification="CANDIDATE_ARITHMETIC" if preview else "ARITHMETIC_INFERENCE_FROM_QUALIFIED_EVENT_STAGES"))
    return dict(share_observations=points, event_lifecycles=events, endpoint_changes=changes,
        planned_executed_variances=stage_variances,
        denominator_risks=[dict(code="SHARE_DEFINITION_SCOPE_AND_DATE_MUST_MATCH",
            text="Issued, outstanding, treasury, listed, tradeable, weighted EPS and diluted EPS are separate bases. Parent legal shares and consolidated treasury treatment may both be valid without being interchangeable."),
            dict(code="STRICT_PER_SHARE_COMPARISON_BLOCKED",
            text="A dated count or bonus-restated EPS cannot supply a current valuation denominator. Missing ex-date, executed lifecycle or coverage leaves price/share continuity UNKNOWN.")],
        strict_per_share_use="BLOCKED_RESEARCH_ONLY", continuity_authority="UNCHANGED_EXISTING_SHARE_OWNER")


def _finish(ticker: str, cutoff: str, claims: list[dict], rejected: list[dict], *, preview: bool = False,
            share_basis: Mapping[str, Any] | None = None) -> dict[str, Any]:
    unique = {json.dumps(c, sort_keys=True, ensure_ascii=False): c for c in claims}
    claims = [unique[k] for k in sorted(unique)]
    groups = {}
    for c in claims:
        key = (c["kind"], c["state"], c["subject"], c.get("effective_date"), c.get("period_start"),
               c.get("period_end"), c["unit"], c["scope"], c.get("event_id"), c.get("share_class"), c.get("denominator_basis"))
        groups.setdefault(key, []).append(c)
    conflicts = {id(c) for rows in groups.values()
                 if len({(c["value"], c.get("consideration")) for c in rows}) > 1 for c in rows}
    if conflicts:
        rejected += [{"citation_id": c["citation_id"], "reason_codes": ["CONFLICTING_ECONOMIC_VALUES"]}
                     for c in claims if id(c) in conflicts]
        claims = [c for c in claims if id(c) not in conflicts]
    rejected = [json.loads(k) for k in sorted({json.dumps(r, sort_keys=True) for r in rejected})]
    basis = copy.deepcopy(dict(share_basis or {}))
    # This is the existing Producer share verdict, never an outstanding-share assertion.
    basis_view = {k: basis.get(k) for k in ("status", "share_concept", "authority", "observation_date", "blocked_reasons")}
    if basis:
        basis_view["interpretation"] = "EXISTING_SHARE_VERDICT_ONLY_NOT_NEW_CURRENT_OUTSTANDING_AUTHORITY"
    result = dict(contract_version=VERSION, ticker=ticker, cutoff=cutoff,
        status="OFFLINE_PREVIEW" if preview else "AVAILABLE" if claims else "UNKNOWN",
        coverage_kind="OFFLINE_FIXTURE" if preview else "REAL_RETAINED_INPUT",
        claims=claims, rejected=rejected, share_basis_context=basis_view if basis else None,
        unavailable_dimensions=[kind for kind in STATES if not any(c["kind"] == kind for c in claims)],
        explanations=_explanations(claims), vote_effect="NONE", authority_effect="NONE", is_actionable=False,
        prohibited_uses=FORBIDDEN, current_outstanding_shares=None, prospective_outstanding_shares=None,
        price_adjustment_factor=None, historical_pit_eligible=False,
        share_capital_research=_share_research(claims, preview=preview),
        limitations=["CLAIM_LOCAL_QUALIFICATION_NOT_GLOBAL_ISSUER_VERDICT", "NO_VALUATION_OR_FACTOR_AUTHORITY",
                     "SOURCE_DATES_AND_KNOWLEDGE_TIMES_REMAIN_DISTINCT", "TECHNICAL_AND_POSTURE_UNCHANGED"])
    result["context_identity"] = _identity(result)
    return result


def project_context(*, ticker: str, cutoff: str, observations: Sequence[Mapping[str, Any]] = (),
                    financial_record: Mapping[str, Any] | None = None,
                    share_basis: Mapping[str, Any] | None = None,
                    inherited_context: Mapping[str, Any] | None = None,
                    retained_common_share_notes: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Explicit input projection only; never discovers candidate documents or changes a gate."""
    boundary = _instant(cutoff)
    if boundary is None:
        return _finish(ticker, cutoff, [], [{"citation_id": None,
            "reason_codes": ["TIMEZONE_AWARE_CUTOFF_REQUIRED"]}])
    claims, rejected = [], []
    if inherited_context is not None:
        inherited = at_cutoff(inherited_context, ticker=ticker, cutoff=cutoff)
        if inherited is not None:
            claims.extend(inherited["claims"])
            rejected.extend(inherited["rejected"])
            if share_basis is None:
                share_basis = inherited.get("share_basis_context")
    for raw in observations:
        if not isinstance(raw, Mapping):
            rejected.append({"citation_id": None, "reason_codes": ["MALFORMED_ECONOMIC_OBSERVATION"]})
            continue
        row = copy.deepcopy(dict(raw))
        reasons = _receipt_reasons(row, ticker, boundary, preview=False)
        if reasons:
            rejected.append({"citation_id": row.get("citation_id"), "reason_codes": sorted(set(reasons))})
        else:
            claims.append(_claim(row))
    for note in retained_common_share_notes:
        try:
            if note.get('contract_version') == 'retained_share_capital_note/v1':
                from stocklookup_core.evidence.current_common_shares_official_evidence_acquisition import qualify_retained_share_capital_note
                verified = qualify_retained_share_capital_note(**{k: note[k] for k in
                    ('document', 'materialization', 'assurance', 'knowledge_available_at')})
                if verified != note or note['ticker'] != ticker:
                    raise ValueError('RETAINED_NOTE_RECEIPT_MISMATCH')
                admitted = copy.deepcopy(note['claims'])
                for row in admitted:
                    if any(_instant(row.get(k)) is None or _instant(row[k]) > boundary
                           for k in ('observed_at', 'knowledge_available_at')) or _day(row['effective_date']) > boundary.date():
                        raise ValueError('SOURCE_NOT_KNOWN_AT_CUTOFF')
                    if row.get('published_at') is not None and _instant(row['published_at']) > boundary:
                        raise ValueError('SOURCE_NOT_KNOWN_AT_CUTOFF')
                claims.extend(admitted)
                continue
            # Reuse the exact existing HPG source-token qualifier. Publication may
            # remain null under THAT contract; this is not a new generic admission.
            from stocklookup_core.evidence.current_common_shares_official_evidence_acquisition import qualify_retained_common_share_note
            citation = note["citation"]
            verified = qualify_retained_common_share_note(
                document=dict(sha256=note["document_sha256"], ticker=note["ticker"],
                    reporting_period=note["effective_date"][:4], observed_at=note["observed_at"],
                    published_at=note.get("published_at"), canonical_url=note["source_url"], document_id=note["evidence_id"]),
                materialization=dict(document_sha256=note["document_sha256"], page_number=citation["pdf_page"],
                    rotation=citation["render_rotation"], rendered_image_sha256=citation["rendered_image_sha256"],
                    tokens=citation["source_tokens"]+citation["date_tokens"]),
                assurance=note["assurance_evidence"], effective_date=note["effective_date"],
                knowledge_available_at=note["knowledge_available_at"])
            if verified != note or note["ticker"] != ticker:
                raise ValueError("RETAINED_NOTE_RECEIPT_MISMATCH")
            if any(_instant(note.get(k)) is None or _instant(note[k]) > boundary
                   for k in ("observed_at", "knowledge_available_at")) or _day(note["effective_date"]) > boundary.date():
                raise ValueError("SOURCE_NOT_KNOWN_AT_CUTOFF")
            claims.append(dict(ticker=ticker, kind="OUTSTANDING_SHARES", state="DATED_OBSERVATION",
                subject=note["identity"], value=note["value"], unit="shares", scope="issuer",
                share_class=note["share_class"], denominator_basis="DATED_LEGAL_COMMON_OUTSTANDING",
                effective_date=note["effective_date"], citation_id=note["citation_id"],
                source_owner="retained_common_share_note", source_identity=note["evidence_id"],
                source_locator=note["source_url"], source_page=citation["pdf_page"],
                document_sha256=note["document_sha256"], published_at=note.get("published_at"),
                observed_at=note["observed_at"], knowledge_available_at=note["knowledge_available_at"],
                qualification_state="QUALIFIED", coverage_kind="REAL_RETAINED_INPUT",
                source_citation=copy.deepcopy(citation), historical_pit_eligible=False,
                limitations=copy.deepcopy(note["limitations"])+["PUBLICATION_UNKNOWN_NO_HISTORICAL_PIT"]))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            rejected.append({"citation_id": note.get("citation_id") if isinstance(note, Mapping) else None,
                "reason_codes": [str(exc) if isinstance(exc, ValueError) else "MALFORMED_RETAINED_SHARE_NOTE"]})
    if financial_record is not None:
        from stocklookup_core.financial.interim_earnings_cash_research import interim_earnings_cash_research_context
        financial = interim_earnings_cash_research_context(financial_record, cutoff=cutoff, ticker=ticker)
        for fact in financial["facts"]:
            kind = FINANCIAL_KINDS.get(fact["canonical_metric"])
            if kind:
                claims.append(dict(kind=kind, state="REPORTED", subject=fact["canonical_metric"],
                    value=fact["normalized_value"], unit=fact["currency"], scope=fact["statement_scope"],
                    period_start=fact["period_start"], period_end=fact["period_end"],
                    effective_date=None, document_sha256=fact["document_sha256"],
                    citation_id=fact["citation_id"], source_identity=fact["source_identity"],
                    knowledge_available_at=fact["knowledge_available_at"],
                    source_owner="EXISTING_OFFICIAL_FINANCIAL_RESEARCH_GATE",
                    qualification_state="QUALIFIED", coverage_kind="REAL_RETAINED_INPUT",
                    availability_basis=financial["availability_basis"], historical_pit_eligible=False))
        rejected += [{"citation_id": r.get("citation_id"), "reason_codes": r["reason_codes"]}
                     for r in financial["rejected"] if r.get("metric") in FINANCIAL_KINDS]
    return _finish(ticker, cutoff, claims, rejected, share_basis=share_basis)


def candidate_discovery_context(*, ticker: str, cutoff: str, report_known_at: str,
        source_manifest: Mapping[str, Any], event_rows: Sequence[Mapping[str, Any]],
        continuity_rows: Sequence[Mapping[str, Any]], gap_rows: Sequence[Mapping[str, Any]] = (),
        original_verifications: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Explicit Hub discovery index; no source/field is qualified by this function.

    CSV FACT/INFERENCE and eligible_uses are report assertions, never gate inputs.
    Even a matched retained PDF leaves the exact new share-field extraction unqualified.
    """
    boundary, known = _instant(cutoff), _instant(report_known_at)
    if boundary is None or known is None:
        raise ValueError("TIMEZONE_AWARE_REPORT_AND_CUTOFF_REQUIRED")
    result = dict(contract_version="shareholder_economics_candidate_discovery/v1", ticker=ticker,
        cutoff=cutoff, report_known_at=report_known_at, coverage_kind="CANDIDATE_DISCOVERY_ONLY",
        is_actionable=False, authority_effect="NONE", qualified_observation_count=0,
        claims=[], status="CANDIDATE_DISCOVERY_AVAILABLE" if known <= boundary else "REPORT_NOT_KNOWN_AT_CUTOFF")
    if known > boundary:
        result.update(sources=[], events=[], continuity_points=[], unresolved_gaps=[],
            blocker_reason_codes=["REPORT_AVAILABLE_AFTER_CUTOFF"], malformed_rows=[])
        result["context_identity"] = _identity(result)
        return result
    malformed = []
    docs = source_manifest.get("documents", []) if isinstance(source_manifest, Mapping) else []
    if not isinstance(docs, list):
        docs = []
        malformed.append("MALFORMED_SOURCE_MANIFEST")
    sources, seen = [], {}
    for doc in docs:
        if not isinstance(doc, Mapping) or not isinstance(doc.get("source_id"), str) or not isinstance(doc.get("issuer"), str):
            malformed.append("MALFORMED_SOURCE_DOCUMENT")
            continue
        if doc["issuer"] != ticker:
            continue
        sid = doc["source_id"]
        original = (original_verifications or {}).get(sid) or {}
        original = original if isinstance(original, Mapping) else {}
        reasons = ["CANDIDATE_EXACT_FIELD_NOT_QUALIFIED"]
        if original.get("status") != "RAW_BYTES_AND_MANIFEST_MATCHED":
            reasons += list(original.get("reason_codes") or ["RETAINED_ORIGINAL_BYTES_NOT_VERIFIED"])
        clocks = doc.get("clocks") if isinstance(doc.get("clocks"), Mapping) else {}
        retrieved = _instant(clocks.get("retrieved_utc"))
        if retrieved is None:
            reasons.append("RETRIEVAL_CLOCK_UNKNOWN")
        elif retrieved > boundary:
            reasons.append("ORIGINAL_RETRIEVED_AFTER_CUTOFF")
        reasons.append("PUBLICATION_AND_HISTORICAL_PIT_NOT_PROVEN")
        if doc.get("host_class") != "FIRST_PARTY_HOST":
            reasons.append("MIRROR_OR_UNVERIFIED_FIRST_PARTY_PROVENANCE")
        if not re.fullmatch(r"[0-9a-f]{64}", str(doc.get("sha256", ""))):
            reasons.append("SOURCE_BYTE_HASH_MISSING_OR_INVALID")
        row = dict(source_id=sid, candidate_source=copy.deepcopy(dict(doc)),
            independently_verified_original=copy.deepcopy(original), blocker_reason_codes=sorted(set(reasons)))
        if sid in seen and seen[sid] != row:
            malformed.append("CONFLICTING_SOURCE_ID:"+sid)
            prior = seen[sid]
            variants = prior.get("candidate_source_variants", [prior["candidate_source"]])+[row["candidate_source"]]
            unique = {json.dumps(v, sort_keys=True, ensure_ascii=False): v for v in variants}
            row["candidate_source_variants"] = [unique[k] for k in sorted(unique)]
            row["candidate_source"] = row["candidate_source_variants"][0]
            row["blocker_reason_codes"] = sorted(set(prior["blocker_reason_codes"]+row["blocker_reason_codes"]+["CONFLICTING_SOURCE_ID"]))
            seen[sid] = row
        else:
            seen[sid] = row
    sources = [seen[k] for k in sorted(seen)]
    def rows(items, id_key):
        selected = {}
        if not isinstance(items, (list, tuple)):
            malformed.append("MALFORMED_CANDIDATE_TABLE")
            return []
        for raw in items:
            if not isinstance(raw, Mapping) or not isinstance(raw.get("issuer"), str):
                malformed.append("MALFORMED_CANDIDATE_ROW")
                continue
            if raw["issuer"] != ticker:
                continue
            if not isinstance(raw.get(id_key), str) or not raw[id_key]:
                malformed.append("MISSING_CANDIDATE_ROW_ID")
                continue
            source_text = raw.get("source_id")
            ids = re.split(r"\s*(?:;| / )\s*", source_text) if isinstance(source_text, str) else []
            blockers = {"CANDIDATE_EXACT_FIELD_NOT_QUALIFIED"}
            for sid in ids:
                blockers.update(seen[sid]["blocker_reason_codes"] if sid in seen else ["UNRESOLVED_EXACT_SOURCE_ID:"+sid])
            if not ids:
                blockers.add("SOURCE_ID_MISSING")
            row = dict(candidate_payload=copy.deepcopy(dict(raw)), source_ids=sorted(ids),
                classification="CANDIDATE_NOT_PRODUCER_QUALIFIED", blocker_reason_codes=sorted(blockers))
            selected[json.dumps(row, sort_keys=True, ensure_ascii=False)] = row
        return [selected[k] for k in sorted(selected)]
    result.update(sources=sources, events=rows(event_rows, "event_id"),
        continuity_points=rows(continuity_rows, "chain_id"), unresolved_gaps=rows(gap_rows, "gap_id"))
    findings = []
    points = [p["candidate_payload"] for p in result["continuity_points"]]
    for eps in points:
        if "eps" not in str(eps.get("share_definition", "")).lower():
            continue
        for legal in points:
            definition = str(legal.get("share_definition", "")).lower()
            left, right = str(legal.get("count", "")), str(eps.get("count", ""))
            if ("eps" not in definition and any(s in definition for s in ("outstanding", "issued", "charter"))
                    and str(eps.get("date", ""))[:10] == str(legal.get("date", ""))[:10]
                    and re.fullmatch(r"\d{2}/\d{2}/\d{4}", str(eps.get("date", ""))[:10])
                    and re.fullmatch(r"[0-9]{1,18}", left) and re.fullmatch(r"[0-9]{1,18}", right)):
                findings.append(dict(code="EPS_AND_LEGAL_BASIS_NOT_INTERCHANGEABLE",
                    classification="CANDIDATE_ARITHMETIC_NOT_QUALIFIED", source_rows=[legal["chain_id"], eps["chain_id"]],
                    reported_legal_basis_count=int(left), reported_eps_basis_count=int(right),
                    eps_minus_legal_count=int(right)-int(left),
                    text="The report's EPS and legal/accounting bases differ at this date. This arithmetic does not prove legal issuance, a current outstanding count, or ownership dilution."))
    if any("consolidated" in str(p).lower() and "parent" in str(p).lower() for p in points):
        findings.append(dict(code="PARENT_AND_CONSOLIDATED_TREASURY_BASES_DISTINCT",
            classification="CANDIDATE_RESEARCH_INTERPRETATION",
            text="Parent legal share ownership and consolidated subsidiary-held treasury treatment may differ. Neither basis substitutes for the other without scope evidence."))
    if any(any(w in str(e["candidate_payload"].get("event", "")).lower() for w in ("buyback", "repurchase"))
           for e in result["events"]):
        findings.append(dict(code="BUYBACK_APPROVAL_AND_NONOBSERVATION_DO_NOT_ESTABLISH_EXECUTION",
            classification="CANDIDATE_RESEARCH_INTERPRETATION",
            text="An approved repurchase and an unchanged reported treasury balance do not prove completion or zero buybacks. Require a separate executed-result original."))
    result["research_findings"] = findings
    result["malformed_rows"] = sorted(set(malformed))
    result["blocker_reason_codes"] = ["CANDIDATE_EXACT_FIELD_NOT_QUALIFIED", "STRICT_SHARE_PRICE_BASIS_UNCHANGED"]
    result["context_identity"] = _identity(result)
    return result


def offline_preview(*, ticker: str, cutoff: str, observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Separate, opt-in demonstration. Never called by live projections or file discovery."""
    boundary = _instant(cutoff)
    if boundary is None:
        raise ValueError("TIMEZONE_AWARE_CUTOFF_REQUIRED")
    claims, rejected = [], []
    for raw in observations:
        if not isinstance(raw, Mapping):
            rejected.append({"citation_id": None, "reason_codes": ["MALFORMED_ECONOMIC_OBSERVATION"]})
            continue
        row = copy.deepcopy(dict(raw))
        reasons = _receipt_reasons(row, ticker, boundary, preview=True)
        if reasons:
            rejected.append({"citation_id": row.get("citation_id"), "reason_codes": sorted(set(reasons))})
        else:
            row.update(coverage_kind="OFFLINE_FIXTURE", qualification_state="CANDIDATE_NOT_PRODUCER_QUALIFIED")
            claims.append(_claim(row))
    return _finish(ticker, cutoff, claims, rejected, preview=True)


def at_cutoff(context: Mapping[str, Any], *, ticker: str, cutoff: str) -> dict[str, Any] | None:
    """No later context, preview or tampered projection can enter a historical consumer."""
    if context.get("contract_version") != VERSION or context.get("context_identity") != _identity(context):
        raise ValueError("SHAREHOLDER_ECONOMICS_IDENTITY_MISMATCH")
    boundary, built = _instant(cutoff), _instant(context.get("cutoff"))
    if (context.get("ticker") != ticker or context.get("coverage_kind") != "REAL_RETAINED_INPUT"
            or boundary is None or built is None or built > boundary):
        return None
    return copy.deepcopy(dict(context))
