"""Tests for Layered Authority Topology B Entity Classification Contract & Downstream Applicability.

Verifies:
1. Seed authority invariance across all 20 curated baseline profiles.
2. Exact resolution of all 20 owner-approved promoted records.
3. Downstream applicability rules on financials (ABB, ACB, AAS, ABW, ABI fail closed on corporate debt/EBITDA).
4. Conflict resolution: disagreement between seed and promoted fails closed as CONFLICT.
5. Non-promoted future classifier output gate: unpromoted QUALIFIED record receives NO authority.
6. Temporal safety: historical PIT request returns HISTORICAL_PIT_NOT_ESTABLISHED.
7. Broad denominator consistency: 20 seed + 20 promoted = 40 positive current-state, 1,620 listed UNKNOWN.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from entity_classification_contract import (
    AUTHORITY_SCOPE_CURRENT_STATE,
    ClassificationStatus,
    ConfidenceSemantics,
    EntityClass,
    EntityClassificationRecord,
    EvidenceTier,
    HISTORICAL_PIT_NOT_ESTABLISHED,
    LayeredClassificationResult,
    load_layered_entity_profiles,
    load_promoted_entity_classifications,
    load_seed_profiles,
    resolve_layered_entity_classification,
)
from financial_entity_applicability import (
    load_entity_profiles,
    metric_applicability,
    resolve_archetype,
)
from financial_mapping import FinancialMappingRegistry

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SEED_PROFILES = {
    "PAN": "corporate",
    "HPG": "corporate",
    "FPT": "corporate",
    "PNJ": "corporate",
    "PVD": "corporate",
    "POW": "corporate",
    "QNS": "corporate",
    "NVL": "corporate",
    "VNM": "corporate",
    "MWG": "corporate",
    "GAS": "corporate",
    "VIC": "corporate",
    "VRE": "corporate",
    "SSI": "securities",
    "VCB": "bank",
    "BID": "bank",
    "MBB": "bank",
    "TCB": "bank",
    "BVH": "insurance",
    "EVF": "finance_company",
}

EXPECTED_PROMOTED_RECORDS = {
    "A32": "corporate",
    "AAA": "corporate",
    "AAH": "corporate",
    "AAM": "corporate",
    "AAN": "corporate",
    "AAS": "securities",
    "AAT": "corporate",
    "AAV": "corporate",
    "ABB": "bank",
    "ABC": "corporate",
    "ABI": "insurance",
    "ABR": "corporate",
    "ABS": "corporate",
    "ABT": "corporate",
    "ABW": "securities",
    "ACB": "bank",
    "ACC": "corporate",
    "ACE": "corporate",
    "ACG": "corporate",
    "ACL": "corporate",
}


def test_seed_authority_invariance():
    """All 20 baseline curated profiles must resolve identically."""
    seeds = load_seed_profiles()
    assert len(seeds) == 20
    assert seeds == EXPECTED_SEED_PROFILES

    for ticker, expected_class in EXPECTED_SEED_PROFILES.items():
        res = resolve_layered_entity_classification(ticker)
        assert res.resolved_entity_class.value == expected_class
        assert res.classification_status == ClassificationStatus.QUALIFIED
        assert res.authority_tier == "curated_seed_authority"
        assert res.is_positive_authority is True
        assert res.authority_scope == AUTHORITY_SCOPE_CURRENT_STATE
        assert res.historical_pit_authority == HISTORICAL_PIT_NOT_ESTABLISHED


def test_promoted_records_resolution():
    """All 20 owner-approved promoted records must resolve to their qualified classes."""
    promoted = load_promoted_entity_classifications()
    assert len(promoted) == 20
    assert set(promoted.keys()) == set(EXPECTED_PROMOTED_RECORDS.keys())

    for ticker, expected_class in EXPECTED_PROMOTED_RECORDS.items():
        rec = promoted[ticker]
        assert rec.classification_status == ClassificationStatus.QUALIFIED
        assert rec.entity_class.value == expected_class
        assert rec.evidence_tier == EvidenceTier.EXCHANGE_SECURITY_MASTER
        assert rec.confidence_semantics == ConfidenceSemantics.DETERMINISTIC_PROOF

        res = resolve_layered_entity_classification(ticker)
        assert res.resolved_entity_class.value == expected_class
        assert res.classification_status == ClassificationStatus.QUALIFIED
        assert res.authority_tier == "promoted_record_authority"
        assert res.is_positive_authority is True
        assert res.authority_scope == AUTHORITY_SCOPE_CURRENT_STATE
        assert res.historical_pit_authority == HISTORICAL_PIT_NOT_ESTABLISHED


def test_layered_profiles_merging():
    """Merged layered profiles contain the 40 original records plus whatever the
    legacy-recovery tier (config/promoted_entity_classifications_legacy_recovery_v1.json,
    see LEGACY_ENTITY_CLASSIFICATION_TRACKED_AUTHORITY_RECOVERY_V1) and the scale-out tier
    (config/promoted_entity_classifications_scaleout_v1.json, see
    MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1) currently add -- the 40 seed
    and original-promoted records are the fixed part of this invariant; the other two
    counts are read from their own manifests rather than hardcoded, since widening them is
    the entire point of those milestones."""
    from entity_classification_contract import (
        load_legacy_recovery_entity_classifications,
        load_scaleout_promoted_entity_classifications,
    )

    profiles = load_layered_entity_profiles()
    legacy_recovery_count = len(load_legacy_recovery_entity_classifications())
    scaleout_count = len(load_scaleout_promoted_entity_classifications())
    assert len(profiles) == 40 + legacy_recovery_count + scaleout_count
    # All 20 seed profiles present
    for t, c in EXPECTED_SEED_PROFILES.items():
        assert profiles[t] == c
    # All 20 promoted profiles present
    for t, c in EXPECTED_PROMOTED_RECORDS.items():
        assert profiles[t] == c


def test_downstream_financial_entity_applicability():
    """Verify archetype and metric applicability on promoted records."""
    # 1. Corporate: A32
    arch_a32 = resolve_archetype("A32")
    assert arch_a32["issuer_entity_type"] == "corporate"
    assert arch_a32["authority"] == "promoted_record_authority"
    app_ebitda_a32 = metric_applicability(arch_a32, "ebitda")
    assert app_ebitda_a32["status"] == "applicable_subject_to_inputs"
    app_ev_a32 = metric_applicability(arch_a32, "ev_ebitda")
    assert app_ev_a32["status"] == "applicable_subject_to_inputs"

    # 2. Bank: ABB and ACB
    for b_sym in ("ABB", "ACB"):
        arch_bank = resolve_archetype(b_sym)
        assert arch_bank["issuer_entity_type"] == "bank"
        assert arch_bank["authority"] == "promoted_record_authority"
        app_ebitda = metric_applicability(arch_bank, "ebitda")
        assert app_ebitda["status"] == "not_applicable"
        assert "is a financial filer" in app_ebitda["reason"]
        app_ev = metric_applicability(arch_bank, "ev_ebitda")
        assert app_ev["status"] == "not_applicable"

    # 3. Securities: AAS and ABW
    for s_sym in ("AAS", "ABW"):
        arch_sec = resolve_archetype(s_sym)
        assert arch_sec["issuer_entity_type"] == "securities"
        assert arch_sec["authority"] == "promoted_record_authority"
        app_ebitda = metric_applicability(arch_sec, "ebitda")
        assert app_ebitda["status"] == "not_applicable"
        app_ev = metric_applicability(arch_sec, "ev_ebitda")
        assert app_ev["status"] == "not_applicable"

    # 4. Insurance: ABI
    arch_ins = resolve_archetype("ABI")
    assert arch_ins["issuer_entity_type"] == "insurance"
    assert arch_ins["authority"] == "promoted_record_authority"
    app_ebitda = metric_applicability(arch_ins, "ebitda")
    assert app_ebitda["status"] == "not_applicable"
    app_ev = metric_applicability(arch_ins, "ev_ebitda")
    assert app_ev["status"] == "not_applicable"


def test_financial_mapping_registry_integration():
    """FinancialMappingRegistry must load all 40 layered entity profiles."""
    mapping_csv = ROOT / "config" / "financial_item_map.csv"
    profiles_csv = ROOT / "config" / "ticker_entity_profiles.csv"
    registry = FinancialMappingRegistry(mapping_csv, profiles_csv)
    
    assert registry.entity_type_for("HPG") == "corporate"
    assert registry.entity_type_for("VCB") == "bank"
    assert registry.entity_type_for("A32") == "corporate"
    assert registry.entity_type_for("ABB") == "bank"
    assert registry.entity_type_for("AAS") == "securities"
    assert registry.entity_type_for("ABI") == "insurance"
    assert registry.entity_type_for("UNKNOWN_TICKER_XYZ") == "unknown"


def test_conflict_fail_closed():
    """Seed authority and promoted record disagreement must fail closed as CONFLICT."""
    # Synthetic conflicting record for HPG (seed is corporate, promoted says bank)
    synthetic_conflict_rec = EntityClassificationRecord(
        issuer_identity="candidate:synthetic",
        ticker="HPG",
        legal_name="Tập đoàn Hòa Phát",
        entity_class=EntityClass.BANK,
        classification_status=ClassificationStatus.QUALIFIED,
        confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
        evidence_tier=EvidenceTier.EXCHANGE_SECURITY_MASTER,
        classification_evidence_id="synthetic_hash",
        source_id="synthetic_test",
        source_record_id=None,
        effective_from=None,
        knowledge_available_at=None,
        verified_at="2026-08-19T00:00:00Z",
        classification_reason="synthetic conflict test",
    )

    res = resolve_layered_entity_classification(
        "HPG",
        seed_profiles={"HPG": "corporate"},
        promoted_records={"HPG": synthetic_conflict_rec},
    )
    assert res.classification_status == ClassificationStatus.CONFLICT
    assert res.resolved_entity_class == EntityClass.UNKNOWN
    assert res.authority_tier == "conflict"
    assert res.is_positive_authority is False
    assert "disagrees with promoted record" in res.reason


def test_seed_and_promoted_agreement_stable():
    """Seed authority and promoted record agreement resolves stably to seed authority."""
    synthetic_matching_rec = EntityClassificationRecord(
        issuer_identity="candidate:synthetic",
        ticker="HPG",
        legal_name="Tập đoàn Hòa Phát",
        entity_class=EntityClass.CORPORATE,
        classification_status=ClassificationStatus.QUALIFIED,
        confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
        evidence_tier=EvidenceTier.EXCHANGE_SECURITY_MASTER,
        classification_evidence_id="synthetic_hash",
        source_id="synthetic_test",
        source_record_id=None,
        effective_from=None,
        knowledge_available_at=None,
        verified_at="2026-08-19T00:00:00Z",
        classification_reason="synthetic matching test",
    )

    res = resolve_layered_entity_classification(
        "HPG",
        seed_profiles={"HPG": "corporate"},
        promoted_records={"HPG": synthetic_matching_rec},
    )
    assert res.classification_status == ClassificationStatus.QUALIFIED
    assert res.resolved_entity_class == EntityClass.CORPORATE
    assert res.authority_tier == "curated_seed_authority"
    assert res.is_positive_authority is True


def test_promoted_ambiguous_and_conflict_records():
    """Promoted record with AMBIGUOUS or CONFLICT status must NOT provide positive authority."""
    ambiguous_rec = EntityClassificationRecord(
        issuer_identity="candidate:ambig",
        ticker="AMB",
        legal_name="Công ty Cổ phần Mơ Hồ",
        entity_class=EntityClass.UNKNOWN,
        classification_status=ClassificationStatus.AMBIGUOUS,
        confidence_semantics=ConfidenceSemantics.UNPROVEN_ABSENCE,
        evidence_tier=EvidenceTier.EXCHANGE_SECURITY_MASTER,
        classification_evidence_id="hash_amb",
        source_id="test",
        source_record_id=None,
        effective_from=None,
        knowledge_available_at=None,
        verified_at="2026-08-19T00:00:00Z",
        classification_reason="ambiguous classification",
    )
    res = resolve_layered_entity_classification(
        "AMB",
        seed_profiles={},
        promoted_records={"AMB": ambiguous_rec},
    )
    assert res.classification_status == ClassificationStatus.AMBIGUOUS
    assert res.resolved_entity_class == EntityClass.UNKNOWN
    assert res.is_positive_authority is False


def test_future_unpromoted_qualified_classifier_output_fails_closed():
    """CRITICAL: A qualified classifier output NOT in the approved promotion manifest provides NO authority."""
    # Suppose a classifier run evaluated VIC2 and found it QUALIFIED corporate
    fresh_classifier_output = EntityClassificationRecord(
        issuer_identity="candidate:vic2",
        ticker="VIC2",
        legal_name="Tập đoàn Vingroup 2",
        entity_class=EntityClass.CORPORATE,
        classification_status=ClassificationStatus.QUALIFIED,
        confidence_semantics=ConfidenceSemantics.DETERMINISTIC_PROOF,
        evidence_tier=EvidenceTier.EXCHANGE_SECURITY_MASTER,
        classification_evidence_id="future_run_hash",
        source_id="future_classifier_run",
        source_record_id=None,
        effective_from=None,
        knowledge_available_at=None,
        verified_at="2026-08-20T00:00:00Z",
        classification_reason="future classifier run without owner promotion authorization",
    )

    # Calling resolve_layered_entity_classification with the default approved manifest:
    # VIC2 is not in seed, and not in config/promoted_entity_classifications.json
    res = resolve_layered_entity_classification("VIC2")
    assert res.resolved_entity_class == EntityClass.UNKNOWN
    assert res.classification_status == ClassificationStatus.UNKNOWN
    assert res.authority_tier == "unknown"
    assert res.is_positive_authority is False
    assert "unclassified listed equity fails closed as UNKNOWN" in res.reason


def test_temporal_safety_and_historical_pit():
    """Historical point-in-time request must fail closed with HISTORICAL_PIT_NOT_ESTABLISHED."""
    # Requesting historical PIT explicitly
    res_pit = resolve_layered_entity_classification("A32", require_historical_pit=True)
    assert res_pit.resolved_entity_class == EntityClass.UNKNOWN
    assert res_pit.classification_status == ClassificationStatus.UNKNOWN
    assert res_pit.authority_tier == "historical_pit_not_established"
    assert res_pit.historical_pit_authority == HISTORICAL_PIT_NOT_ESTABLISHED
    assert res_pit.is_positive_authority is False
    assert "HISTORICAL_PIT_NOT_ESTABLISHED" in res_pit.reason

    # Requesting as_of before knowledge availability
    res_asof_past = resolve_layered_entity_classification("A32", as_of="2020-01-01")
    assert res_asof_past.resolved_entity_class == EntityClass.UNKNOWN
    assert res_asof_past.classification_status == ClassificationStatus.UNKNOWN
    assert res_asof_past.authority_tier == "prior_to_knowledge_availability"
    assert res_asof_past.is_positive_authority is False

    # Requesting as_of at or after knowledge availability (2026-08-19)
    res_asof_now = resolve_layered_entity_classification("A32", as_of="2026-08-19")
    assert res_asof_now.resolved_entity_class == EntityClass.CORPORATE
    assert res_asof_now.is_positive_authority is True


def test_p2e3_promotion_artifact_integrity():
    """Verify P2-E3 promotion artifact exists and matches deterministic hash."""
    from field_temporal_contract import stable_id

    artifact_path = ROOT / "operations-review" / "p2e3-bounded-entity-classification-promotion-20260819" / "p2e3_entity_classification_promotion_artifact.json"
    assert artifact_path.is_file()
    
    data = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert data["artifact_id"] == "p2e3_entity_classification_promotion:f47d56819fc6c1668614338efc103c7eed1508159c8bae5f66f9a09f459680a9"
    assert data["artifact_hash"] == "f47d56819fc6c1668614338efc103c7eed1508159c8bae5f66f9a09f459680a9"
    assert data["authority_status"] == "CURRENT_STATE_AUTHORITY_PROMOTED"

    # Verify scale metrics
    scale = data["scale_metrics"]
    assert scale["total_canonical_candidates"] == 3250
    assert scale["listed_equity_candidates"] == 1660
    assert scale["seed_authority_records"] == 20
    assert scale["new_promoted_records"] == 20
    assert scale["total_positive_current_state_records"] == 40
    assert scale["remaining_unknown_listed_equities"] == 1620
    assert scale["seed_profile_file_modified"] is False
    assert scale["historical_pit_promoted"] is False
    assert scale["automatic_future_promotion"] is False


def test_multi_period_financial_panel_layered_integration():
    """Verify multi_period_financial_panel respects layered authority profiles."""
    from multi_period_financial_panel import evaluate_sector_applicability, ApplicabilityState

    profiles = load_entity_profiles()

    # Seed corporate HPG: debt_to_equity is APPLICABLE
    state_hpg, _ = evaluate_sector_applicability(
        ticker="HPG",
        entity_type=profiles.get("HPG"),
        canonical_metric="debt_to_equity",
    )
    assert state_hpg == ApplicabilityState.APPLICABLE

    # Seed bank VCB: debt_to_equity is NOT_APPLICABLE
    state_vcb, _ = evaluate_sector_applicability(
        ticker="VCB",
        entity_type=profiles.get("VCB"),
        canonical_metric="debt_to_equity",
    )
    assert state_vcb == ApplicabilityState.NOT_APPLICABLE

    # Promoted corporate A32: debt_to_equity and ebitda are APPLICABLE
    state_a32, _ = evaluate_sector_applicability(
        ticker="A32",
        entity_type=profiles.get("A32"),
        canonical_metric="debt_to_equity",
    )
    assert state_a32 == ApplicabilityState.APPLICABLE

    # Promoted bank ABB: debt_to_equity and ebitda are NOT_APPLICABLE
    state_abb_debt, _ = evaluate_sector_applicability(
        ticker="ABB",
        entity_type=profiles.get("ABB"),
        canonical_metric="debt_to_equity",
    )
    assert state_abb_debt == ApplicabilityState.NOT_APPLICABLE

    state_abb_ebitda, _ = evaluate_sector_applicability(
        ticker="ABB",
        entity_type=profiles.get("ABB"),
        canonical_metric="ebitda",
    )
    assert state_abb_ebitda == ApplicabilityState.NOT_APPLICABLE

    # Promoted securities AAS: debt_to_equity is NOT_APPLICABLE
    state_aas, _ = evaluate_sector_applicability(
        ticker="AAS",
        entity_type=profiles.get("AAS"),
        canonical_metric="debt_to_equity",
    )
    assert state_aas == ApplicabilityState.NOT_APPLICABLE

    # Promoted insurance ABI: debt_to_equity is NOT_APPLICABLE
    state_abi, _ = evaluate_sector_applicability(
        ticker="ABI",
        entity_type=profiles.get("ABI"),
        canonical_metric="debt_to_equity",
    )
    assert state_abi == ApplicabilityState.NOT_APPLICABLE

    # Non-promoted unknown: UNKNOWN
    state_unk, _ = evaluate_sector_applicability(
        ticker="XYZ_NON_EXISTENT",
        entity_type=profiles.get("XYZ_NON_EXISTENT"),
        canonical_metric="debt_to_equity",
    )
    assert state_unk == ApplicabilityState.UNKNOWN

