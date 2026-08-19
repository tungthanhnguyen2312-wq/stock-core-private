"""Phase 2 / P2-E: Evidence-Backed Entity Classification Contract.

Defines the canonical entity classification schema, deterministic status codes,
evidence tiers, and immutable provenance record containers.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from enum import StrEnum
import hashlib
import json
from pathlib import Path
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


# Layered Authority Constants
ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_SEED_PROFILES_PATH = ROOT_DIR / "config" / "ticker_entity_profiles.csv"
DEFAULT_PROMOTED_CLASSIFICATIONS_PATH = ROOT_DIR / "config" / "promoted_entity_classifications.json"

AUTHORITY_SCOPE_CURRENT_STATE = "CURRENT_STATE_ONLY"
HISTORICAL_PIT_NOT_ESTABLISHED = "NOT_ESTABLISHED"


@dataclass(frozen=True)
class LayeredClassificationResult:
    """Result container from the generic Layered Authority Topology B resolver."""
    ticker: str
    resolved_entity_class: EntityClass
    classification_status: ClassificationStatus
    authority_tier: str
    authority_scope: str
    historical_pit_authority: str
    reason: str
    seed_record: str | None = None
    promoted_record: EntityClassificationRecord | None = None
    is_positive_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "resolved_entity_class": self.resolved_entity_class.value,
            "classification_status": self.classification_status.value,
            "authority_tier": self.authority_tier,
            "authority_scope": self.authority_scope,
            "historical_pit_authority": self.historical_pit_authority,
            "reason": self.reason,
            "seed_record": self.seed_record,
            "promoted_record": self.promoted_record.to_dict() if self.promoted_record else None,
            "is_positive_authority": self.is_positive_authority,
        }


def load_seed_profiles(path: Path | str | None = None) -> dict[str, str]:
    """Load baseline curated profiles from config/ticker_entity_profiles.csv."""
    p = Path(path) if path else DEFAULT_SEED_PROFILES_PATH
    if not p.is_file():
        return {}
    profiles: dict[str, str] = {}
    with p.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sym = str(row.get("ticker") or "").strip().upper()
            etype = str(row.get("entity_type") or "").strip().lower()
            if sym and etype and etype not in {"unknown", "none", "null"}:
                profiles[sym] = etype
    return profiles


def load_promoted_entity_classifications(
    manifest_path: Path | str | None = None,
) -> dict[str, EntityClassificationRecord]:
    """Load approved promoted entity classification records from config/promoted_entity_classifications.json."""
    p = Path(manifest_path) if manifest_path else DEFAULT_PROMOTED_CLASSIFICATIONS_PATH
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    records_raw = data.get("promoted_records", {})
    records: dict[str, EntityClassificationRecord] = {}
    for sym, r in records_raw.items():
        clean_sym = str(sym).upper().strip()
        e_cls_str = str(r.get("entity_class", "unknown")).lower().strip()
        e_cls = EntityClass(e_cls_str) if e_cls_str in {e.value for e in EntityClass} else EntityClass.UNKNOWN
        c_status_str = str(r.get("classification_status", "UNKNOWN")).strip()
        c_status = ClassificationStatus(c_status_str) if c_status_str in {c.value for c in ClassificationStatus} else ClassificationStatus.UNKNOWN
        c_sem_str = str(r.get("confidence_semantics", "DETERMINISTIC_PROOF")).strip()
        c_sem = ConfidenceSemantics(c_sem_str) if c_sem_str in {cs.value for cs in ConfidenceSemantics} else ConfidenceSemantics.DETERMINISTIC_PROOF
        e_tier_str = str(r.get("evidence_tier", "exchange_security_master")).strip()
        e_tier = EvidenceTier(e_tier_str) if e_tier_str in {et.value for et in EvidenceTier} else EvidenceTier.EXCHANGE_SECURITY_MASTER

        rec = EntityClassificationRecord(
            issuer_identity=r.get("issuer_identity", f"issuer:{clean_sym}"),
            ticker=clean_sym,
            legal_name=r.get("legal_name"),
            entity_class=e_cls,
            classification_status=c_status,
            confidence_semantics=c_sem,
            evidence_tier=e_tier,
            classification_evidence_id=r.get("classification_evidence_id", ""),
            source_id=r.get("source_id", "config/promoted_entity_classifications.json"),
            source_record_id=r.get("source_record_id"),
            effective_from=r.get("effective_from"),
            knowledge_available_at=r.get("knowledge_available_at"),
            verified_at=r.get("verified_at", ""),
            classification_reason=r.get("classification_reason", "promoted_record"),
            supporting_evidence=r.get("supporting_evidence", {}),
        )
        records[clean_sym] = rec
    return records


def resolve_layered_entity_classification(
    ticker: str,
    *,
    seed_profiles: Mapping[str, str] | None = None,
    promoted_records: Mapping[str, EntityClassificationRecord] | None = None,
    seed_path: Path | str | None = None,
    promoted_path: Path | str | None = None,
    as_of: str | None = None,
    require_historical_pit: bool = False,
) -> LayeredClassificationResult:
    """Resolve an issuer ticker under Layered Authority Topology B.

    Precedence:
    A. If seed authority exists: seed remains authoritative.
    B. If no seed exists and an explicitly promoted qualified record exists: use promoted record.
    C. If seed and promoted record disagree: fail closed as CONFLICT. Do NOT silently override seed.
    D. If promoted record is AMBIGUOUS / CONFLICT / UNKNOWN: must not supply positive classification.
    E. If neither authority exists: UNKNOWN.
    """
    clean_sym = str(ticker).upper().strip()

    if require_historical_pit:
        return LayeredClassificationResult(
            ticker=clean_sym,
            resolved_entity_class=EntityClass.UNKNOWN,
            classification_status=ClassificationStatus.UNKNOWN,
            authority_tier="historical_pit_not_established",
            authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
            historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
            reason="HISTORICAL_PIT_NOT_ESTABLISHED: Layered authority topology B establishes current-state entity classification only; historical point-in-time lookup is not established",
            seed_record=None,
            promoted_record=None,
            is_positive_authority=False,
        )

    seeds = seed_profiles if seed_profiles is not None else load_seed_profiles(seed_path)
    promoted = promoted_records if promoted_records is not None else load_promoted_entity_classifications(promoted_path)

    seed_val = seeds.get(clean_sym)
    seed_class: EntityClass | None = None
    if seed_val:
        s_norm = seed_val.strip().lower()
        if s_norm in {e.value for e in EntityClass if e != EntityClass.UNKNOWN}:
            seed_class = EntityClass(s_norm)

    prom_rec = promoted.get(clean_sym)

    # Case A: Seed authority exists
    if seed_class is not None:
        if prom_rec is not None:
            if prom_rec.classification_status == ClassificationStatus.QUALIFIED and prom_rec.entity_class != seed_class:
                return LayeredClassificationResult(
                    ticker=clean_sym,
                    resolved_entity_class=EntityClass.UNKNOWN,
                    classification_status=ClassificationStatus.CONFLICT,
                    authority_tier="conflict",
                    authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
                    historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
                    reason=f"CONFLICT: seed authority ({seed_class.value}) disagrees with promoted record ({prom_rec.entity_class.value}); fails closed",
                    seed_record=seed_class.value,
                    promoted_record=prom_rec,
                    is_positive_authority=False,
                )
        return LayeredClassificationResult(
            ticker=clean_sym,
            resolved_entity_class=seed_class,
            classification_status=ClassificationStatus.QUALIFIED,
            authority_tier="curated_seed_authority",
            authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
            historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
            reason="authoritative_seed_profile_from_config_ticker_entity_profiles",
            seed_record=seed_class.value,
            promoted_record=prom_rec,
            is_positive_authority=True,
        )

    # Case B: No seed exists, check promoted records
    if prom_rec is not None:
        if as_of is not None:
            k_avail = prom_rec.knowledge_available_at or prom_rec.verified_at
            if k_avail and str(as_of).strip() < k_avail[:10]:
                return LayeredClassificationResult(
                    ticker=clean_sym,
                    resolved_entity_class=EntityClass.UNKNOWN,
                    classification_status=ClassificationStatus.UNKNOWN,
                    authority_tier="prior_to_knowledge_availability",
                    authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
                    historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
                    reason=f"as_of '{as_of}' is prior to knowledge_available_at/verified_at boundary '{k_avail}'; historical PIT not established",
                    seed_record=None,
                    promoted_record=prom_rec,
                    is_positive_authority=False,
                )

        if prom_rec.classification_status == ClassificationStatus.QUALIFIED and prom_rec.entity_class != EntityClass.UNKNOWN:
            return LayeredClassificationResult(
                ticker=clean_sym,
                resolved_entity_class=prom_rec.entity_class,
                classification_status=ClassificationStatus.QUALIFIED,
                authority_tier="promoted_record_authority",
                authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
                historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
                reason=f"promoted_record_authority:{prom_rec.classification_reason}",
                seed_record=None,
                promoted_record=prom_rec,
                is_positive_authority=True,
            )
        else:
            return LayeredClassificationResult(
                ticker=clean_sym,
                resolved_entity_class=EntityClass.UNKNOWN,
                classification_status=prom_rec.classification_status,
                authority_tier="promoted_non_qualified",
                authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
                historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
                reason=f"promoted_record_non_qualified:{prom_rec.classification_reason}",
                seed_record=None,
                promoted_record=prom_rec,
                is_positive_authority=False,
            )

    # Case C: Neither exists (or unpromoted classifier output)
    return LayeredClassificationResult(
        ticker=clean_sym,
        resolved_entity_class=EntityClass.UNKNOWN,
        classification_status=ClassificationStatus.UNKNOWN,
        authority_tier="unknown",
        authority_scope=AUTHORITY_SCOPE_CURRENT_STATE,
        historical_pit_authority=HISTORICAL_PIT_NOT_ESTABLISHED,
        reason="no_seed_profile_and_no_approved_promoted_record; unclassified listed equity fails closed as UNKNOWN",
        seed_record=None,
        promoted_record=None,
        is_positive_authority=False,
    )


def load_layered_entity_profiles(
    seed_path: Path | str | None = None,
    promoted_path: Path | str | None = None,
) -> dict[str, str]:
    """Load merged positive entity profiles {TICKER: entity_type} under Layered Authority Topology B.

    Precedence:
    1. Seed authority from config/ticker_entity_profiles.csv (20 baseline issuers)
    2. Exact owner-approved promoted records from config/promoted_entity_classifications.json (20 promoted issuers)
    3. Contradictory records across seed and promoted fail closed (omitted).
    4. Unpromoted issuers are omitted (defaulting to unknown).
    """
    seeds = load_seed_profiles(seed_path)
    promoted = load_promoted_entity_classifications(promoted_path)

    merged: dict[str, str] = {}

    # First apply all seed profiles
    for sym in seeds.keys():
        res = resolve_layered_entity_classification(
            sym,
            seed_profiles=seeds,
            promoted_records=promoted,
        )
        if res.is_positive_authority and res.resolved_entity_class != EntityClass.UNKNOWN:
            merged[sym] = res.resolved_entity_class.value

    # Next apply promoted records for non-seed tickers
    for sym in promoted.keys():
        if sym in merged:
            continue
        res = resolve_layered_entity_classification(
            sym,
            seed_profiles=seeds,
            promoted_records=promoted,
        )
        if res.is_positive_authority and res.resolved_entity_class != EntityClass.UNKNOWN:
            merged[sym] = res.resolved_entity_class.value

    return merged
