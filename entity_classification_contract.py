"""Phase 2 / P2-E: Evidence-Backed Entity Classification Contract.

Defines the canonical entity classification schema, deterministic status codes,
evidence tiers, and immutable provenance record containers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "entity_classification_contract/v1"


class EntityClass(StrEnum):
    CORPORATE = "corporate"
    BANK = "bank"
    SECURITIES = "securities"
    INSURANCE = "insurance"
    FINANCE_COMPANY = "finance_company"
    UNKNOWN = "unknown"


class ClassificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"            # Positive, unambiguous evidence established
    UNKNOWN = "UNKNOWN"                # Insufficient evidence; fails closed
    AMBIGUOUS = "AMBIGUOUS"            # Multiple competing non-conflicting interpretations
    NOT_APPLICABLE = "NOT_APPLICABLE"  # Non-operating or unsupported structure
    CONFLICT = "CONFLICT"              # Contradictory evidence across authoritative sources


class EvidenceTier(StrEnum):
    DOCUMENTED_VERIFIED = "documented_verified"                # Official regulatory/exchange filing
    EXCHANGE_SECURITY_MASTER = "exchange_security_master"      # Official listing/security master charter
    FINANCIAL_STATEMENT_TEMPLATE = "statement_template"        # BCTC Form codes & exclusive line-item markers
    CURATED_SEED_AUTHORITY = "curated_seed_authority"          # config/ticker_entity_profiles.csv seed baseline


class ConfidenceSemantics(StrEnum):
    DETERMINISTIC_PROOF = "DETERMINISTIC_PROOF"
    UNPROVEN_ABSENCE = "UNPROVEN_ABSENCE"
    CONTRADICTORY_EVIDENCE = "CONTRADICTORY_EVIDENCE"


def _canonical_json(val: Any) -> str:
    return json.dumps(val, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def compute_classification_evidence_id(
    *,
    issuer_identity: str,
    ticker: str,
    entity_class: str,
    classification_status: str,
    source_id: str,
    evidence_payload: Mapping[str, Any],
) -> str:
    """Compute deterministic SHA-256 evidence hash bound to classification payload."""
    payload = {
        "issuer_identity": str(issuer_identity).strip(),
        "ticker": str(ticker).upper().strip(),
        "entity_class": str(entity_class).strip().lower(),
        "classification_status": str(classification_status).strip(),
        "source_id": str(source_id).strip(),
        "evidence_payload": dict(evidence_payload),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EntityClassificationRecord:
    """Immutable, provenance-bound entity classification record."""
    issuer_identity: str
    ticker: str
    legal_name: str | None
    entity_class: EntityClass
    classification_status: ClassificationStatus
    confidence_semantics: ConfidenceSemantics
    evidence_tier: EvidenceTier
    classification_evidence_id: str
    source_id: str
    source_record_id: str | None
    effective_from: str | None
    knowledge_available_at: str | None
    verified_at: str
    classification_reason: str
    supporting_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "contract_version": CONTRACT_VERSION,
            "issuer_identity": self.issuer_identity,
            "ticker": self.ticker,
            "legal_name": self.legal_name,
            "entity_class": self.entity_class.value,
            "classification_status": self.classification_status.value,
            "confidence_semantics": self.confidence_semantics.value,
            "evidence_tier": self.evidence_tier.value,
            "classification_evidence_id": self.classification_evidence_id,
            "source_id": self.source_id,
            "source_record_id": self.source_record_id,
            "effective_from": self.effective_from,
            "knowledge_available_at": self.knowledge_available_at,
            "verified_at": self.verified_at,
            "classification_reason": self.classification_reason,
            "supporting_evidence": self.supporting_evidence,
        }
