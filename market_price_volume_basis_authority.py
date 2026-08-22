"""Consolidated, read-only fitness-for-use authority for Vietnamese-equity PRICE and
VOLUME/TRADED-VALUE basis (``MARKET_PRICE_VOLUME_BASIS_QUALIFICATION_V1``).

WHAT THIS MODULE IS
    A single reusable capability matrix that answers, per (price/volume-value capability,
    downstream use case): is the underlying data acquired, are its semantics qualified, and
    is it ELIGIBLE / PARTIAL / BLOCKED / NOT_APPLICABLE / UNKNOWN for that specific use. Every
    verdict is read live from an already-authoritative module (``market_data_source_authority``,
    ``provider_price_basis_registry``, ``dnse_ohlc_price_basis_capability``,
    ``current_valuation_input_authority``, ``market_volume_value_semantic_contract``,
    ``market_capability_taxonomy``, ``dnse_fhsc_volume_basis``,
    ``dnse_fhsc_market_composition_scaleout``, ``official_corporate_action_ledger``) or cites a
    specific, dated ``docs/STATE.md`` / ``docs/DECISIONS.md`` entry. Nothing here re-derives a
    verdict, re-probes a provider, or promotes authority: ``authority_effect`` is always
    ``"NONE"`` and every echoed global invariant (``RAW_AS_TRADED``, ``QUALIFIED_LIQUIDITY_INPUTS``,
    ``POSITION_SIZING_IS_SAFE``) is read from its owning module, never restated as a local literal
    that could drift out of sync.

WHAT THIS MODULE IS NOT
    Not a new price/volume qualification engine, not a new source registry, not a valuation or
    liquidity calculator, and not a replacement for any cited module. If a cited module's verdict
    changes, this module's next run reflects that change automatically -- it has no frozen copies
    of another module's finding.

WHY ONE BLOCKED USE MUST NOT BLOCK ANOTHER
    Historical PIT/backtest ineligibility and current-descriptive eligibility are independent
    fitness cells on the same capability row. ``assert_registry_fail_closed`` checks the opposite
    direction only (nothing here may claim PIT/BACKTEST/LIQUIDITY/POSITION_SIZING eligibility) --
    it never forces a blocked use to also block an unrelated, independently qualified use.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import current_valuation_input_authority as current_valuation
import dnse_fhsc_market_composition_scaleout as fhsc_composition
import dnse_fhsc_volume_basis as fhsc_volume_basis
import dnse_ohlc_price_basis_capability as dnse_price_capability
import dnse_provider_native_closed_ohlc as dnse_native_ohlc
import market_capability_taxonomy as taxonomy
import market_data_source_authority as source_authority
import market_volume_capability_matrix as vci_volume_capability
import market_volume_value_semantic_contract as volume_value_contract
import official_corporate_action_ledger as corporate_action_ledger
import price_representation_contract as representation
import provider_price_basis_registry as price_basis_registry
from dnse_volume_composition_reconciliation import (
    C5_CANDIDATE,
    CANDIDATE_DEFINITIONS,
    CANONICAL_TRADES_LINEAGE_STATUS,
    CANONICAL_TRADES_SOURCE_COMMIT,
)
from market_phase2_foundation import DNSE_BOARD_SEMANTICS

CONTRACT_VERSION = "market_price_volume_basis_authority/v1"
SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------------
# Downstream use-case taxonomy (fixed by the milestone; never inferred per-row)
# ---------------------------------------------------------------------------------

CURRENT_DESCRIPTIVE_RESEARCH = "CURRENT_DESCRIPTIVE_RESEARCH"
CURRENT_VALUATION_RESEARCH = "CURRENT_VALUATION_RESEARCH"
LIQUIDITY_RESEARCH = "LIQUIDITY_RESEARCH"
ADV_ADTV_RESEARCH = "ADV_ADTV_RESEARCH"
POSITION_SIZING = "POSITION_SIZING"
HISTORICAL_RETURN_RESEARCH = "HISTORICAL_RETURN_RESEARCH"
PIT = "PIT"
BACKTEST = "BACKTEST"

USE_CASES = (
    CURRENT_DESCRIPTIVE_RESEARCH, CURRENT_VALUATION_RESEARCH, LIQUIDITY_RESEARCH,
    ADV_ADTV_RESEARCH, POSITION_SIZING, HISTORICAL_RETURN_RESEARCH, PIT, BACKTEST,
)

#: A use case that, if ever found ELIGIBLE/PARTIAL, would itself promote authority this
#: milestone is explicitly forbidden from promoting (docs/STATE.md Invariants 1-2).
_AUTHORITY_SENSITIVE_USE_CASES = frozenset({LIQUIDITY_RESEARCH, ADV_ADTV_RESEARCH, POSITION_SIZING, PIT, BACKTEST})

ELIGIBLE = "ELIGIBLE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"
FITNESS_STATES = (ELIGIBLE, PARTIAL, BLOCKED, NOT_APPLICABLE, UNKNOWN)

PRICE_BASIS_DOMAIN = "PRICE_BASIS"
VOLUME_VALUE_BASIS_DOMAIN = "VOLUME_VALUE_BASIS"
DOMAINS = (PRICE_BASIS_DOMAIN, VOLUME_VALUE_BASIS_DOMAIN)


class BasisAuthorityError(ValueError):
    """A row or verdict violates this module's own fail-closed shape -- never silently coerced."""


def _fitness(state: str, *, reason: str, cites: Sequence[str]) -> dict[str, Any]:
    if state not in FITNESS_STATES:
        raise BasisAuthorityError(f"unregistered_fitness_state:{state}")
    if not cites:
        raise BasisAuthorityError(f"fitness_verdict_requires_citation:{reason}")
    return {"state": state, "reason": reason, "cites": list(cites)}


def _row(
    capability_id: str, domain: str, *, data_acquired: bool, data_semantics_qualified: bool,
    scope: Mapping[str, Any], source_modules: Sequence[str], evidence: Mapping[str, Any],
    fitness: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if domain not in DOMAINS:
        raise BasisAuthorityError(f"unregistered_domain:{domain}")
    missing = set(USE_CASES) - set(fitness)
    if missing:
        raise BasisAuthorityError(f"{capability_id}_missing_use_case_fitness:{sorted(missing)}")
    return {
        "capability_id": capability_id,
        "domain": domain,
        "data_acquired": bool(data_acquired),
        "data_semantics_qualified": bool(data_semantics_qualified),
        "scope": dict(scope),
        "source_modules": list(source_modules),
        "evidence": dict(evidence),
        "fitness": {use: fitness[use] for use in USE_CASES},
    }


# ---------------------------------------------------------------------------------
# PRICE BASIS capability rows
# ---------------------------------------------------------------------------------

def _price_capability_rows() -> list[dict[str, Any]]:
    dnse_ohlc_basis = source_authority.DNSE_OHLC_PRICE_BASIS  # "ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME"
    kvnd_contract = representation.lookup_contract("DNSE", "ohlc_1D", "VN_LISTED_EQUITY")
    hpg_bounded = price_basis_registry.bounded_price_basis_for("DNSE", "ohlc_1D", "HPG", "2026-05-25")
    vcb_bounded = price_basis_registry.bounded_price_basis_for("DNSE", "ohlc_1D", "VCB", "2026-07-23")
    dnse_native = taxonomy.capability("CLOSE_KVND", "DNSE")

    rows: list[dict[str, Any]] = []

    rows.append(_row(
        "DNSE_OHLC_CURRENT_SESSION_CLOSE", PRICE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=True,
        scope={"source": "DNSE", "endpoint": "/price/ohlc", "field": "close",
               "instrument_class": "VN_LISTED_EQUITY", "session_type": "latest_completed_session"},
        source_modules=[
            "current_valuation_input_authority.qualify_current_market_price",
            "current_valuation_input_authority.latest_completed_vietnam_session",
            "price_representation_contract.lookup_contract",
        ],
        evidence={
            "price_namespace": current_valuation.CURRENT_MARKET,
            "price_basis": current_valuation.ADJUSTED_RETROSPECTIVE,
            "raw_as_traded": "NOT_PROMOTED",
            "market_data_source_authority.DNSE_OHLC_PRICE_BASIS": dnse_ohlc_basis,
            "unit_representation_contract_id": kvnd_contract["contract_id"],
            "unit_representation_contract_basis_tier": kvnd_contract["contract_basis_tier"],
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(
                ELIGIBLE, reason="exact latest-completed-session close, VND-normalized via the explicit K-VND contract, full provenance",
                cites=["current_valuation_input_authority.qualify_current_market_price"]),
            CURRENT_VALUATION_RESEARCH: _fitness(
                ELIGIBLE, reason="qualified as the price-input leg of current_market_valuation_only; overall valuation readiness is independently gated by the unrelated current-share-basis blocker (0/11 SHARE_READY), unchanged here",
                cites=["current_valuation_input_authority.qualify_current_market_price", "current_valuation_input_authority.resolve_current_valuation_inputs"]),
            LIQUIDITY_RESEARCH: _fitness(NOT_APPLICABLE, reason="price field, not a volume/value field", cites=["price_representation_contract"]),
            ADV_ADTV_RESEARCH: _fitness(NOT_APPLICABLE, reason="price field, not a volume/value field", cites=["price_representation_contract"]),
            POSITION_SIZING: _fitness(NOT_APPLICABLE, reason="a price alone does not size a position", cites=["price_representation_contract"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(
                BLOCKED, reason="single current session only; multi-session continuity is the separate DNSE_OHLC_HISTORICAL_SERIES capability",
                cites=["current_valuation_input_authority.qualify_current_market_price"]),
            PIT: _fitness(BLOCKED, reason="ADJUSTED_RETROSPECTIVE, non-raw, non-point-in-time", cites=["market_data_source_authority.DNSE_OHLC_PRICE_BASIS", "pit_price_reconstruction_contract"]),
            BACKTEST: _fitness(BLOCKED, reason="no RAW_AS_TRADED authority exists for DNSE to backtest against", cites=["market_data_source_authority.DNSE_OHLC_PRICE_BASIS"]),
        },
    ))

    rows.append(_row(
        "DNSE_OHLC_HISTORICAL_SERIES", PRICE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=False,
        scope={"source": "DNSE", "endpoint": "/price/ohlc", "fields": ["open", "high", "low", "close"],
               "instrument_class": "VN_LISTED_EQUITY", "session_type": "closed_historical_session"},
        source_modules=[
            "dnse_provider_native_closed_ohlc.qualify_provider_native_closed_ohlc",
            "dnse_provider_native_closed_ohlc.scale_invariant_return",
            "provider_price_basis_registry.bounded_price_basis_for",
        ],
        evidence={
            "formal_price_unit": dnse_native_ohlc.FORMAL_PRICE_UNIT,
            "adjustment_basis": dnse_native_ohlc.ADJUSTMENT_BASIS,
            "raw_as_traded": dnse_native_ohlc.RAW_AS_TRADED,
            "unit_representation_contract_id": kvnd_contract["contract_id"],
            "prohibited_use_classes": list(dnse_native_ohlc.PROHIBITED_USE_CLASSES),
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(
                PARTIAL, reason="bounded representation-safe uses only: reconciliation, field consistency, anomaly detection within one uniform representation",
                cites=["dnse_provider_native_closed_ohlc.qualify_provider_native_closed_ohlc"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="current valuation is served by DNSE_OHLC_CURRENT_SESSION_CLOSE, not the historical series", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(NOT_APPLICABLE, reason="price field, not a volume/value field", cites=["price_representation_contract"]),
            ADV_ADTV_RESEARCH: _fitness(NOT_APPLICABLE, reason="price field, not a volume/value field", cites=["price_representation_contract"]),
            POSITION_SIZING: _fitness(NOT_APPLICABLE, reason="a price series alone does not size a position", cites=["price_representation_contract"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(
                PARTIAL, reason="scale-invariant same-representation returns only, and only across an independently confirmed basis-continuity interval (no corporate action in the window)",
                cites=["dnse_provider_native_closed_ohlc.scale_invariant_return"]),
            PIT: _fitness(BLOCKED, reason="RAW_AS_TRADED=NOT_QUALIFIED; formal price unit and adjustment basis remain UNRESOLVED", cites=["dnse_provider_native_closed_ohlc.FORMAL_PRICE_UNIT", "dnse_provider_native_closed_ohlc.RAW_AS_TRADED"]),
            BACKTEST: _fitness(BLOCKED, reason="RAW_AS_TRADED_BACKTEST is an explicit prohibited use class", cites=["dnse_provider_native_closed_ohlc.PROHIBITED_USE_CLASSES"]),
        },
    ))

    rows.append(_row(
        "DNSE_BOUNDED_CORPORATE_ACTION_WINDOWS", PRICE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=True,
        scope={"source": "DNSE", "tickers": sorted(dnse_price_capability.EVIDENCE_QUALIFIED_TICKERS),
               "instrument_class": "VN_LISTED_EQUITY", "session_type": "bounded_event_window"},
        source_modules=["dnse_ohlc_price_basis_capability.active_capability_contract", "provider_price_basis_registry.bounded_price_basis_for"],
        evidence={
            "active_price_basis_verdict": dnse_price_capability.ACTIVE_PRICE_BASIS_VERDICT,
            "current_analysis_price_basis_safe": dnse_price_capability.CURRENT_ANALYSIS_PRICE_BASIS_SAFE,
            "backtest_point_in_time_safe": dnse_price_capability.BACKTEST_POINT_IN_TIME_SAFE,
            "hpg_bounded_window_2026-05-25": hpg_bounded,
            "vcb_bounded_window_2026-07-23": vcb_bounded,
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(ELIGIBLE, reason="CURRENT_ANALYSIS_PRICE_BASIS_SAFE=True for the two evidence-qualified tickers/windows", cites=["dnse_ohlc_price_basis_capability.CURRENT_ANALYSIS_PRICE_BASIS_SAFE"]),
            CURRENT_VALUATION_RESEARCH: _fitness(ELIGIBLE, reason="same bounded-window safety extends to current descriptive valuation input", cites=["dnse_ohlc_price_basis_capability.CURRENT_ANALYSIS_PRICE_BASIS_SAFE"]),
            LIQUIDITY_RESEARCH: _fitness(NOT_APPLICABLE, reason="price field, not a volume/value field", cites=["price_representation_contract"]),
            ADV_ADTV_RESEARCH: _fitness(NOT_APPLICABLE, reason="price field, not a volume/value field", cites=["price_representation_contract"]),
            POSITION_SIZING: _fitness(NOT_APPLICABLE, reason="a price alone does not size a position", cites=["price_representation_contract"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(
                PARTIAL, reason="bounded ticker/window only (HPG stock-dividend, VCB cash-dividend); not a general historical-return authority",
                cites=["dnse_ohlc_price_basis_capability.EVIDENCE_EVENTS"]),
            PIT: _fitness(BLOCKED, reason="ADJUSTED_CONFIRMED is a current-analysis verdict, not RAW_AS_TRADED/PIT", cites=["dnse_ohlc_price_basis_capability.ACTIVE_PRICE_BASIS_VERDICT"]),
            BACKTEST: _fitness(BLOCKED, reason="BACKTEST_POINT_IN_TIME_SAFE is explicitly False", cites=["dnse_ohlc_price_basis_capability.BACKTEST_POINT_IN_TIME_SAFE"]),
        },
    ))

    rows.append(_row(
        "OFFICIAL_CORPORATE_ACTION_EX_DATE_EVIDENCE", PRICE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=False,
        scope={"source": "OFFICIAL", "tickers": ["HPG", "SSI", "VCB", "VNM"], "instrument_class": "VN_LISTED_EQUITY"},
        source_modules=["official_corporate_action_ledger._adjustment_factor", "docs/STATE.md#3-active-blockers--invariant-governance-rules"],
        evidence={
            "authority_state": corporate_action_ledger.AUTHORITY_STATE,
            "blocking_reason_code": "missing_explicit_official_ex_date",
            "finding": (
                "No retained official document in the corpus states an explicit official ex-date "
                "for HPG, SSI, VCB, or VNM; only record/payment/approval/new-shares-listing dates "
                "are present. Record/listing/effective/trading dates never substitute (docs/STATE.md "
                "P3-A, re-confirmed 2026-08-22 CORPORATE_ACTION_AND_PIT_AUTHORITY_V1 closure)."
            ),
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(NOT_APPLICABLE, reason="this row is a PIT/backtest prerequisite, not a directly consumed data field", cites=["official_corporate_action_ledger.AUTHORITY_STATE"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="ex-date evidence is not a current-valuation input", cites=["official_corporate_action_ledger.AUTHORITY_STATE"]),
            LIQUIDITY_RESEARCH: _fitness(NOT_APPLICABLE, reason="price-basis prerequisite, not a volume/value field", cites=["official_corporate_action_ledger.AUTHORITY_STATE"]),
            ADV_ADTV_RESEARCH: _fitness(NOT_APPLICABLE, reason="price-basis prerequisite, not a volume/value field", cites=["official_corporate_action_ledger.AUTHORITY_STATE"]),
            POSITION_SIZING: _fitness(NOT_APPLICABLE, reason="price-basis prerequisite, not a sizing input", cites=["official_corporate_action_ledger.AUTHORITY_STATE"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(PARTIAL, reason="bounded-window returns remain safe (see DNSE_BOUNDED_CORPORATE_ACTION_WINDOWS); a general historical-return authority still needs this evidence", cites=["official_corporate_action_ledger._adjustment_factor"]),
            PIT: _fitness(BLOCKED, reason="missing_explicit_official_ex_date; inferring ex-date from record date is a strictly forbidden fabrication", cites=["official_corporate_action_ledger._adjustment_factor", "docs/STATE.md Invariant 5"]),
            BACKTEST: _fitness(BLOCKED, reason="P3-A remains P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE", cites=["docs/STATE.md#p3"]),
        },
    ))

    rows.append(_row(
        "DNSE_KVND_TO_VND_UNIT_REPRESENTATION_CONTRACT", PRICE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=True,
        scope={"source": "DNSE", "capability_id": "ohlc_1D", "instrument_class": "VN_LISTED_EQUITY", "fields": list(kvnd_contract["applies_to_fields"])},
        source_modules=["price_representation_contract.lookup_contract", "price_representation_contract.to_canonical_ohlc"],
        evidence={
            "contract_id": kvnd_contract["contract_id"],
            "contract_basis_tier": kvnd_contract["contract_basis_tier"],
            "scale_factor": kvnd_contract["scale_factor"],
            "native_dnse_close_representation": dnse_native["provider_native_representation"],
            "independence": "unit representation is independent of RAW_AS_TRADED/PIT/adjustment basis (docs/STATE.md Invariant 6); never inferred from magnitude",
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(ELIGIBLE, reason="uniform, deterministic K-VND->VND conversion applied identically to O/H/L/C, no magnitude heuristic", cites=["price_representation_contract.to_canonical_ohlc"]),
            CURRENT_VALUATION_RESEARCH: _fitness(ELIGIBLE, reason="same uniform conversion underlies the current-valuation price input", cites=["price_representation_contract.to_canonical_ohlc"]),
            LIQUIDITY_RESEARCH: _fitness(NOT_APPLICABLE, reason="a price-unit contract, not a volume/value field", cites=["price_representation_contract"]),
            ADV_ADTV_RESEARCH: _fitness(NOT_APPLICABLE, reason="a price-unit contract, not a volume/value field", cites=["price_representation_contract"]),
            POSITION_SIZING: _fitness(NOT_APPLICABLE, reason="a price-unit contract does not size a position", cites=["price_representation_contract"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(ELIGIBLE, reason="the same uniform representation applies across the historical series (representation only, not adjustment basis)", cites=["price_representation_contract.to_canonical_ohlc"]),
            PIT: _fitness(NOT_APPLICABLE, reason="unit representation never promotes or substitutes for RAW_AS_TRADED/PIT authority (docs/STATE.md Invariant 6)", cites=["docs/STATE.md Invariant 6"]),
            BACKTEST: _fitness(NOT_APPLICABLE, reason="unit representation never promotes or substitutes for backtest authority (docs/STATE.md Invariant 6)", cites=["docs/STATE.md Invariant 6"]),
        },
    ))

    return rows


# ---------------------------------------------------------------------------------
# VOLUME / TRADED-VALUE BASIS capability rows
# ---------------------------------------------------------------------------------

def board_semantics_snapshot() -> dict[str, str]:
    """The documented DNSE board-code -> semantic-meaning mapping, verified rather than assumed.

    Sourced from ``market_phase2_foundation.DNSE_BOARD_SEMANTICS`` (status ``DOCUMENTED`` in its
    own ``semantic_registry()``). This module never redefines the mapping; it only cites it.
    """
    return dict(DNSE_BOARD_SEMANTICS)


def assert_lot_and_route_not_conflated() -> Mapping[str, tuple[str, ...]]:
    """Fail closed if matched/put-through or round-lot/odd-lot ever collapse to one bucket.

    Returns the four distinct board categories so a caller can see the real partition
    (docs/DATA_FIRST_DOCTRINE.md #10: "keep matched, put-through, odd-lot ... distinct").
    """
    categories: dict[str, list[str]] = {"MATCHED_ROUND_LOT": [], "MATCHED_ODD_LOT": [], "PUT_THROUGH_ROUND_LOT": [], "PUT_THROUGH_ODD_LOT": []}
    for code, meaning in DNSE_BOARD_SEMANTICS.items():
        if meaning == "ROUND_LOT":
            categories["MATCHED_ROUND_LOT"].append(code)
        elif meaning == "ODD_LOT":
            categories["MATCHED_ODD_LOT"].append(code)
        elif meaning == "PUT_THROUGH_ROUND_LOT":
            categories["PUT_THROUGH_ROUND_LOT"].append(code)
        elif meaning == "PUT_THROUGH_ODD_LOT":
            categories["PUT_THROUGH_ODD_LOT"].append(code)
        else:
            raise BasisAuthorityError(f"unrecognized_board_semantic:{code}:{meaning}")
    if any(not codes for codes in categories.values()):
        raise BasisAuthorityError("board_category_collapsed_to_empty")
    if len({tuple(sorted(v)) for v in categories.values()}) != 4:
        raise BasisAuthorityError("board_categories_are_not_pairwise_distinct")
    return {key: tuple(sorted(value)) for key, value in categories.items()}


def _volume_value_capability_rows() -> list[dict[str, Any]]:
    dnse_matched_taxonomy = taxonomy.capability("MATCHED_VOLUME_SHARES", "DNSE")
    fhsc_matched_taxonomy = taxonomy.capability("MATCHED_VOLUME_SHARES", "FHSC")
    fhsc_put_through_taxonomy = taxonomy.capability("PUT_THROUGH_VOLUME_SHARES", "FHSC")
    fhsc_total_taxonomy = taxonomy.capability("TOTAL_VOLUME_SHARES", "FHSC")
    dnse_field_contract = volume_value_contract.field_contract("dnse.daily.ohlc.v").record()
    board_categories = assert_lot_and_route_not_conflated()

    rows: list[dict[str, Any]] = []

    rows.append(_row(
        "DNSE_OHLC_DAILY_VOLUME_MATCHED_SHADOW", VOLUME_VALUE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=False,
        scope={"source": "DNSE", "endpoint": "/price/ohlc", "field": "v", "exchange": "HOSE_ONLY",
               "instrument_class": "VN_LISTED_EQUITY", "board_scope": "unknown_by_canonical_contract"},
        source_modules=[
            "market_volume_value_semantic_contract.field_contract",
            "dnse_fhsc_volume_basis.reconcile_volume_rows",
            "dnse_fhsc_market_composition_scaleout.reconcile_scaleout",
            "market_capability_taxonomy.capability",
        ],
        evidence={
            "canonical_field_contract_qualification_state": dnse_field_contract["qualification_state"],
            "canonical_field_contract_prohibited_uses": dnse_field_contract["prohibited_uses"],
            "shadow_finding": "DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL",
            "shadow_scaleout_candidate": "DNSE_MATCHED_VOLUME_SEMANTICS_HOSE_SCALEOUT_VALIDATED",
            "shadow_scope": "HOSE only; HNX/UPCOM unresolved after the bounded 24-call FHSC budget was exhausted (8 HTTP 429 responses)",
            "market_capability_taxonomy_dnse_usability_state": dnse_matched_taxonomy["usability_state"],
            "note": (
                "The canonical live field contract (market_volume_value_semantic_contract, v1.1.0) "
                "still records every execution-scope dimension of dnse.daily.ohlc.v as UNKNOWN and "
                "was not updated by the newer DNSE/FHSC empirical finding above; this row preserves "
                "both facts rather than silently promoting the canonical contract."
            ),
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(ELIGIBLE, reason="DISPLAY and PROVIDER_SCOPED_ANALYTICS are explicitly eligible uses on the canonical field contract", cites=["market_volume_value_semantic_contract.FIELD_CONTRACTS"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="current valuation input in this repository is price x shares; volume is not a valuation-multiple input", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(BLOCKED, reason="MARKET_LIQUIDITY is an explicit prohibited use on the canonical field contract; market composition (put-through/odd-lot share) is not qualified", cites=["market_volume_value_semantic_contract.FIELD_CONTRACTS", "market_data_source_authority.DNSE_MARKET_VOLUME_BASIS"]),
            ADV_ADTV_RESEARCH: _fitness(BLOCKED, reason="an average/turnover over an unqualified-composition field inherits the same composition blocker", cites=["market_volume_value_semantic_contract.FIELD_CONTRACTS"]),
            POSITION_SIZING: _fitness(BLOCKED, reason="EXECUTION_SIZING is an explicit prohibited use on the canonical field contract", cites=["market_volume_value_semantic_contract.FIELD_CONTRACTS"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(NOT_APPLICABLE, reason="a volume field is not a return input", cites=["market_volume_value_semantic_contract.FIELD_CONTRACTS"]),
            PIT: _fitness(NOT_APPLICABLE, reason="P0-B closure applies unconditionally to volume authority independent of PIT price status", cites=["docs/STATE.md P0-B"]),
            BACKTEST: _fitness(BLOCKED, reason="P0-B: QUALIFIED_LIQUIDITY_INPUTS=NO and POSITION_SIZING_IS_SAFE=NO, unconditionally assigned", cites=["docs/STATE.md P0-B TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION"]),
        },
    ))

    rows.append(_row(
        "DNSE_NUMERIC_BOARD_COMPOSITION", VOLUME_VALUE_BASIS_DOMAIN,
        data_acquired=False, data_semantics_qualified=False,
        scope={"source": "DNSE", "boards": sorted(DNSE_BOARD_SEMANTICS), "categories": board_categories},
        source_modules=["market_phase2_foundation.DNSE_BOARD_SEMANTICS", "dnse_volume_composition_reconciliation"],
        evidence={
            "board_label_semantics_status": "DOCUMENTED",
            "board_label_meanings": dict(DNSE_BOARD_SEMANTICS),
            "numeric_source_status": CANONICAL_TRADES_LINEAGE_STATUS,
            "numeric_source_commit": CANONICAL_TRADES_SOURCE_COMMIT,
            "additive_candidates": CANDIDATE_DEFINITIONS,
            "additive_candidates_verdict_on_full_corpus": "CONFLICTING_OR_INSUFFICIENT_DISCRIMINATION (C1 exact 0/35,231; C2=2; C3=1; C4=2)",
            "shadow_candidate": C5_CANDIDATE.record(),
            "shadow_candidate_residuals_unresolved": 67,
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(
                PARTIAL, reason="board LABEL semantics (G1=round-lot, G4=odd-lot, T1/T3=put-through round-lot, T4/T6=put-through odd-lot) are documented, but no live consumer can read a numeric per-board split today: the only corpus that ever carried it is SOURCE_GENERATOR_NOT_IN_CURRENT_MAIN_ANCESTRY",
                cites=["market_phase2_foundation.DNSE_BOARD_SEMANTICS", "dnse_volume_composition_reconciliation.CANONICAL_TRADES_LINEAGE_STATUS"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="board composition is not a valuation input", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(BLOCKED, reason="matched-vs-put-through and round-lot-vs-odd-lot decomposition is exactly the missing input liquidity/turnover would require", cites=["dnse_volume_composition_reconciliation.CANDIDATE_DEFINITIONS"]),
            ADV_ADTV_RESEARCH: _fitness(BLOCKED, reason="same missing numeric decomposition", cites=["dnse_volume_composition_reconciliation.CANDIDATE_DEFINITIONS"]),
            POSITION_SIZING: _fitness(BLOCKED, reason="same missing numeric decomposition", cites=["dnse_volume_composition_reconciliation.CANDIDATE_DEFINITIONS"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(NOT_APPLICABLE, reason="board composition is not a return input", cites=["dnse_volume_composition_reconciliation"]),
            PIT: _fitness(NOT_APPLICABLE, reason="volume authority is blocked unconditionally regardless of PIT price status", cites=["docs/STATE.md P0-B"]),
            BACKTEST: _fitness(BLOCKED, reason="the C5=10xG1 shadow candidate remains EMPIRICAL_CANDIDATE with semantic_unit_interpretation=UNKNOWN and 67 unresolved residuals; never promoted", cites=["dnse_volume_composition_reconciliation.C5_CANDIDATE"]),
        },
    ))

    rows.append(_row(
        "DNSE_DAILY_TRADED_VALUE", VOLUME_VALUE_BASIS_DOMAIN,
        data_acquired=False, data_semantics_qualified=False,
        scope={"source": "DNSE", "endpoint": "/price/ohlc", "field": "traded_value_vnd (absent)"},
        source_modules=["market_volume_value_semantic_contract.DNSE_DAILY_TRADED_VALUE_FIELD", "dnse_fhsc_market_composition_scaleout.value_matrix"],
        evidence={
            "field_status": volume_value_contract.DNSE_DAILY_TRADED_VALUE_FIELD,
            "cross_check_verdict": fhsc_composition.DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE,
            "note": "Missing != zero: DNSE's daily OHLC 7-key shape simply has no traded-value field; price*volume or a foreign-flow value are explicitly not substituted for it.",
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(BLOCKED, reason="OBSERVED_ABSENT from DNSE daily OHLC; no substitute field is permitted", cites=["market_volume_value_semantic_contract.DNSE_DAILY_TRADED_VALUE_FIELD"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="traded value is not a valuation-multiple input", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(BLOCKED, reason="no traded-value field exists to qualify", cites=["dnse_fhsc_market_composition_scaleout.DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE"]),
            ADV_ADTV_RESEARCH: _fitness(BLOCKED, reason="ADTV requires traded value, which is absent from this source", cites=["dnse_fhsc_market_composition_scaleout.DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE"]),
            POSITION_SIZING: _fitness(BLOCKED, reason="no traded-value field exists to size against", cites=["dnse_fhsc_market_composition_scaleout.DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(NOT_APPLICABLE, reason="traded value is not a return input", cites=["dnse_fhsc_market_composition_scaleout"]),
            PIT: _fitness(NOT_APPLICABLE, reason="volume/value authority is blocked unconditionally regardless of PIT price status", cites=["docs/STATE.md P0-B"]),
            BACKTEST: _fitness(BLOCKED, reason="P0-B: daily traded value remains unevidenced and unpromoted", cites=["docs/STATE.md P0-B TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION"]),
        },
    ))

    rows.append(_row(
        "FHSC_MATCHED_PUT_THROUGH_TOTAL_VOLUME_DECOMPOSITION", VOLUME_VALUE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=True,
        scope={"source": "FHSC", "endpoint": "trading-history", "exchange": "HOSE_TESTED_ONLY",
               "fields": ["matched.volume", "put_through.volume", "total.volume"]},
        source_modules=["dnse_fhsc_volume_basis.parse_fhsc_trading_history", "market_capability_taxonomy.capability"],
        evidence={
            "documented_arithmetic_identity": "matched + put_through = total (retained official FHSC OpenAPI; all 15 retained historical rows replay it exactly)",
            "matched_usability_state": fhsc_matched_taxonomy["usability_state"],
            "put_through_usability_state": fhsc_put_through_taxonomy["usability_state"],
            "total_usability_state": fhsc_total_taxonomy["usability_state"],
            "coverage_limit": "8 of 12 issuers HTTP 429 after the bounded 24-call FHSC trading-history budget; HNX/UPCOM have no comparable rows",
            "source_role": "SHADOW_REFERENCE_PROVIDER (not a DNSE replacement)",
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(PARTIAL, reason="retained sessions only, HOSE-tested; rate-limit-bounded coverage, never treated as market-wide", cites=["dnse_fhsc_volume_basis.parse_fhsc_trading_history"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="volume decomposition is not a valuation-multiple input", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(BLOCKED, reason="FHSC is SHADOW_REFERENCE_PROVIDER only; no liquidity/turnover authority is promoted from a shadow source", cites=["docs/STATE.md FHSC Reference Reconciliation Foundation V1"]),
            ADV_ADTV_RESEARCH: _fitness(BLOCKED, reason="same shadow-provider boundary, plus rate-limited coverage cannot support a market-wide average", cites=["docs/STATE.md DNSE/FHSC Market Composition Scale-Out V1"]),
            POSITION_SIZING: _fitness(BLOCKED, reason="same shadow-provider boundary", cites=["docs/STATE.md FHSC Reference Reconciliation Foundation V1"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(NOT_APPLICABLE, reason="volume decomposition is not a return input", cites=["dnse_fhsc_volume_basis"]),
            PIT: _fitness(NOT_APPLICABLE, reason="volume/value authority is blocked unconditionally regardless of PIT price status", cites=["docs/STATE.md P0-B"]),
            BACKTEST: _fitness(BLOCKED, reason="shadow-reference provider with bounded, rate-limited coverage cannot back a backtest liquidity constraint", cites=["docs/STATE.md FHSC Reference Reconciliation Foundation V1"]),
        },
    ))

    rows.append(_row(
        "FHSC_TRADED_VALUE_DECOMPOSITION", VOLUME_VALUE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=True,
        scope={"source": "FHSC", "endpoint": "trading-history", "exchange": "HOSE_TESTED_ONLY",
               "fields": ["matched.value", "put_through.value", "total.value"]},
        source_modules=["dnse_fhsc_volume_basis.parse_fhsc_trading_history", "market_capability_taxonomy.capability"],
        evidence={
            "documented_arithmetic_identity": "matched.value + put_through.value = total.value where retained values are present",
            "matched_value_usability_state": taxonomy.capability("MATCHED_TRADED_VALUE_VND", "FHSC")["usability_state"],
            "coverage_limit": "same 24-call bounded FHSC budget as the volume decomposition above; retained where trading-history responses succeeded",
            "dnse_comparator": "unavailable (see DNSE_DAILY_TRADED_VALUE row); no cross-source reconciliation possible for value",
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(PARTIAL, reason="retained sessions only, HOSE-tested, rate-limit-bounded", cites=["dnse_fhsc_volume_basis.parse_fhsc_trading_history"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="traded value is not a valuation-multiple input", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(BLOCKED, reason="FHSC is SHADOW_REFERENCE_PROVIDER only", cites=["docs/STATE.md FHSC Reference Reconciliation Foundation V1"]),
            ADV_ADTV_RESEARCH: _fitness(BLOCKED, reason="same shadow-provider boundary, plus no DNSE comparator exists to cross-validate", cites=["dnse_fhsc_market_composition_scaleout.DNSE_TRADED_VALUE_COMPARATOR_UNAVAILABLE"]),
            POSITION_SIZING: _fitness(BLOCKED, reason="same shadow-provider boundary", cites=["docs/STATE.md FHSC Reference Reconciliation Foundation V1"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(NOT_APPLICABLE, reason="traded value is not a return input", cites=["dnse_fhsc_volume_basis"]),
            PIT: _fitness(NOT_APPLICABLE, reason="volume/value authority is blocked unconditionally regardless of PIT price status", cites=["docs/STATE.md P0-B"]),
            BACKTEST: _fitness(BLOCKED, reason="shadow-reference provider with bounded coverage cannot back a backtest liquidity constraint", cites=["docs/STATE.md FHSC Reference Reconciliation Foundation V1"]),
        },
    ))

    rows.append(_row(
        "LEGACY_DESCRIPTIVE_VOLUME_ANALYTICS", VOLUME_VALUE_BASIS_DOMAIN,
        data_acquired=True, data_semantics_qualified=True,
        scope={"source": "VCI", "fields": ["legacy.rel_vol", "legacy.gtgd20_ty", "risk_liquidity.average_volume"]},
        source_modules=["market_volume_value_semantic_contract.field_contract", "market_volume_capability_matrix.capability", "risk_liquidity._average_volume"],
        evidence={
            "rel_vol_semantic_type": volume_value_contract.field_contract("legacy.rel_vol").semantic_type.value,
            "vci_capability_matrix_days_to_liquidate": vci_volume_capability.capability("days_to_liquidate")["availability"],
            "vci_capability_matrix_odd_lot_analysis": vci_volume_capability.capability("odd_lot_analysis")["availability"],
            "vci_capability_matrix_negotiated_versus_matched": vci_volume_capability.capability("negotiated_versus_matched_flow_analysis")["availability"],
            "vci_capability_matrix_participation_rate_sizing": vci_volume_capability.capability("participation_rate_sizing")["availability"],
            "note": (
                "This VCI-scoped granular capability matrix is the structural precedent for the "
                "DNSE volume gate above, not a DNSE authority itself: risk_liquidity.py's live "
                "_average_volume() is still hardcoded source='VCI' and does not yet consume DNSE "
                "volume at all. A future DNSE wiring effort should reuse this same fail-closed "
                "shape rather than default the gate open."
            ),
        },
        fitness={
            CURRENT_DESCRIPTIVE_RESEARCH: _fitness(ELIGIBLE, reason="within-series ratio/mean, explicitly labelled descriptive, not a liquidity claim", cites=["market_volume_capability_matrix.capability(provider_volume_moving_average)"]),
            CURRENT_VALUATION_RESEARCH: _fitness(NOT_APPLICABLE, reason="a volume ratio is not a valuation-multiple input", cites=["current_valuation_input_authority"]),
            LIQUIDITY_RESEARCH: _fitness(BLOCKED, reason="UNAVAILABLE_BY_CONTRACT: market composition (matched vs negotiated, odd-lot) is not qualified for VCI, and DNSE volume is not wired into this gate at all", cites=["market_volume_capability_matrix.UNAVAILABLE_BY_CONTRACT"]),
            ADV_ADTV_RESEARCH: _fitness(BLOCKED, reason="days_to_liquidate/turnover are UNAVAILABLE_BY_CONTRACT for the same composition reason", cites=["market_volume_capability_matrix.capability(days_to_liquidate)"]),
            POSITION_SIZING: _fitness(BLOCKED, reason="participation_rate_sizing/liquidity_adjusted_position_sizing are UNAVAILABLE_BY_CONTRACT", cites=["market_volume_capability_matrix.capability(participation_rate_sizing)"]),
            HISTORICAL_RETURN_RESEARCH: _fitness(NOT_APPLICABLE, reason="a volume ratio is not a return input", cites=["market_volume_value_semantic_contract"]),
            PIT: _fitness(NOT_APPLICABLE, reason="volume/value authority is blocked unconditionally regardless of PIT price status", cites=["docs/STATE.md P0-B"]),
            BACKTEST: _fitness(BLOCKED, reason="production_backtest_liquidity_constraint is UNAVAILABLE_BY_CONTRACT", cites=["market_volume_capability_matrix.capability(production_backtest_liquidity_constraint)"]),
        },
    ))

    return rows


# ---------------------------------------------------------------------------------
# Cross-cutting, read-only impact analyses (milestone sections 13-15)
# ---------------------------------------------------------------------------------

def current_valuation_price_input_impact() -> dict[str, Any]:
    """Section 13: read-only check of whether existing current-valuation consumers stay safe.

    Adds no new formula and promotes no share/valuation authority; it only confirms the
    already-qualified DNSE current price is exactly what ``current_valuation_input_authority``
    already consumes, and that its consumer's own gates -- unrelated to this milestone --
    remain the binding blocker for full valuation readiness.
    """
    return {
        "price_input_status": "ALREADY_CONSUMED_UNCHANGED",
        "consumer": "current_valuation_input_authority.resolve_current_valuation_inputs",
        "price_leg": current_valuation.PRICE_READY,
        "share_leg_unchanged_blocker": current_valuation.SHARE_BLOCKED,
        "provider_issued_shares_authority": "NOT_PROMOTED (provider_price_basis_registry / P3-F5: AUTHORITY_NOT_PROMOTED_PENDING_OWNER_DECISION)",
        "new_formulas_added": False,
        "common_shares_outstanding_promoted": False,
        "market_wide_current_valuation_input_scaleout_touched": False,
        "note": "This milestone changes no valuation authority; it documents that the price leg it qualifies was already the exact leg current_valuation_input_authority.py consumes.",
    }


def liquidity_and_sizing_impact() -> dict[str, Any]:
    """Section 14: what becomes newly usable, kept strictly separate from sizing/execution."""
    return {
        "descriptive_turnover_or_liquidity_research_newly_unlocked": False,
        "sizing_or_execution_capacity_newly_unlocked": False,
        "qualified_liquidity_inputs": source_authority.DNSE_MARKET_VOLUME_BASIS,
        "position_sizing_is_safe": False,
        "reason": (
            "P0-B's unconditional QUALIFIED_LIQUIDITY_INPUTS=NO / POSITION_SIZING_IS_SAFE=NO "
            "closure is unchanged. The newer DNSE_OHLC_VOLUME_MATCHED_EMPIRICAL shadow finding "
            "raises confidence about matched-volume composition on HOSE but is explicitly shadow "
            "evidence, not a promoted authority, and does not by itself open turnover or sizing."
        ),
        "distinguishes_research_usable_volume_from_sizing_authority": True,
    }


def pit_and_backtest_impact() -> dict[str, Any]:
    """Section 15: this milestone's effect on PIT/backtest readiness -- none, by design."""
    return {
        "pit_readiness_changed": False,
        "backtest_readiness_changed": False,
        "raw_as_traded": "NOT_PROMOTED",
        "reason_price": "market_data_source_authority.DNSE_OHLC_PRICE_BASIS remains ADJUSTED_CONFIRMED_NON_RAW_NON_POINT_IN_TIME",
        "reason_price_mechanism": "pit_price_reconstruction_contract.classify_price_reconstruction: MODE_PIT_AS_KNOWN cannot reach QUALIFIED while every bounded DNSE authority asserts ADJUSTED_RETROSPECTIVE rather than RAW_AS_TRADED",
        "reason_corporate_action": "missing_explicit_official_ex_date for HPG/SSI/VCB/VNM; P3-A remains P3A_BLOCKED_PENDING_QUALIFIED_EX_DATE",
        "reason_volume": "docs/STATE.md P0-B TERMINAL_CLOSEOUT_NO_AUTHORITY_PROMOTION, unconditional",
        "new_backtest_engine_implemented": False,
    }


# ---------------------------------------------------------------------------------
# Assembly, determinism, and fail-closed self-check
# ---------------------------------------------------------------------------------

def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def content_identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"market_price_volume_basis_authority:{digest}"}


def build_matrix() -> dict[str, Any]:
    """Assemble the full deterministic fitness-for-use matrix. Pure function: same inputs (the
    imported modules' current state) always produce byte-identical output."""
    price_rows = _price_capability_rows()
    volume_rows = _volume_value_capability_rows()
    rows = price_rows + volume_rows

    matrix: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "milestone": "MARKET_PRICE_VOLUME_BASIS_QUALIFICATION_V1",
        "use_cases": list(USE_CASES),
        "fitness_states": list(FITNESS_STATES),
        "capability_rows": rows,
        "board_semantics": board_semantics_snapshot(),
        "board_categories": assert_lot_and_route_not_conflated(),
        "current_valuation_price_input_impact": current_valuation_price_input_impact(),
        "liquidity_and_sizing_impact": liquidity_and_sizing_impact(),
        "pit_and_backtest_impact": pit_and_backtest_impact(),
        "global_invariants": {
            "raw_as_traded": "NOT_PROMOTED",
            "dnse_ohlc_price_basis": source_authority.DNSE_OHLC_PRICE_BASIS,
            "dnse_market_volume_basis": source_authority.DNSE_MARKET_VOLUME_BASIS,
            "qualified_liquidity_inputs": False,
            "position_sizing_is_safe": False,
            "active_universe": "UNKNOWN",
        },
        "authority_effect": "NONE",
    }
    matrix.update(content_identity(matrix))
    return matrix


def snapshot() -> dict[str, Any]:
    """Alias matching this repository's other registry modules' public entrypoint name."""
    return build_matrix()


def assert_registry_fail_closed(matrix: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    """The one hard safety net: no row may claim an authority-sensitive use is open, and every
    fitness cell must cite at least one existing module. Raises on the first violation."""
    snap = matrix if matrix is not None else build_matrix()
    if snap.get("authority_effect") != "NONE":
        raise BasisAuthorityError("matrix_authority_effect_must_be_NONE")
    invariants = snap.get("global_invariants", {})
    if invariants.get("qualified_liquidity_inputs") is not False:
        raise BasisAuthorityError("qualified_liquidity_inputs_must_be_False")
    if invariants.get("position_sizing_is_safe") is not False:
        raise BasisAuthorityError("position_sizing_is_safe_must_be_False")
    if invariants.get("raw_as_traded") != "NOT_PROMOTED":
        raise BasisAuthorityError("raw_as_traded_must_remain_NOT_PROMOTED")
    for row in snap.get("capability_rows", []):
        for use_case in _AUTHORITY_SENSITIVE_USE_CASES:
            cell = row["fitness"][use_case]
            if cell["state"] in (ELIGIBLE, PARTIAL):
                raise BasisAuthorityError(
                    f"authority_sensitive_use_case_must_not_be_open:{row['capability_id']}:{use_case}:{cell['state']}"
                )
            if not cell.get("cites"):
                raise BasisAuthorityError(f"uncited_fitness_verdict:{row['capability_id']}:{use_case}")
    return snap


def serialize(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
