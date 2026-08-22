"""Canonical market evidence integration and per-use usability projection boundary.

WHY THIS MODULE EXISTS
    This module forms the canonical integration boundary between retained capability-first
    EOD session packets (produced by tools/collect_market_evidence.py) and downstream
    Stock Lookup research, feature, and reconciliation consumers.

THE CANONICAL PIPELINE
    retained raw/provider observations
    -> EOD session packet (session_packet.json)
    -> canonical integration boundary (this module)
    -> semantic / per-use usability projection
    -> downstream research/feature consumers

CORE INVARIANTS
    1. Provider-native observations are preserved; canonical representations are derived and
       never replace native values.
    2. Usability is projected per downstream use-case. There is no single global boolean flag.
    3. Authority effect is strictly "NONE" throughout. Research usability never confers
       RAW_AS_TRADED, liquidity/sizing, valuation, or recommendation authority.
    4. Multi-source observations for the same semantic identity remain distinct and provenance-bound;
       they are never collapsed into an averaged or synthetic consensus fact.
    5. Temporal rules strictly maintain provider_session_date != retrieved_at when they differ.
       Current-state data is never back-projected to historical sessions.
    6. Non-acquired and conflicting states (MISSING_REQUESTED_SESSION, PROVIDER_RATE_LIMITED,
       BUDGET_EXHAUSTED, SEMANTIC_UNRESOLVED, CONFLICTING) are preserved distinctly and fail closed
       for affected downstream uses without fabricating zeros or facts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping, Sequence

import market_capability_taxonomy as taxonomy
import price_representation_contract as price_contract
from field_temporal_contract import canonical_json, stable_id

CONTRACT_VERSION = "capability_first_canonical_integration/v1"
SCHEMA_VERSION = "1.0.0"

# Permitted and prohibited downstream use-case identities
USE_DESCRIPTIVE_RESEARCH_DISPLAY = "descriptive_research_display"
USE_WITHIN_SERIES_ANALYTICS = "within_series_analytics"
USE_CROSS_SOURCE_RECONCILIATION = "cross_source_reconciliation"
USE_FLOW_RESEARCH = "flow_research"
USE_CROSS_SECTIONAL_RESEARCH = "cross_sectional_research"

# Prohibited use-case identities (strictly fail-closed / blocked)
PROHIBITED_LIQUIDITY_SIZING = "liquidity_sizing"
PROHIBITED_VALUATION = "valuation"
PROHIBITED_RAW_AS_TRADED_PIT_BACKTEST = "raw_as_traded_pit_backtest"
PROHIBITED_RECOMMENDATION_AUTHORITY = "recommendation_authority"

ALL_EVALUATED_USES = (
    USE_DESCRIPTIVE_RESEARCH_DISPLAY,
    USE_WITHIN_SERIES_ANALYTICS,
    USE_CROSS_SOURCE_RECONCILIATION,
    USE_FLOW_RESEARCH,
    USE_CROSS_SECTIONAL_RESEARCH,
    PROHIBITED_LIQUIDITY_SIZING,
    PROHIBITED_VALUATION,
    PROHIBITED_RAW_AS_TRADED_PIT_BACKTEST,
    PROHIBITED_RECOMMENDATION_AUTHORITY,
)

STRICTLY_PROHIBITED_USES = frozenset({
    PROHIBITED_LIQUIDITY_SIZING,
    PROHIBITED_VALUATION,
    PROHIBITED_RAW_AS_TRADED_PIT_BACKTEST,
    PROHIBITED_RECOMMENDATION_AUTHORITY,
})

AUTHORITY_BOUNDARIES = {
    "authority_effect": "NONE",
    "raw_as_traded_promoted": False,
    "pit_backtest_eligible": False,
    "liquidity_sizing_authority": "BLOCKED",
    "valuation_authority": False,
    "recommendation_authority": False,
    "database_mutated": False,
}


@dataclass(frozen=True)
class CanonicalMarketObservation:
    """A deterministic canonical observation bound to its provider provenance and usability."""
    instrument: str
    session: str
    retrieved_at: str
    source: str
    endpoint_id: str
    capability_family: str
    semantic_identity: str
    provider_native_value: Any
    provider_native_unit: str | None
    canonical_value: Any | None
    canonical_unit: str | None
    raw_payload_identity: str
    raw_sha256: str
    observation_status: str
    usability_state: str
    conflict_state: str
    contract_id: str
    authority_effect: str
    downstream_eligibility: dict[str, bool]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observation_identity(obs: Mapping[str, Any]) -> str:
    """Compute deterministic SHA-256 identity for a canonical observation."""
    clean = {
        "instrument": obs.get("instrument"),
        "session": obs.get("session"),
        "source": obs.get("source"),
        "endpoint_id": obs.get("endpoint_id"),
        "semantic_identity": obs.get("semantic_identity"),
        "provider_native_value": obs.get("provider_native_value"),
        "provider_native_unit": obs.get("provider_native_unit"),
        "canonical_value": obs.get("canonical_value"),
        "canonical_unit": obs.get("canonical_unit"),
        "raw_sha256": obs.get("raw_sha256"),
        "observation_status": obs.get("observation_status"),
        "usability_state": obs.get("usability_state"),
        "conflict_state": obs.get("conflict_state"),
        "contract_id": obs.get("contract_id"),
    }
def canonical_representation_of(semantic_identity: str) -> str:
    """Return the canonical representation identity if distinct from native."""
    if semantic_identity.endswith("_KVND"):
        return semantic_identity.removesuffix("_KVND") + "_VND"
    if semantic_identity == "ACTIVE_BUY_COUNT":
        return "ACTIVE_BUY_ORDER_COUNT"
    if semantic_identity == "ACTIVE_SELL_COUNT":
        return "ACTIVE_SELL_ORDER_COUNT"
    return semantic_identity


def _evaluate_downstream_eligibility(
    *,
    semantic_identity: str,
    family: str,
    source: str,
    observation_status: str,
    usability_state: str,
    conflict_state: str,
) -> dict[str, bool]:
    """Evaluate eligibility per downstream use case deterministically."""
    # Base invariant: if not acquired or conflicting or rate-limited, fail closed for operational uses
    is_acquired = observation_status == "ACQUIRED"
    is_clean = conflict_state in ("CLEAN", "NONE")
    is_usable = usability_state in (taxonomy.RESEARCH_USABLE, taxonomy.SEMANTIC_MAPPED, taxonomy.RAW_RETAINED)

    eligibility: dict[str, bool] = {}

    # 1. Descriptive research display
    eligibility[USE_DESCRIPTIVE_RESEARCH_DISPLAY] = is_acquired and is_clean and is_usable

    # 2. Within-series analytics (technical indicators, returns within same provider series)
    eligibility[USE_WITHIN_SERIES_ANALYTICS] = is_acquired and is_clean and is_usable

    # 3. Cross-source reconciliation (reconciliation is permitted even on unresolved or conflicting
    #    observations so operators and engines can inspect deviations without promoting them)
    eligibility[USE_CROSS_SOURCE_RECONCILIATION] = is_acquired

    # 4. Flow research (foreign or proprietary flow research)
    is_flow_family = family in (taxonomy.FAMILY_FOREIGN, taxonomy.FAMILY_PROPRIETARY)
    eligibility[USE_FLOW_RESEARCH] = is_acquired and is_clean and is_usable and is_flow_family

    # 5. Cross-sectional breadth research
    # Price fields require explicit price representation contract; volume/flow fields eligible if usable
    eligibility[USE_CROSS_SECTIONAL_RESEARCH] = is_acquired and is_clean and is_usable

    # 6-9. Strictly prohibited uses (always False / BLOCKED)
    for prohibited in STRICTLY_PROHIBITED_USES:
        eligibility[prohibited] = False

    return eligibility


def _detect_packet_observation_conflicts(raw_obs: Mapping[str, Any]) -> str:
    """Detect arithmetic or internal consistency conflicts within a single observation."""
    native = raw_obs.get("native_fields") or {}

    # Check volume arithmetic if all three components are present
    matched_v = native.get("MATCHED_VOLUME_SHARES", {}).get("value")
    pt_v = native.get("PUT_THROUGH_VOLUME_SHARES", {}).get("value")
    tot_v = native.get("TOTAL_VOLUME_SHARES", {}).get("value")
    if matched_v is not None and pt_v is not None and tot_v is not None:
        try:
            if int(matched_v) + int(pt_v) != int(tot_v):
                return "CONFLICTING_VOLUME_ARITHMETIC"
        except (ValueError, TypeError):
            pass

    # Check traded value arithmetic if all three components are present
    matched_val = native.get("MATCHED_TRADED_VALUE_VND", {}).get("value")
    pt_val = native.get("PUT_THROUGH_TRADED_VALUE_VND", {}).get("value")
    tot_val = native.get("TOTAL_TRADED_VALUE_VND", {}).get("value")
    if matched_val is not None and pt_val is not None and tot_val is not None:
        try:
            if int(matched_val) + int(pt_val) != int(tot_val):
                return "CONFLICTING_TRADED_VALUE_ARITHMETIC"
        except (ValueError, TypeError):
            pass

    # Check foreign room arithmetic: owned + available == max_volume
    room_max = native.get("FOREIGN_ROOM_MAX", {}).get("value")
    room_owned = native.get("FOREIGN_ROOM_OWNED", {}).get("value")
    room_avail = native.get("FOREIGN_ROOM_AVAILABLE", {}).get("value")
    if room_max is not None and room_owned is not None and room_avail is not None:
        try:
            if int(room_owned) + int(room_avail) != int(room_max):
                return "CONFLICTING_FOREIGN_ROOM_ARITHMETIC"
        except (ValueError, TypeError):
            pass

    # Check proprietary flow arithmetic: buy - sell == net
    prop_buy_v = native.get("PROPRIETARY_BUY_VOLUME", {}).get("value")
    prop_sell_v = native.get("PROPRIETARY_SELL_VOLUME", {}).get("value")
    prop_net_v = native.get("PROPRIETARY_NET_VOLUME", {}).get("value")
    if prop_buy_v is not None and prop_sell_v is not None and prop_net_v is not None:
        try:
            if int(prop_buy_v) - int(prop_sell_v) != int(prop_net_v):
                return "CONFLICTING_PROPRIETARY_VOLUME_ARITHMETIC"
        except (ValueError, TypeError):
            pass

    # Check active order volume arithmetic: buy.volume - sell.volume == net_volume
    act_buy_v = native.get("ACTIVE_BUY_VOLUME", {}).get("value")
    act_sell_v = native.get("ACTIVE_SELL_VOLUME", {}).get("value")
    act_net_v = native.get("ACTIVE_NET_VOLUME", {}).get("value")
    if act_buy_v is not None and act_sell_v is not None and act_net_v is not None:
        try:
            if int(act_buy_v) - int(act_sell_v) != int(act_net_v):
                return "CONFLICTING_ACTIVE_ORDER_VOLUME_ARITHMETIC"
        except (ValueError, TypeError):
            pass

    return "CLEAN"


def integrate_session_packet(
    packet: Mapping[str, Any],
    *,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Integrate a capability-first EOD market evidence session packet into canonical observations.

    Parameters
    ----------
    packet : Mapping[str, Any]
        A session packet structure as produced by collect_market_evidence.
    options : Mapping[str, Any] | None
        Optional configuration parameters.

    Returns
    -------
    dict[str, Any]
        Deterministic integration envelope containing all canonical observations,
        provenance references, and per-use usability projections.
    """
    session_date = str(packet.get("session_date", ""))
    packet_created_at = str(packet.get("created_at", ""))
    packet_identity = str(packet.get("packet_identity", ""))
    packet_sha256 = str(packet.get("packet_sha256", ""))
    execution_mode = str(packet.get("execution_mode", "UNKNOWN"))

    raw_observations = packet.get("observations", [])
    canonical_observations: list[dict[str, Any]] = []

    counts_by_status: dict[str, int] = {}
    counts_by_usability: dict[str, int] = {}
    counts_by_family: dict[str, int] = {}
    counts_by_source: dict[str, int] = {}

    for raw_obs in raw_observations:
        instrument = str(raw_obs.get("instrument", ""))
        obs_session = str(raw_obs.get("session", session_date))
        source = str(raw_obs.get("source", ""))
        endpoint_id = str(raw_obs.get("endpoint_id", ""))
        obs_status = str(raw_obs.get("status", "UNKNOWN"))
        raw_retrieved_at = str(raw_obs.get("retrieved_at") or packet_created_at)
        raw_path = str(raw_obs.get("raw_path", ""))
        raw_sha256 = str(raw_obs.get("raw_sha256", ""))

        counts_by_status[obs_status] = counts_by_status.get(obs_status, 0) + 1
        counts_by_source[source] = counts_by_source.get(source, 0) + 1

        # Check for non-acquired or exceptional statuses
        if obs_status != "ACQUIRED":
            # Preserve non-acquired observations distinctly without creating canonical values
            usability_state = obs_status  # e.g. PROVIDER_RATE_LIMITED, BUDGET_EXHAUSTED, MISSING_REQUESTED_SESSION
            counts_by_usability[usability_state] = counts_by_usability.get(usability_state, 0) + 1

            non_acquired_record = CanonicalMarketObservation(
                instrument=instrument,
                session=obs_session,
                retrieved_at=raw_retrieved_at,
                source=source,
                endpoint_id=endpoint_id,
                capability_family="UNKNOWN",
                semantic_identity="UNACQUIRED_PAYLOAD",
                provider_native_value=None,
                provider_native_unit=None,
                canonical_value=None,
                canonical_unit=None,
                raw_payload_identity=raw_path or "UNACQUIRED",
                raw_sha256=raw_sha256 or "UNACQUIRED",
                observation_status=obs_status,
                usability_state=usability_state,
                conflict_state="NONE",
                contract_id="none",
                authority_effect="NONE",
                downstream_eligibility=_evaluate_downstream_eligibility(
                    semantic_identity="UNACQUIRED_PAYLOAD",
                    family="UNKNOWN",
                    source=source,
                    observation_status=obs_status,
                    usability_state=usability_state,
                    conflict_state="NONE",
                ),
                provenance={
                    "packet_identity": packet_identity,
                    "packet_sha256": packet_sha256,
                    "raw_path": raw_path,
                    "error_details": raw_obs.get("error_code") or raw_obs.get("reason"),
                },
            )
            canonical_observations.append(non_acquired_record.to_dict())
            continue

        # Check for internal conflicts (e.g. arithmetic inconsistencies)
        conflict_state = _detect_packet_observation_conflicts(raw_obs)
        base_usability = str(raw_obs.get("usability_state", taxonomy.RESEARCH_USABLE))
        effective_usability = taxonomy.CONFLICTING if conflict_state != "CLEAN" else base_usability

        counts_by_usability[effective_usability] = counts_by_usability.get(effective_usability, 0) + 1

        native_fields = raw_obs.get("native_fields", {})
        canonical_fields = raw_obs.get("canonical_fields", {})

        # Process each semantic identity present in native and canonical fields
        all_field_identities = sorted(set(native_fields.keys()) | set(canonical_fields.keys()))

        for identity in all_field_identities:
            family = taxonomy.family_of(identity) or "UNKNOWN"
            counts_by_family[family] = counts_by_family.get(family, 0) + 1

            native_info = native_fields.get(identity, {})
            canonical_info = canonical_fields.get(identity, {})

            p_val = native_info.get("value")
            p_unit = native_info.get("unit")
            c_val = canonical_info.get("value")
            c_unit = canonical_info.get("unit")
            contract_id = canonical_info.get("contract_id") or "identity/raw"
            contract_tier = canonical_info.get("contract_basis_tier")
            derived_from = canonical_info.get("derived_from")

            # Bidirectional linking: if native info is missing p_val but canonical has derived_from
            if p_val is None and derived_from and derived_from in native_fields:
                p_val = native_fields[derived_from].get("value")
                p_unit = native_fields[derived_from].get("unit")

            # If canonical info is missing c_val but identity points to a canonical representation
            if c_val is None:
                canonical_rep = canonical_representation_of(identity)
                if canonical_rep and canonical_rep in canonical_fields:
                    c_val = canonical_fields[canonical_rep].get("value")
                    c_unit = canonical_fields[canonical_rep].get("unit")
                    contract_id = canonical_fields[canonical_rep].get("contract_id", contract_id)
                    contract_tier = canonical_fields[canonical_rep].get("contract_basis_tier", contract_tier)
                    derived_from = canonical_fields[canonical_rep].get("derived_from", derived_from)

            # Evaluate downstream usability
            downstream_eligibility = _evaluate_downstream_eligibility(
                semantic_identity=identity,
                family=family,
                source=source,
                observation_status=obs_status,
                usability_state=effective_usability,
                conflict_state=conflict_state,
            )

            obs_record = CanonicalMarketObservation(
                instrument=instrument,
                session=obs_session,
                retrieved_at=raw_retrieved_at,
                source=source,
                endpoint_id=endpoint_id,
                capability_family=family,
                semantic_identity=identity,
                provider_native_value=p_val,
                provider_native_unit=p_unit,
                canonical_value=c_val,
                canonical_unit=c_unit,
                raw_payload_identity=raw_path,
                raw_sha256=raw_sha256,
                observation_status=obs_status,
                usability_state=effective_usability,
                conflict_state=conflict_state,
                contract_id=contract_id,
                authority_effect="NONE",
                downstream_eligibility=downstream_eligibility,
                provenance={
                    "packet_identity": packet_identity,
                    "packet_sha256": packet_sha256,
                    "raw_path": raw_path,
                    "contract_basis_tier": contract_tier,
                    "derived_from": derived_from,
                    "native_raw_field": native_info.get("raw_field"),
                },
            )
            canonical_observations.append(obs_record.to_dict())

    # Build deterministic summary envelope
    integrated_at = datetime.now(timezone.utc).isoformat()
    envelope: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "packet_identity": packet_identity,
        "packet_sha256": packet_sha256,
        "session_date": session_date,
        "execution_mode": execution_mode,
        "integrated_at": integrated_at,
        "total_canonical_observations": len(canonical_observations),
        "counts_by_status": counts_by_status,
        "counts_by_usability": counts_by_usability,
        "counts_by_family": counts_by_family,
        "counts_by_source": counts_by_source,
        "authority_boundaries": dict(AUTHORITY_BOUNDARIES),
        "observations": canonical_observations,
    }

    # Digest covers all deterministic content, excluding clock-dependent integrated_at
    deterministic_payload = {k: v for k, v in envelope.items() if k != "integrated_at"}
    digest = stable_id(deterministic_payload)
    envelope["integration_sha256"] = digest
    envelope["integration_identity"] = f"canonical_market_integration:{digest}"
    return envelope


def project_research_market_features(
    integration_result: Mapping[str, Any],
    *,
    permitted_use: str = USE_WITHIN_SERIES_ANALYTICS,
    target_symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Downstream research proof projection.

    Projects filtered canonical observations into structured research-usable feature views
    strictly conforming to the requested permitted use-case. If a prohibited use is requested,
    fails closed immediately.
    """
    if permitted_use in STRICTLY_PROHIBITED_USES:
        return {
            "status": "PROHIBITED_USE_REJECTED",
            "permitted_use_requested": permitted_use,
            "is_actionable": False,
            "reason": f"Downstream use '{permitted_use}' is strictly prohibited across all canonical market observations.",
            "features_by_instrument": {},
            "authority_effect": "NONE",
        }

    symbols_filter = set(s.upper() for s in target_symbols) if target_symbols else None
    features_by_instrument: dict[str, dict[str, Any]] = {}

    for obs in integration_result.get("observations", []):
        sym = obs.get("instrument")
        if not sym or (symbols_filter and sym not in symbols_filter):
            continue

        # Check eligibility for the specific requested use
        eligibility = obs.get("downstream_eligibility", {})
        if not eligibility.get(permitted_use, False):
            continue

        if sym not in features_by_instrument:
            features_by_instrument[sym] = {
                "instrument": sym,
                "session": obs.get("session"),
                "prices": {},
                "volumes": {},
                "traded_values": {},
                "foreign_flow": {},
                "foreign_room": {},
                "proprietary_flow": {},
                "microstructure": {},
            }

        source = obs.get("source", "UNKNOWN")
        ident = obs.get("semantic_identity", "")
        family = obs.get("capability_family", "")
        val = obs.get("canonical_value") if obs.get("canonical_value") is not None else obs.get("provider_native_value")
        unit = obs.get("canonical_unit") or obs.get("provider_native_unit")

        entry = {
            "value": val,
            "unit": unit,
            "native_value": obs.get("provider_native_value"),
            "native_unit": obs.get("provider_native_unit"),
            "source": source,
            "contract_id": obs.get("contract_id"),
            "raw_sha256": obs.get("raw_sha256"),
        }

        inst_dict = features_by_instrument[sym]
        if family == taxonomy.FAMILY_PRICE:
            if source not in inst_dict["prices"]:
                inst_dict["prices"][source] = {}
            inst_dict["prices"][source][ident] = entry
        elif family == taxonomy.FAMILY_VOLUME:
            if source not in inst_dict["volumes"]:
                inst_dict["volumes"][source] = {}
            inst_dict["volumes"][source][ident] = entry
        elif family == taxonomy.FAMILY_TRADED_VALUE:
            if source not in inst_dict["traded_values"]:
                inst_dict["traded_values"][source] = {}
            inst_dict["traded_values"][source][ident] = entry
        elif family == taxonomy.FAMILY_FOREIGN:
            if "ROOM" in ident:
                if source not in inst_dict["foreign_room"]:
                    inst_dict["foreign_room"][source] = {}
                inst_dict["foreign_room"][source][ident] = entry
            else:
                if source not in inst_dict["foreign_flow"]:
                    inst_dict["foreign_flow"][source] = {}
                inst_dict["foreign_flow"][source][ident] = entry
        elif family == taxonomy.FAMILY_PROPRIETARY:
            if source not in inst_dict["proprietary_flow"]:
                inst_dict["proprietary_flow"][source] = {}
            inst_dict["proprietary_flow"][source][ident] = entry
        elif family == taxonomy.FAMILY_MICROSTRUCTURE:
            if source not in inst_dict["microstructure"]:
                inst_dict["microstructure"][source] = {}
            inst_dict["microstructure"][source][ident] = entry

    return {
        "status": "SUCCESS",
        "permitted_use_applied": permitted_use,
        "contract_version": CONTRACT_VERSION,
        "integration_identity": integration_result.get("integration_identity"),
        "session_date": integration_result.get("session_date"),
        "is_actionable": False,
        "authority_effect": "NONE",
        "instrument_count": len(features_by_instrument),
        "features_by_instrument": features_by_instrument,
    }
