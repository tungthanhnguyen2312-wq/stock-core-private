"""Provider-independent, authority-neutral reference reconciliation.

This contract compares already-retained observations.  It never fetches a
provider, selects a winning provider, or changes any existing authority.
FHSC enters solely as a shadow reference whose observations must carry their
own field, session, finalization, unit, and provenance semantics.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
CONTRACT_VERSION = "provider_reference_observation/v1"
FHSC_OPEN_API_BASE = "https://open-api.fhsc.com.vn"

PRIMARY_CANDIDATE = "PRIMARY_CANDIDATE"
SHADOW_REFERENCE_PROVIDER = "SHADOW_REFERENCE_PROVIDER"
LEGACY_REFERENCE = "LEGACY_REFERENCE"
LEGACY_OPERATIONAL = "LEGACY_OPERATIONAL"
FACTUAL_AUTHORITY = "FACTUAL_AUTHORITY"

CLOSED_SESSION_OBSERVATION = "CLOSED_SESSION_OBSERVATION"
LIVE_OR_CURRENT_SESSION_OBSERVATION = "LIVE_OR_CURRENT_SESSION_OBSERVATION"
FINALIZATION_STATUS_UNKNOWN = "FINALIZATION_STATUS_UNKNOWN"

SEMANTICS_RESOLVED = "SEMANTICS_RESOLVED"
BASIS_UNRESOLVED = "BASIS_UNRESOLVED"
UNKNOWN_SEMANTICS = "UNKNOWN_SEMANTICS"
LEGACY_SOURCE_PROVENANCE_UNRESOLVED = "LEGACY_SOURCE_PROVENANCE_UNRESOLVED"

EXACT_MATCH = "EXACT_MATCH"
VALUE_MISMATCH = "VALUE_MISMATCH"
MISSING_SOURCE_OBSERVATION = "MISSING_SOURCE_OBSERVATION"
SESSION_MISMATCH = "SESSION_MISMATCH"
UNIT_MISMATCH = "UNIT_MISMATCH"
FINALIZATION_MISMATCH = "FINALIZATION_MISMATCH"
TIMESTAMP_SEMANTICS_UNRESOLVED = "TIMESTAMP_SEMANTICS_UNRESOLVED"
NOT_COMPARABLE = "NOT_COMPARABLE"
RECONCILIATION_VERDICTS = frozenset({
    EXACT_MATCH, VALUE_MISMATCH, MISSING_SOURCE_OBSERVATION, SESSION_MISMATCH,
    UNIT_MISMATCH, BASIS_UNRESOLVED, FINALIZATION_MISMATCH,
    TIMESTAMP_SEMANTICS_UNRESOLVED, NOT_COMPARABLE, UNKNOWN_SEMANTICS,
})

FHSC_CAPABILITY_PROFILES: tuple[dict[str, Any], ...] = (
    {"capability": "stock_quote", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["current_price", "intraday_open", "intraday_high", "intraday_low", "cumulative_volume", "updated_at"],
     "session_semantics": LIVE_OR_CURRENT_SESSION_OBSERVATION,
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "stock_history_1d", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["open", "high", "low", "close", "volume"],
     "session_semantics": "DAILY_HISTORY_OBSERVATION",
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "stock_trading", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["matched_volume", "put_through_volume", "total_volume"],
     "volume_semantics": {"matched_plus_put_through_equals_total": "OBSERVED_CONNECTOR_BEHAVIOR_NOT_AUTHORITY"},
     "session_semantics": LIVE_OR_CURRENT_SESSION_OBSERVATION,
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "stock_trading_history", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["matched_volume", "put_through_volume", "total_volume"],
     "volume_semantics": {"matched_plus_put_through_equals_total": "OBSERVED_CONNECTOR_BEHAVIOR_NOT_AUTHORITY"},
     "session_semantics": "HISTORICAL_TRADING_OBSERVATION",
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "foreign_flow", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["foreign_buy", "foreign_sell", "foreign_net"], "session_semantics": UNKNOWN_SEMANTICS,
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "proprietary_flow", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["proprietary_buy", "proprietary_sell", "proprietary_net"], "session_semantics": UNKNOWN_SEMANTICS,
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "foreign_room", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["foreign_room", "foreign_ownership"], "session_semantics": UNKNOWN_SEMANTICS,
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "stock_listing", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["symbol", "exchange", "listing_status"], "session_semantics": "CURRENT_PROVIDER_REFERENCE",
     "finalization": FINALIZATION_STATUS_UNKNOWN},
    {"capability": "financial_statement", "interface": "fhsc_open_api_tier1", "role": SHADOW_REFERENCE_PROVIDER,
     "fields": ["provider_financial_fields"], "session_semantics": UNKNOWN_SEMANTICS,
     "finalization": FINALIZATION_STATUS_UNKNOWN,
     "financial_authority": "PROVIDER_REFERENCE_DESCRIPTIVE_ONLY",
     "canonical_fact_mapping": "PROHIBITED_PENDING_ENTITY_PERIOD_SCOPE_CURRENCY_SCALE_PUBLICATION_PIT_LINEAGE_QUALIFICATION"},
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def source_topology() -> dict[str, Any]:
    """Return roles without changing the repository's current source authority."""
    return {
        "DNSE": {"role": PRIMARY_CANDIDATE, "authority": "EXISTING_REPOSITORY_CONTRACT_UNCHANGED",
                 "price_basis": "ADJUSTED_RETROSPECTIVE_CURRENT_ANALYSIS_ONLY", "raw_as_traded": "NOT_PROMOTED"},
        "FHSC": {"role": SHADOW_REFERENCE_PROVIDER, "authority": "NONE", "provider_replacement": False},
        "VNStock": {"role": LEGACY_OPERATIONAL, "authority": "LEGACY_PROVENANCE_DEPENDENT"},
        "VCI": {"role": LEGACY_REFERENCE, "authority": "LEGACY_PROVIDER_NAMESPACED"},
        "KBS": {"role": LEGACY_REFERENCE, "authority": "LEGACY_PROVIDER_NAMESPACED"},
        "official_issuer_vsdc_exchange": {"role": FACTUAL_AUTHORITY, "authority": "EXISTING_PROMOTED_FACTS_ONLY"},
    }


def fhsc_credential_status(secrets_path: Path | str | None = None) -> dict[str, Any]:
    """Inspect configured FHSC/Finhay key names only; never expose or load values."""
    names = ("FINHAY_API_KEY", "FINHAY_API_SECRET", "FHSC_API_KEY", "FHSC_API_SECRET")
    configured_env = {name for name in names if os.getenv(name, "").strip()}
    path = Path(secrets_path) if secrets_path is not None else Path(
        os.getenv("STOCK_LOOKUP_SECRETS_FILE", r"C:\Users\tungt\.stocklookup\secrets.env")
    )
    configured_file: set[str] = set()
    found = False
    try:
        found = path.is_file()
        if found:
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                stripped = line.strip()
                if stripped.startswith("export "):
                    stripped = stripped[7:].strip()
                if "=" in stripped:
                    name, _, value = stripped.partition("=")
                    if name.strip() in names and value.strip().strip("\"'"):
                        configured_file.add(name.strip())
    except OSError:
        found = False
    available = configured_env | configured_file
    pair_available = ({"FINHAY_API_KEY", "FINHAY_API_SECRET"} <= available
                      or {"FHSC_API_KEY", "FHSC_API_SECRET"} <= available)
    return {
        "credential_configured": pair_available,
        "credential_state": "FHSC_LIVE_PROBE_AVAILABLE" if pair_available else "FHSC_LIVE_PROBE_BLOCKED_CREDENTIAL_NOT_CONFIGURED",
        "secrets_file_consulted": True,
        "secrets_file_found": found,
        "configured_key_name_count": len(available),
        "secret_values_exposed": False,
    }


def provider_reference_observation(**kwargs: Any) -> dict[str, Any]:
    """Create a normalized, provenance-bearing observation without inference."""
    required = ("provider", "provider_interface", "endpoint_capability", "instrument", "session", "field")
    missing = [name for name in required if not str(kwargs.get(name) or "").strip()]
    if missing:
        raise ValueError(f"provider_reference_observation_missing:{','.join(missing)}")
    observation = {
        "provider": str(kwargs["provider"]),
        "provider_interface": str(kwargs["provider_interface"]),
        "endpoint_capability": str(kwargs["endpoint_capability"]),
        "instrument": str(kwargs["instrument"]).upper(),
        "exchange": kwargs.get("exchange"),
        "session": str(kwargs["session"]),
        "event_time": kwargs.get("event_time"),
        "retrieval_time": kwargs.get("retrieval_time"),
        "field": str(kwargs["field"]),
        "raw_value": kwargs.get("raw_value"),
        "normalized_value": kwargs.get("normalized_value"),
        "unit": kwargs.get("unit"),
        "basis": kwargs.get("basis", UNKNOWN_SEMANTICS),
        "semantic_status": kwargs.get("semantic_status", UNKNOWN_SEMANTICS),
        "finalization_status": kwargs.get("finalization_status", FINALIZATION_STATUS_UNKNOWN),
        "source_payload_identity": kwargs.get("source_payload_identity"),
        "source_payload_sha256": kwargs.get("source_payload_sha256"),
        "missing_disposition": kwargs.get("missing_disposition", "OBSERVED"),
        "provenance": dict(kwargs.get("provenance") or {}),
        "source_role": kwargs.get("source_role", SHADOW_REFERENCE_PROVIDER),
    }
    return observation


def _stable_observations(observations: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted((dict(item) for item in observations), key=lambda item: _canonical_json(item))


def reconcile_observations(observations: Iterable[Mapping[str, Any]], *, primary_provider: str = "DNSE",
                           challenger_provider: str = "FHSC") -> dict[str, Any]:
    """Reconcile one field while preserving every source observation.

    The result is comparison-only.  Matching values and provider majorities
    never select a provider or create factual authority.
    """
    rows = _stable_observations(observations)
    by_provider = {row["provider"]: row for row in rows}
    provider_counts = {provider: sum(row["provider"] == provider for row in rows) for provider in by_provider}
    primary = by_provider.get(primary_provider)
    challenger = by_provider.get(challenger_provider)
    key = {name: (primary or challenger or rows[0]).get(name) for name in ("instrument", "session", "field")} if rows else {}
    result = {
        "contract_version": CONTRACT_VERSION,
        "comparison_key": key,
        "primary_provider": primary_provider,
        "challenger_provider": challenger_provider,
        "observations": rows,
        "authority_effect": "NONE",
        "provider_majority_creates_authority": False,
        "selected_provider": None,
        "authoritative_value": None,
    }
    ambiguous = [provider for provider in (primary_provider, challenger_provider) if provider_counts.get(provider, 0) > 1]
    if ambiguous:
        result.update(verdict=NOT_COMPARABLE, reason="multiple_observations_for_comparison_provider",
                      ambiguous_providers=ambiguous, missing_providers=[])
        return result
    if not primary or not challenger:
        result.update(verdict=MISSING_SOURCE_OBSERVATION,
                      missing_providers=[provider for provider in (primary_provider, challenger_provider) if provider not in by_provider])
        return result
    if primary["instrument"] != challenger["instrument"] or primary["session"] != challenger["session"]:
        result.update(verdict=SESSION_MISMATCH, missing_providers=[])
        return result
    if primary["field"] != challenger["field"]:
        result.update(verdict=NOT_COMPARABLE, reason="field_identity_mismatch", missing_providers=[])
        return result
    if primary.get("unit") != challenger.get("unit"):
        result.update(verdict=UNIT_MISMATCH, missing_providers=[])
        return result
    if (primary.get("finalization_status") != CLOSED_SESSION_OBSERVATION
            or challenger.get("finalization_status") != CLOSED_SESSION_OBSERVATION):
        result.update(verdict=FINALIZATION_MISMATCH, missing_providers=[])
        return result
    if not primary.get("retrieval_time") or not challenger.get("retrieval_time"):
        result.update(verdict=TIMESTAMP_SEMANTICS_UNRESOLVED, missing_providers=[])
        return result
    statuses = {primary.get("semantic_status"), challenger.get("semantic_status")}
    if BASIS_UNRESOLVED in statuses:
        result.update(verdict=BASIS_UNRESOLVED, missing_providers=[])
        return result
    if UNKNOWN_SEMANTICS in statuses:
        result.update(verdict=UNKNOWN_SEMANTICS, missing_providers=[])
        return result
    if primary.get("normalized_value") is None or challenger.get("normalized_value") is None:
        result.update(verdict=NOT_COMPARABLE, reason="present_null_or_missing_normalized_value", missing_providers=[])
        return result
    result.update(verdict=EXACT_MATCH if primary["normalized_value"] == challenger["normalized_value"] else VALUE_MISMATCH,
                  missing_providers=[])
    return result


def _artifact_file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retained_dnse_observations() -> list[dict[str, Any]]:
    path = ROOT / "operations-review" / "mva-daily-investment-research-20260820" / "mva_daily_investment_research_artifact.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifact_identity = payload["artifact_identity"]
    file_hash = _artifact_file_hash(path)
    output: list[dict[str, Any]] = []
    for row in payload["stock_research"]:
        if row["ticker"] not in {"HPG", "VCB", "SSI"}:
            continue
        facts = row["ai_ready_brief"]["facts"]
        output.append(provider_reference_observation(
            provider="DNSE", provider_interface="dnse_openapi_retained_shadow", endpoint_capability="ohlc_1d",
            instrument=row["ticker"], exchange=None, session=facts["session"], event_time=None,
            retrieval_time="2026-08-20T17:20:44.267667+07:00", field="close", raw_value=facts["close"],
            normalized_value=facts["close"], unit="VND_PER_SHARE", basis="ADJUSTED_RETROSPECTIVE",
            semantic_status=SEMANTICS_RESOLVED, finalization_status=CLOSED_SESSION_OBSERVATION,
            source_payload_identity=artifact_identity, source_payload_sha256=None,
            provenance={"retained_artifact_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "retained_artifact_file_sha256": file_hash,
                        "raw_payload_identity_available": False,
                        "raw_as_traded": "NOT_PROMOTED"}, source_role=PRIMARY_CANDIDATE,
        ))
    return output


def _legacy_reference_inventory() -> list[dict[str, Any]]:
    path = ROOT / "operations-review" / "kbs-empirical-basis-20260804" / "observations.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [{"provider": row["provider"], "instrument": row["ticker"], "interface": "vnstock_kbs_adapter",
             "retained_artifact": row["artifact"], "source_payload_sha256": row["raw_response_sha256"],
             "session_overlap_with_dnse_2026_08_20": False,
             "disposition": "LEGACY_SOURCE_PROVENANCE_RECOVERABLE_BUT_NO_SAME_SESSION_OBSERVATION"}
            for row in payload["observations"] if row["ticker"] in {"HPG", "VCB", "SSI"}]


def build_offline_artifact() -> dict[str, Any]:
    """Produce the deterministic no-FHSC-credential foundation artifact."""
    dnse_rows = _retained_dnse_observations()
    reconciliations = [reconcile_observations([row]) for row in dnse_rows]
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": "FHSC_REFERENCE_RECONCILIATION_FOUNDATION",
        "source_topology": source_topology(),
        "fhsc_capability_profiles": list(FHSC_CAPABILITY_PROFILES),
        "fhsc_credential_state": fhsc_credential_status(),
        "real_probe": {"status": "FHSC_LIVE_PROBE_BLOCKED_CREDENTIAL_NOT_CONFIGURED", "network_requests": 0,
                       "raw_responses_retained": 0},
        "dnse_retained_observations": dnse_rows,
        "reconciliation_rows": reconciliations,
        "legacy_reference_inventory": _legacy_reference_inventory(),
        "legacy_reference_boundary": {
            "source_identity_rule": "PRESERVE_VCI_KBS_VNSTOCK_PROVENANCE_SEPARATELY",
            "ambiguous_legacy_disposition": LEGACY_SOURCE_PROVENANCE_UNRESOLVED,
            "same_session_legacy_comparison_available": False,
        },
        "fundamental_semantics": {
            "FHSC_financial_statement": "PROVIDER_REFERENCE_DESCRIPTIVE_ONLY",
            "canonical_fact_mapping": "NOT_PERMITTED",
            "required_future_qualification": ["issuer", "reporting_period", "periodicity", "instant_or_duration",
                                                "scope", "currency", "unit_scale", "restatement", "publication_timing",
                                                "knowledge_timing", "source_lineage"],
        },
        "authority_boundaries": {
            "fhsc_promoted": False, "dnse_replaced": False, "legacy_provider_retired": False,
            "raw_as_traded_promoted": False, "liquidity_sizing_promoted": False,
            "provider_fundamentals_promoted": False, "canonical_facts_created": 0,
            "valuation_or_recommendation_authority_created": False, "runtime_or_database_mutated": False,
        },
        "verdict": "FHSC_REFERENCE_RECONCILIATION_READY_PENDING_CREDENTIAL",
    }
    artifact["artifact_sha256"] = _content_hash(artifact)
    artifact["artifact_identity"] = f"fhsc_reference_reconciliation:{artifact['artifact_sha256']}"
    return artifact
