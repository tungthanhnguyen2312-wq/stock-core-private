"""MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1: reconciliation engine.

Resolves the UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS cohort (tickers absent from both
`config/ticker_entity_profiles.csv` and `config/promoted_entity_classifications.json`)
by reconciling three already-retained, governed evidence sources -- no new provider, no
PDF/OCR, no ratio- or name-only heuristics:

  1. Statement-template evidence (`statement_taxonomy_sidecar.py`, generated from the
     issuer's own retained balance sheet): the strongest single signal, because it is a
     direct observation of which statutory accounting regime this ticker's own filing
     actually uses -- which is exactly what determines whether Financial V2's ordinary
     corporate ratios apply. `corporate_vas` never grants CORPORATE by itself (same
     "absence of financial markers is not evidence of corporate" principle the sidecar
     already enforces); it only withholds the specialized-financial alternative.
  2. Exchange-provider ICB sector classification (`exchange_industry_classification.py`):
     positive evidence for CORPORATE (16 governed non-financial sectors) or for BANK /
     INSURANCE (their ICB sectors are exclusive licenses); "Dịch vụ tài chính" (Financial
     Services) is informative-only and never resolves a specific class by itself.
  3. Specialized legal-charter evidence (`evidence_backed_entity_classifier.
     evaluate_legal_charter_evidence`), consulted only for its SPECIALIZED outcomes (a
     charter naming "ngan hang" / "chung khoan" / "bao hiem" / "tai chinh" specifically).
     Its general "any joint-stock company" fallback (Case D) is deliberately never
     consulted here: a generic "Công ty Cổ phần ..." prefix is common to non-financial and
     financial issuers alike and is explicitly excluded as sufficient evidence by this
     milestone's brief, even though it remains valid (and untouched) for the 20 tickers
     already promoted under it in config/promoted_entity_classifications.json.

Any two of these sources disagreeing at the entity-class level fails closed as CONFLICT,
never resolved by picking one. A ticker with no positive signal at all -- most commonly
"Dịch vụ tài chính" with no corroborating statement/charter evidence, or a ticker missing
from the ICB sync entirely -- stays UNKNOWN. Reaching for a wider bucket to force those
residual tickers into a positive class would be exactly the "maximize the count" shortcut
this milestone's brief repeatedly prohibits.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, NamedTuple

from entity_classification_contract import (
    CONTRACT_VERSION,
    ClassificationStatus,
    ConfidenceSemantics,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    compute_classification_evidence_id,
)
from evidence_backed_entity_classifier import evaluate_legal_charter_evidence
from exchange_industry_classification import (
    HINT_AMBIGUOUS_FINANCIAL,
    HINT_BANK,
    HINT_CORPORATE,
    HINT_INSURANCE,
)

SOURCE_ID = "market_wide_financial_entity_classification_scaleout/v1"

#: Statement-template values recognized from statement_taxonomy_sidecar.py's
#: `statement_taxonomy` field. Anything else (including "unresolved") is treated as no
#: signal, the same fail-closed default the sidecar itself uses.
_TAX_SECURITIES = "securities_company"
_TAX_CREDIT_INSTITUTION = "credit_institution"
_TAX_AMBIGUOUS_SPECIALIZED = "financial_specialized_ambiguous"
_TAX_CORPORATE = "corporate_vas"

SUPPORTED_SECURITY_TYPES = frozenset({"EQUITY"})

REASON_UNSUPPORTED_SECURITY_TYPE = "UNSUPPORTED_SECURITY_TYPE"
REASON_ENTITY_TYPE_MISSING = "ENTITY_TYPE_MISSING_NO_INDUSTRY_SYNC_RECORD"
REASON_AMBIGUOUS_NO_SUBTYPE = "AMBIGUOUS_FINANCIAL_SECTOR_NO_SPECIALIZED_SUBTYPE_EVIDENCE"
REASON_METADATA_TOO_GENERIC = "METADATA_TOO_GENERIC_UNRECOGNIZED_SECTOR_LABEL"
REASON_UNKNOWN_BY_EVIDENCE = "UNKNOWN_BY_EVIDENCE_NO_POSITIVE_SIGNAL"
REASON_CONFLICT = "ENTITY_CLASSIFICATION_CONFLICT"


class ReconciliationInput(NamedTuple):
    ticker: str
    issuer_identity: str
    legal_name: str | None
    instrument_class: str | None
    icb_industry_hint: str | None      # HINT_CORPORATE / HINT_BANK / HINT_INSURANCE / HINT_AMBIGUOUS_FINANCIAL / None
    icb_industry_label: str | None     # raw retained label, for provenance only
    icb_industry_reason: str | None    # reason string from resolve_industry_hint, for provenance
    statement_taxonomy: str | None     # corporate_vas / credit_institution / securities_company /
                                        # financial_specialized_ambiguous / unresolved / None


class ReconciliationResult(NamedTuple):
    record: EntityClassificationRecord | None   # None when NOT_APPLICABLE (security-type guard)
    outcome: str                                 # entity_class value, "CONFLICT", "NOT_APPLICABLE", or "UNKNOWN"
    reason_code: str
    detail: dict[str, Any]


def _charter_specialized_match(legal_name: str | None) -> EntityClass | None:
    """Only the SPECIALIZED outcomes of the existing charter evaluator; see module docstring."""
    matched_class, _reason, _markers = evaluate_legal_charter_evidence(legal_name)
    if matched_class is not None and matched_class != EntityClass.CORPORATE:
        return matched_class
    return None


def _record(
    inp: ReconciliationInput,
    *,
    entity_class: EntityClass,
    status: ClassificationStatus,
    evidence_tier: EvidenceTier,
    reason: str,
    supporting_evidence: dict[str, Any],
    verified_at: str,
) -> EntityClassificationRecord:
    ev_id = compute_classification_evidence_id(
        issuer_identity=inp.issuer_identity,
        ticker=inp.ticker,
        entity_class=entity_class.value,
        classification_status=status.value,
        source_id=SOURCE_ID,
        evidence_payload=supporting_evidence,
    )
    return EntityClassificationRecord(
        issuer_identity=inp.issuer_identity,
        ticker=inp.ticker,
        legal_name=inp.legal_name,
        entity_class=entity_class,
        classification_status=status,
        confidence_semantics=(ConfidenceSemantics.DETERMINISTIC_PROOF if status == ClassificationStatus.QUALIFIED
                              else ConfidenceSemantics.CONTRADICTORY_EVIDENCE if status == ClassificationStatus.CONFLICT
                              else ConfidenceSemantics.UNPROVEN_ABSENCE),
        evidence_tier=evidence_tier,
        classification_evidence_id=ev_id,
        source_id=SOURCE_ID,
        source_record_id=None,
        effective_from=None,
        knowledge_available_at=None,
        verified_at=verified_at,
        classification_reason=reason,
        supporting_evidence=supporting_evidence,
    )


def reconcile_ticker(inp: ReconciliationInput, *, verified_at: str | None = None) -> ReconciliationResult:
    """Reconcile one ticker's retained evidence into a classification outcome.

    Zero ticker branches: every decision below reads only from the four evidence fields
    on `inp`, never from `inp.ticker` itself.
    """
    v_time = verified_at or datetime.now(timezone.utc).isoformat()

    # Security-type guard first: only an explicitly known non-equity instrument blocks.
    # A ticker missing from the C.1 candidate master (instrument_class=None) is not
    # evidence of an unsupported security type -- it just means that snapshot doesn't
    # cover it -- so classification proceeds on the remaining evidence in that case.
    if inp.instrument_class is not None and inp.instrument_class not in SUPPORTED_SECURITY_TYPES:
        detail = {"instrument_class": inp.instrument_class}
        return ReconciliationResult(record=None, outcome="NOT_APPLICABLE",
                                    reason_code=f"{REASON_UNSUPPORTED_SECURITY_TYPE}:{inp.instrument_class}",
                                    detail=detail)

    tax = inp.statement_taxonomy
    icb = inp.icb_industry_hint
    charter = _charter_specialized_match(inp.legal_name)

    detail = {
        "statement_taxonomy": tax, "icb_industry_hint": icb, "icb_industry_label": inp.icb_industry_label,
        "icb_industry_reason": inp.icb_industry_reason,
        "charter_specialized_match": charter.value if charter else None,
    }

    def qualified(entity_class: EntityClass, tier: EvidenceTier, reason: str) -> ReconciliationResult:
        rec = _record(inp, entity_class=entity_class, status=ClassificationStatus.QUALIFIED,
                      evidence_tier=tier, reason=reason, supporting_evidence=detail, verified_at=v_time)
        return ReconciliationResult(record=rec, outcome=entity_class.value, reason_code=reason, detail=detail)

    def conflict(reason: str) -> ReconciliationResult:
        rec = _record(inp, entity_class=EntityClass.UNKNOWN, status=ClassificationStatus.CONFLICT,
                      evidence_tier=EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION, reason=reason,
                      supporting_evidence=detail, verified_at=v_time)
        return ReconciliationResult(record=rec, outcome="CONFLICT", reason_code=f"{REASON_CONFLICT}:{reason}", detail=detail)

    def unknown(reason: str) -> ReconciliationResult:
        return ReconciliationResult(record=None, outcome="UNKNOWN", reason_code=reason, detail=detail)

    # --- Statement evidence positively shows a specialized-financial template ---
    if tax == _TAX_SECURITIES:
        if icb in (HINT_BANK, HINT_INSURANCE, HINT_CORPORATE):
            return conflict(f"statement_taxonomy={tax!r} disagrees with icb_industry_hint={icb!r}")
        if charter is not None and charter != EntityClass.SECURITIES:
            return conflict(f"statement_taxonomy={tax!r} disagrees with charter evidence ({charter.value})")
        return qualified(EntityClass.SECURITIES, EvidenceTier.FINANCIAL_STATEMENT_TEMPLATE,
                         "statement_taxonomy positively evidences the securities-company template"
                         + (f"; corroborated by icb_industry_hint={icb!r}" if icb == HINT_AMBIGUOUS_FINANCIAL else ""))

    if tax == _TAX_CREDIT_INSTITUTION:
        if icb in (HINT_INSURANCE, HINT_CORPORATE):
            return conflict(f"statement_taxonomy={tax!r} disagrees with icb_industry_hint={icb!r}")
        if icb == HINT_BANK:
            if charter is not None and charter != EntityClass.BANK:
                return conflict(f"statement_taxonomy+icb agree on BANK but charter evidence says {charter.value}")
            return qualified(EntityClass.BANK, EvidenceTier.FINANCIAL_STATEMENT_TEMPLATE,
                             "statement_taxonomy positively evidences the credit-institution template; "
                             f"corroborated by icb_industry_hint={icb!r}")
        # icb is AMBIGUOUS_FINANCIAL or None: credit_institution alone cannot distinguish bank
        # from finance_company (both file under Circular 49/2014/TT-NHNN); only a specialized
        # charter match may narrow it further.
        if charter == EntityClass.BANK:
            return qualified(EntityClass.BANK, EvidenceTier.EXCHANGE_SECURITY_MASTER,
                             "statement_taxonomy evidences the credit-institution template; "
                             "specialized charter narrows it to a commercial bank")
        if charter == EntityClass.FINANCE_COMPANY:
            return qualified(EntityClass.FINANCE_COMPANY, EvidenceTier.EXCHANGE_SECURITY_MASTER,
                             "statement_taxonomy evidences the credit-institution template; "
                             "specialized charter narrows it to a finance company")
        if charter is not None:
            return conflict(f"statement_taxonomy={tax!r} disagrees with charter evidence ({charter.value})")
        return unknown(REASON_AMBIGUOUS_NO_SUBTYPE)

    if tax == _TAX_AMBIGUOUS_SPECIALIZED:
        if icb == HINT_CORPORATE:
            return conflict(f"statement_taxonomy={tax!r} disagrees with icb_industry_hint={icb!r}")
        if icb == HINT_BANK:
            if charter is not None and charter != EntityClass.BANK:
                return conflict(f"statement_taxonomy+icb agree on BANK but charter evidence says {charter.value}")
            return qualified(EntityClass.BANK, EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION,
                             f"statement_taxonomy={tax!r} confirms a specialized-financial template; "
                             f"icb_industry_hint={icb!r} resolves which one")
        if icb == HINT_INSURANCE:
            if charter is not None and charter != EntityClass.INSURANCE:
                return conflict(f"statement_taxonomy+icb agree on INSURANCE but charter evidence says {charter.value}")
            return qualified(EntityClass.INSURANCE, EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION,
                             f"statement_taxonomy={tax!r} confirms a specialized-financial template; "
                             f"icb_industry_hint={icb!r} resolves which one")
        # icb is AMBIGUOUS_FINANCIAL or None: fall back to a specialized charter match.
        if charter is not None:
            return qualified(charter, EvidenceTier.EXCHANGE_SECURITY_MASTER,
                             f"statement_taxonomy={tax!r} confirms a specialized-financial template; "
                             f"specialized charter evidence resolves which one ({charter.value})")
        return unknown(REASON_AMBIGUOUS_NO_SUBTYPE)

    # --- Statement evidence does NOT positively show a specialized-financial template
    #     (tax == "corporate_vas", "unresolved", or no retained balance sheet at all) ---
    if icb == HINT_CORPORATE:
        if charter is not None:
            return conflict(f"icb_industry_hint={icb!r} disagrees with charter evidence ({charter.value})")
        return qualified(EntityClass.CORPORATE, EvidenceTier.EXCHANGE_INDUSTRY_CLASSIFICATION,
                         "icb_industry_hint positively evidences a governed non-financial sector"
                         + ("; no retained balance-sheet template contradicts it" if tax is None
                            else f"; retained statement_taxonomy={tax!r} does not contradict it"))

    if icb == HINT_BANK:
        return conflict(f"icb_industry_hint={icb!r} disagrees with statement_taxonomy={tax!r}")

    if icb == HINT_INSURANCE:
        return conflict(f"icb_industry_hint={icb!r} disagrees with statement_taxonomy={tax!r}")

    if icb == HINT_AMBIGUOUS_FINANCIAL:
        if tax == _TAX_CORPORATE and charter is not None:
            return conflict(f"statement_taxonomy={tax!r} (ordinary template) disagrees with "
                            f"charter evidence ({charter.value}) despite icb_industry_hint={icb!r}")
        if charter is not None:
            return qualified(charter, EvidenceTier.EXCHANGE_SECURITY_MASTER,
                             f"icb_industry_hint={icb!r} is uncontradicted; specialized charter "
                             f"evidence resolves the specific subtype ({charter.value})")
        return unknown(REASON_AMBIGUOUS_NO_SUBTYPE)

    # icb is None: either no industry-sync record, or an unrecognized future ICB label.
    if inp.icb_industry_label is not None:
        # A label we don't recognize -- distinct, more specific reason than "missing" (defensive
        # against ICB taxonomy drift; never silently treated as either financial or industrial).
        if charter is not None:
            return qualified(charter, EvidenceTier.EXCHANGE_SECURITY_MASTER,
                             f"icb_level_2_label={inp.icb_industry_label!r} is unrecognized; specialized "
                             f"charter evidence independently resolves the class ({charter.value})")
        return unknown(f"{REASON_METADATA_TOO_GENERIC}:{inp.icb_industry_label!r}")

    if charter is not None:
        return qualified(charter, EvidenceTier.EXCHANGE_SECURITY_MASTER,
                         f"no industry-sync record; specialized charter evidence independently "
                         f"resolves the class ({charter.value})")
    return unknown(REASON_ENTITY_TYPE_MISSING)
